from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "video" / "assets" / "audio"
OUT.mkdir(parents=True, exist_ok=True)

SR = 48000
DURATION = 169.0
N = int(SR * DURATION)


def env_adsr(n: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    a = int(attack * SR)
    d = int(decay * SR)
    r = int(release * SR)
    s = max(0, n - a - d - r)
    return np.concatenate(
        [
            np.linspace(0, 1, a, endpoint=False),
            np.linspace(1, sustain, d, endpoint=False),
            np.full(s, sustain),
            np.linspace(sustain, 0, r, endpoint=False),
        ]
    )[:n]


def pad_note(freq: float, n: int, amp: float, pan: float, detune: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    phase = 2 * np.pi * (freq + detune) * t
    wave_data = (
        np.sin(phase) + 0.32 * np.sin(2 * phase + 0.4) + 0.10 * np.sin(3 * phase + 1.1) + 0.05 * np.sin(4 * phase + 0.2)
    )
    # gentle slow chorus
    wave_data *= 0.92 + 0.08 * np.sin(2 * np.pi * 0.11 * t + pan)
    left = wave_data * math.sqrt(max(0.0, 0.5 - pan * 0.5))
    right = wave_data * math.sqrt(max(0.0, 0.5 + pan * 0.5))
    return np.stack([left, right], axis=1) * amp


def lowpass(signal: np.ndarray, cutoff: float) -> np.ndarray:
    """Frequency-domain one-pole low-pass (fast, no scipy dependency)."""
    squeeze = signal.ndim == 1
    if squeeze:
        signal = signal[:, None]
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / SR)
    freqs = np.fft.rfftfreq(signal.shape[0], 1.0 / SR)
    response = alpha / (1.0 - (1.0 - alpha) * np.exp(-1j * 2.0 * np.pi * freqs / SR))
    filtered = np.fft.irfft(np.fft.rfft(signal, axis=0) * response[:, None], n=signal.shape[0], axis=0)
    return filtered[:, 0] if squeeze else filtered


def add_at(target: np.ndarray, start: float, source: np.ndarray) -> None:
    i = int(start * SR)
    if i >= len(target):
        return
    n = min(len(source), len(target) - i)
    target[i : i + n] += source[:n]


def impact(duration: float = 1.0, amp: float = 0.55) -> np.ndarray:
    n = int(duration * SR)
    t = np.arange(n) / SR
    freq = 82 * np.exp(-2.8 * t) + 34
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * np.exp(-3.6 * t) * amp
    noise = np.random.default_rng(7).normal(0, 1, n)
    noise = lowpass(noise[:, None], 180)[:, 0]
    thump = noise * np.exp(-18 * t) * amp * 0.5
    mono = body + thump
    return np.stack([mono, mono], axis=1)


def whoosh(duration: float = 0.55, amp: float = 0.10) -> np.ndarray:
    n = int(duration * SR)
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, n)
    # simple band emphasis: difference of two one-pole lowpasses
    low = lowpass(noise[:, None], 2200)[:, 0]
    lower = lowpass(noise[:, None], 500)[:, 0]
    band = low - lower
    t = np.arange(n) / n
    envelope = np.sin(np.pi * t) ** 1.7
    mono = band * envelope * amp
    return np.stack([mono, mono], axis=1)


def shimmer(duration: float = 1.4, amp: float = 0.045) -> np.ndarray:
    n = int(duration * SR)
    t = np.arange(n) / SR
    env = np.exp(-2.2 * t) * np.minimum(1, t / 0.08)
    left = np.zeros(n)
    right = np.zeros(n)
    for freq, pan in [(880, -0.3), (1320, 0.2), (1760, -0.1), (2640, 0.35)]:
        tone = np.sin(2 * np.pi * freq * t + freq) * env
        left += tone * math.sqrt(max(0, 0.5 - pan * 0.5))
        right += tone * math.sqrt(max(0, 0.5 + pan * 0.5))
    return np.stack([left, right], axis=1) * amp


def build() -> np.ndarray:
    rng = np.random.default_rng(3)
    bed = np.zeros((N, 2), dtype=np.float64)

    chords = [
        [110.00, 130.81, 164.81, 246.94],  # Am9
        [87.31, 110.00, 130.81, 164.81],  # Fmaj7
        [130.81, 164.81, 196.00, 293.66],  # Cmaj9
        [98.00, 123.47, 146.83, 164.81],  # G6
    ]
    chord_len = 8.0
    overlap = 2.0
    start = 0.0
    index = 0
    while start < DURATION:
        n = int((chord_len + overlap) * SR)
        chord = chords[index % len(chords)]
        segment = np.zeros((n, 2), dtype=np.float64)
        for j, freq in enumerate(chord):
            env = env_adsr(n, attack=2.0, decay=0.5, sustain=0.9, release=2.0)
            note = pad_note(freq, n, amp=0.16 / (j + 1) ** 0.4, pan=(-0.35 + 0.23 * j), detune=(j - 1.5) * 0.09)
            segment += note * env[:, None]
        add_at(bed, start, segment)
        start += chord_len
        index += 1

    # Air / room texture
    noise = rng.normal(0, 1, (N, 2))
    air = lowpass(noise, 5200)
    t = np.arange(N) / SR
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.035 * t)
    bed += air * (0.006 * lfo[:, None])

    # Subtle heartbeat pulse from the reveal onward.
    pulse = impact(duration=0.42, amp=0.12)
    for at in np.arange(18.0, DURATION - 1.0, 2.0):
        add_at(bed, float(at), pulse * (0.55 + 0.15 * math.sin(at * 0.7)))

    # Scene accents.
    add_at(bed, 0.0, impact(1.0, 0.38))
    add_at(bed, 0.0, shimmer(1.8, 0.030))
    add_at(bed, 7.8, whoosh(0.6, 0.07))
    add_at(bed, 17.7, impact(1.2, 0.42))
    add_at(bed, 17.7, shimmer(1.8, 0.055))
    add_at(bed, 35.7, whoosh(0.55, 0.065))
    add_at(bed, 54.7, whoosh(0.55, 0.065))
    add_at(bed, 76.7, shimmer(1.1, 0.035))
    add_at(bed, 103.7, whoosh(0.55, 0.06))
    add_at(bed, 121.3, impact(1.4, 0.52))
    add_at(bed, 121.3, whoosh(0.8, 0.06))
    add_at(bed, 135.7, whoosh(0.6, 0.065))
    add_at(bed, 154.7, impact(1.1, 0.30))
    add_at(bed, 154.7, shimmer(2.0, 0.05))

    # Soft overall low-pass to remove harshness.
    bed = lowpass(bed, 9000)

    # Fade in/out and normalize.
    fade_in = int(2.0 * SR)
    fade_out = int(4.0 * SR)
    bed[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    bed[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    peak = np.max(np.abs(bed))
    bed = bed / max(peak, 1e-9) * 0.22
    return bed


def write_wav(path: Path, data: np.ndarray) -> None:
    pcm = np.clip(data, -1, 1)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())
    print(f"wrote {path} ({DURATION:.1f}s)")


if __name__ == "__main__":
    write_wav(OUT / "music_bed.wav", build())
