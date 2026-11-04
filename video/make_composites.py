from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import make_graphics as mg

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "video" / "assets" / "screens"
PLATES = ROOT / "video" / "assets" / "plates"
OUT = ROOT / "video" / "assets" / "composites"
OUT.mkdir(parents=True, exist_ok=True)
mg.OUT = OUT

S = mg.S
CREAM = mg.CREAM
MINT = mg.MINT
TEAL = mg.TEAL
TEAL_LIGHT = mg.TEAL_LIGHT
AMBER = mg.AMBER
AMBER_LIGHT = mg.AMBER_LIGHT
RED = mg.RED
RED_LIGHT = mg.RED_LIGHT
PURPLE = mg.PURPLE
BLUE = mg.BLUE
INK = mg.INK
MUTED = mg.MUTED
PAPER = mg.PAPER
PAPER_LIGHT = mg.PAPER_LIGHT
DARK = mg.DARK


def paste_card(c: mg.Canvas, path: Path, box, xy, width: int | None = None, radius: int = 12) -> tuple[int, int]:
    img = Image.open(path).convert("RGB").crop(box)
    if width:
        img = img.resize((width, int(img.height * width / img.width)), Image.LANCZOS)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
    big = img.resize((img.width * S, img.height * S), Image.LANCZOS)
    big_mask = mask.resize(big.size, Image.LANCZOS)
    w, h = img.size
    c.rect((xy[0] - 3, xy[1] - 3, xy[0] + w + 3, xy[1] + h + 3), fill="#0B0908", radius=radius + 3)
    c.image.paste(big, (xy[0] * S, xy[1] * S), big_mask)
    c.draw = ImageDraw.Draw(c.image)
    return w, h


def label(c: mg.Canvas, x: int, y: int, text: str, color=AMBER_LIGHT) -> None:
    c.text((x, y), text, mg.font(mg.CONSOLAS_BOLD, 18), color, spacing=2.0)


def finding_receipt() -> None:
    c = mg.Canvas(DARK)
    c.gradient("#1A1512", "#0F0D0C")
    c.glow(1530, 280, 620, 420, TEAL, 70)
    c.glow(260, 930, 520, 380, AMBER, 32)
    c.grid(80, 8)
    c.noise(4)
    c.wordmark(112, 64)

    label(c, 112, 190, "04 / THE FINDING")
    c.text((112, 232), "Historical owner found.", mg.font(mg.GEORGIA_BOLD, 70), CREAM)
    c.text(
        (112, 326),
        "HIGH confidence   ·   12 evidence records   ·   1 coverage gap",
        mg.font(mg.CONSOLAS, 19),
        MINT,
    )
    c.text((112, 384), "REAL PRODUCT UI  ·  CASE A", mg.font(mg.CONSOLAS_BOLD, 14), MUTED, spacing=1.6)

    paste_card(c, SHOTS / "09_lineage_a_owner.png", (450, 650, 1735, 995), (318, 420), width=1285, radius=14)

    chips = [
        ("EXACT ARN MATCH", "#122522", MINT, TEAL_LIGHT),
        ("WORKSPACE orders-prod", "#2B1B05", AMBER_LIGHT, AMBER),
        ("RUN run-historical-042", "#1B1233", "#C4B5FD", PURPLE),
        ("ACTOR arjun.mehta@example.com", "#0B1B33", "#BFDBFE", BLUE),
    ]
    x = 318
    for text, bg, fg, border in chips:
        w, _ = c.pill(x, 802, text, mg.font(mg.CONSOLAS_BOLD, 15), fg, bg, border, 16, 10)
        x += w + 10

    c.line([(318, 888), (1600, 888)], "#3B302A", 1)
    c.text((318, 914), "A historical manager — not a current owner.", mg.font(mg.GEORGIA_ITALIC, 34), MINT)
    c.text((112, 1002), "The verdict is deterministic. The receipts are attached.", mg.font(mg.SEGOE, 19), "#A79C8E")
    c.save("08_finding_receipt.png")


def coverage_gap() -> None:
    c = mg.Canvas(PAPER)
    c.gradient("#FBF9F4", "#F1ECE1")
    c.grid(80, 5)
    c.noise(3)
    c.wordmark(100, 64, INK, TEAL)
    label(c, 100, 176, "05 / THE LIMIT", TEAL)
    c.text((100, 214), "Missing data is not proof of absence.", mg.font(mg.GEORGIA_BOLD, 58), INK)
    c.text(
        (100, 298),
        "GroundTruth reports coverage gaps explicitly. It never turns an unchecked source into a clean result.",
        mg.font(mg.SEGOE, 23),
        MUTED,
    )

    # Quote panel
    c.rect((100, 390, 850, 880), fill="#171310", outline="#3B302A", width=1, radius=18)
    c.text((140, 424), "“", mg.font(mg.GEORGIA_BOLD, 96), TEAL_LIGHT)
    c.text((140, 510), "When a source", mg.font(mg.GEORGIA_ITALIC, 38), CREAM)
    c.text((140, 562), "can't be checked,", mg.font(mg.GEORGIA_ITALIC, 38), CREAM)
    c.text((140, 614), "you see a gap —", mg.font(mg.GEORGIA_ITALIC, 38), MINT)
    c.text((140, 666), "not an empty result.", mg.font(mg.GEORGIA_ITALIC, 38), MINT)
    c.rect((140, 758, 530, 812), fill="#2A1512", outline=RED, width=1, radius=27)
    c.text((162, 773), "COVERAGE GAP ≠ ABSENCE", mg.font(mg.CONSOLAS_BOLD, 16), "#FEE4E2")
    c.text((140, 838), "The report says what it could not see.", mg.font(mg.SEGOE, 18), "#A79C8E")

    # Coverage table
    c.rect((890, 390, 1820, 880), fill=PAPER_LIGHT, outline="#DED6C8", width=1, radius=18)
    c.text((920, 418), "COVERAGE  /  CASE A", mg.font(mg.CONSOLAS_BOLD, 16), TEAL, spacing=1.8)
    c.text((920, 444), "From the exported evidence bundle", mg.font(mg.SEGOE, 17), MUTED)
    c.line([(920, 480), (1790, 480)], "#E4DDD0", 1)

    rows = [
        ("AWS Lambda", "success", "identity loaded", TEAL),
        ("Scalr", "success", "workspace · run · state", AMBER),
        ("Git", "success", "commit · file matches", BLUE),
        ("CloudTrail", "success", "2 management events", RED),
        ("CloudWatch", "success", "672 datapoints", "#0891B2"),
        ("CloudWatch Omni", "not configured", "visible coverage gap", AMBER),
    ]
    y = 494
    for name, status, detail, color in rows:
        c.circle(938, y + 20, 6, fill=color)
        c.text((958, y + 4), name, mg.font(mg.SEGOE_SEMI, 19), INK)
        c.text((958, y + 29), detail, mg.font(mg.CONSOLAS, 14), MUTED)
        is_gap = status == "not configured"
        c.text(
            (1778, y + 15),
            status.upper(),
            mg.font(mg.CONSOLAS_BOLD, 14),
            RED if is_gap else TEAL,
            anchor="ra",
        )
        c.line([(920, y + 50), (1790, y + 50)], "#ECE6DA", 1)
        y += 54
    c.rect((920, 820, 1790, 870), fill="#FFF8E7", outline="#F3D9A4", width=1, radius=10)
    c.text((940, 833), "1 coverage gap reported. 6 sources checked.", mg.font(mg.CONSOLAS_BOLD, 15), "#92400E")
    c.save("09_coverage_gap.png")


def bundle_checksum() -> None:
    c = mg.Canvas(DARK)
    c.gradient("#191411", "#0D0B0A")
    c.glow(1500, 300, 620, 420, TEAL, 65)
    c.glow(200, 900, 520, 380, AMBER, 28)
    c.grid(80, 7)
    c.noise(4)
    c.wordmark(112, 64)
    label(c, 112, 184, "07 / THE RECEIPT")
    c.text((112, 222), "Portable. Redacted. Checksummed.", mg.font(mg.GEORGIA_BOLD, 62), CREAM)
    c.text(
        (112, 306),
        "The same evidence bundle the app downloads — JSON, Markdown, and a SHA-256 you can recompute.",
        mg.font(mg.SEGOE, 22),
        "#CFC5B8",
    )

    # Code panel
    c.rect((112, 386, 1000, 894), fill="#0B0908", outline="#3B302A", width=1, radius=16)
    c.text((142, 412), "groundtruth_bundle.json", mg.font(mg.CONSOLAS_BOLD, 15), MINT)
    c.text((970, 412), "REAL EXPORT", mg.font(mg.CONSOLAS, 12), MUTED, anchor="ra")
    lines = [
        ("{", "#A79C8E"),
        ('  "status": "HISTORICAL_OWNER_FOUND",', "#FBBF24"),
        ('  "confidence": "HIGH",', "#FBBF24"),
        ('  "redaction_applied": true,', "#93C5FD"),
        ('  "ai_explanation": {', "#A79C8E"),
        ('    "generated_by": "muse-spark",', "#5EEAD4"),
        ('    "model": "muse-spark-1.3",', "#5EEAD4"),
        ('    "tool_calls_used": 1', "#5EEAD4"),
        ("  },", "#A79C8E"),
        ('  "integrity": {', "#A79C8E"),
        ('    "algorithm": "sha256",', "#F9A8D4"),
        ('    "checksum": "e1f4bdbd…5e4e"', "#F9A8D4"),
        ("  }", "#A79C8E"),
        ("}", "#A79C8E"),
    ]
    y = 456
    for text, color in lines:
        c.text((142, y), text, mg.font(mg.CONSOLAS, 19), color)
        y += 29

    # Checksum panel
    c.rect((1040, 386, 1810, 894), fill="#13201D", outline=TEAL, width=2, radius=16)
    c.text((1072, 414), "SHA-256 INTEGRITY", mg.font(mg.CONSOLAS_BOLD, 16), MINT, spacing=1.6)
    c.text((1072, 460), "Verified", mg.font(mg.GEORGIA_BOLD, 72), CREAM)
    c.text((1072, 560), "e1f4bdbd61303fefcc4b551ed0022262", mg.font(mg.CONSOLAS, 23), TEAL_LIGHT)
    c.text((1072, 596), "0727025b876543a758d4a8b9902c5e4e", mg.font(mg.CONSOLAS, 23), TEAL_LIGHT)
    c.text((1072, 650), "Computed over the bundle payload", mg.font(mg.SEGOE, 17), "#A7C4BD")
    c.text((1072, 675), "excluding the integrity block.", mg.font(mg.SEGOE, 17), "#A7C4BD")
    c.rect((1072, 720, 1430, 768), fill="#122522", outline=TEAL_LIGHT, width=1, radius=24)
    c.text((1092, 733), "ACCOUNT IDs REDACTED", mg.font(mg.CONSOLAS_BOLD, 14), MINT)
    c.text((1072, 800), "12 EVIDENCE   ·   6 SOURCES   ·   1 GAP", mg.font(mg.CONSOLAS_BOLD, 15), CREAM)
    c.text((1072, 834), "JSON 50 KB   ·   MARKDOWN 14 KB", mg.font(mg.CONSOLAS, 15), "#A7C4BD")

    c.text(
        (112, 940), "Attach it to a change request, an incident review, or an audit.", mg.font(mg.SEGOE_SEMI, 22), MINT
    )
    c.text((1810, 940), "DEMO / FIXTURE DATA", mg.font(mg.CONSOLAS_BOLD, 15), AMBER_LIGHT, anchor="ra")
    c.save("12_bundle_checksum.png")


def hardstop() -> None:
    c = mg.Canvas(DARK)
    c.gradient("#1C1210", "#0C0808")
    c.glow(960, 500, 760, 480, RED, 70)
    c.grid(80, 7)
    c.noise(4)
    c.wordmark(112, 64)
    label(c, 112, 184, "08 / THE HARD STOP", RED_LIGHT)
    c.text((112, 222), "The engine knows", mg.font(mg.GEORGIA_BOLD, 70), CREAM)
    c.text((112, 302), "when to stop.", mg.font(mg.GEORGIA_BOLD, 70), CREAM)
    c.text(
        (112, 402),
        "Two active workspaces claim the exact same Lambda ARN.",
        mg.font(mg.SEGOE, 24),
        "#D8CCC0",
    )
    c.text(
        (112, 438),
        "GroundTruth returns MULTIPLE ACTIVE OWNERS and blocks adoption.",
        mg.font(mg.SEGOE, 24),
        "#D8CCC0",
    )
    stamp = Image.open(mg.OUT.parent / "graphics" / "stamp_blocked.png").convert("RGBA")
    stamp = stamp.resize((int(stamp.width * 1.02), int(stamp.height * 1.02)), Image.LANCZOS)
    stamp_big = stamp.resize((stamp.width * S, stamp.height * S), Image.LANCZOS)
    sx, sy = 600, 560
    c.image = c.image.convert("RGBA")
    c.image.alpha_composite(stamp_big, (sx * S, sy * S))
    c.image = c.image.convert("RGB")
    c.draw = ImageDraw.Draw(c.image)
    c.text((112, 930), "No winner is picked. No change is authorized.", mg.font(mg.GEORGIA_ITALIC, 34), MINT)
    c.text((1810, 1000), "DETERMINISTIC HARD STOP", mg.font(mg.CONSOLAS_BOLD, 15), RED_LIGHT, anchor="ra")
    c.save("13_hardstop.png")


def main() -> None:
    finding_receipt()
    coverage_gap()
    bundle_checksum()
    hardstop()


if __name__ == "__main__":
    main()
