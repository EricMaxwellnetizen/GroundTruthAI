from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "video" / "assets" / "graphics"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
S = 2  # supersampling

INK = "#1C1917"
MUTED = "#6B625A"
PAPER = "#F7F5EF"
PAPER_LIGHT = "#FFFDF8"
DARK = "#151210"
DARK_2 = "#1D1916"
CREAM = "#FFF8EC"
TEAL = "#0F766E"
TEAL_LIGHT = "#5EEAD4"
MINT = "#A7F3D0"
AMBER = "#D97706"
AMBER_LIGHT = "#FBBF24"
RED = "#B42318"
RED_LIGHT = "#F97066"
PURPLE = "#6D4AFF"
BLUE = "#2563EB"

FONT_DIR = Path("C:/Windows/Fonts")
GEORGIA_BOLD = FONT_DIR / "georgiab.ttf"
GEORGIA = FONT_DIR / "georgia.ttf"
GEORGIA_ITALIC = FONT_DIR / "georgiai.ttf"
SEGOE = FONT_DIR / "segoeui.ttf"
SEGOE_BOLD = FONT_DIR / "segoeuib.ttf"
SEGOE_SEMI = FONT_DIR / "seguisb.ttf"
CONSOLAS = FONT_DIR / "consola.ttf"
CONSOLAS_BOLD = FONT_DIR / "consolab.ttf"


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), int(size * S))


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def rgba(value, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(value, tuple):
        if len(value) == 4:
            return value
        r, g, b = value
        return (r, g, b, alpha)
    r, g, b = hex_rgb(value)
    return (r, g, b, alpha)


class Canvas:
    def __init__(self, bg: str = DARK) -> None:
        self.image = Image.new("RGB", (W * S, H * S), hex_rgb(bg))
        self.draw = ImageDraw.Draw(self.image)

    def layer(self) -> Image.Image:
        return Image.new("RGBA", self.image.size, (0, 0, 0, 0))

    def composite(self, layer: Image.Image) -> None:
        self.image = Image.alpha_composite(self.image.convert("RGBA"), layer).convert("RGB")
        self.draw = ImageDraw.Draw(self.image)

    def gradient(self, top: str, bottom: str) -> None:
        top_rgb = np.array(hex_rgb(top), dtype=np.float32)
        bottom_rgb = np.array(hex_rgb(bottom), dtype=np.float32)
        rows = np.linspace(0, 1, self.image.height, dtype=np.float32)[:, None, None]
        arr = top_rgb[None, None, :] * (1 - rows) + bottom_rgb[None, None, :] * rows
        arr = np.repeat(arr, self.image.width, axis=1)
        self.image = Image.fromarray(arr.astype(np.uint8), "RGB")
        self.draw = ImageDraw.Draw(self.image)

    def glow(self, x: int, y: int, rx: int, ry: int, color: str, alpha: int = 90) -> None:
        layer = self.layer()
        d = ImageDraw.Draw(layer)
        d.ellipse(
            [(x - rx) * S, (y - ry) * S, (x + rx) * S, (y + ry) * S],
            fill=rgba(color, alpha),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(120 * S))
        self.composite(layer)

    def noise(self, amount: int = 5) -> None:
        rng = np.random.default_rng(42)
        arr = np.array(self.image, dtype=np.int16)
        noise = rng.integers(-amount, amount + 1, arr.shape[:2], dtype=np.int16)
        arr = np.clip(arr + noise[:, :, None], 0, 255).astype(np.uint8)
        self.image = Image.fromarray(arr, "RGB")
        self.draw = ImageDraw.Draw(self.image)

    def grid(self, step: int = 72, alpha: int = 10) -> None:
        layer = self.layer()
        d = ImageDraw.Draw(layer)
        for x in range(0, W, step):
            d.line([(x * S, 0), (x * S, H * S)], fill=(255, 255, 255, alpha), width=1 * S)
        for y in range(0, H, step):
            d.line([(0, y * S), (W * S, y * S)], fill=(255, 255, 255, alpha), width=1 * S)
        self.composite(layer)

    def rect(self, box, fill=None, outline=None, width=1, radius=0) -> None:
        x0, y0, x1, y1 = [v * S for v in box]
        if radius:
            self.draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=radius * S,
                fill=rgba(fill) if fill else None,
                outline=rgba(outline) if outline else None,
                width=max(1, int(width * S)),
            )
        else:
            self.draw.rectangle(
                [x0, y0, x1, y1],
                fill=rgba(fill) if fill else None,
                outline=rgba(outline) if outline else None,
                width=max(1, int(width * S)),
            )

    def text(self, xy, text, f, fill, anchor="la", spacing=0) -> None:
        x, y = xy
        if spacing:
            self.tracked(x, y, text, f, fill, spacing)
            return
        self.draw.text((x * S, y * S), text, font=f, fill=rgba(fill) if len(fill) == 7 else fill, anchor=anchor)

    def tracked(self, x, y, text, f, fill, spacing) -> None:
        cursor = x
        for ch in text:
            self.draw.text((cursor * S, y * S), ch, font=f, fill=rgba(fill), anchor="ls")
            cursor += self.draw.textlength(ch, font=f) / S + spacing

    def line(self, points, fill, width=1, dash=None) -> None:
        scaled = [(x * S, y * S) for x, y in points]
        if dash:
            self.dashed(points, fill, width, dash)
        else:
            self.draw.line(scaled, fill=rgba(fill) if len(fill) == 7 else fill, width=max(1, int(width * S)))

    def dashed(self, points, fill, width, dash) -> None:
        dash, gap = dash
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            length = math.hypot(x1 - x0, y1 - y0)
            if length == 0:
                continue
            dx, dy = (x1 - x0) / length, (y1 - y0) / length
            t = 0.0
            while t < length:
                a = (x0 + dx * t, y0 + dy * t)
                b = (x0 + dx * min(t + dash, length), y0 + dy * min(t + dash, length))
                self.draw.line(
                    [(a[0] * S, a[1] * S), (b[0] * S, b[1] * S)],
                    fill=rgba(fill),
                    width=max(1, int(width * S)),
                )
                t += dash + gap

    def arrow(self, x0, y0, x1, y1, fill, width=2, head=10) -> None:
        self.line([(x0, y0), (x1, y1)], fill, width)
        angle = math.atan2(y1 - y0, x1 - x0)
        left = (x1 - head * math.cos(angle - math.pi / 6), y1 - head * math.sin(angle - math.pi / 6))
        right = (x1 - head * math.cos(angle + math.pi / 6), y1 - head * math.sin(angle + math.pi / 6))
        self.draw.polygon(
            [(x1 * S, y1 * S), (left[0] * S, left[1] * S), (right[0] * S, right[1] * S)],
            fill=rgba(fill),
        )

    def circle(self, x, y, r, fill=None, outline=None, width=1) -> None:
        self.draw.ellipse(
            [(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S],
            fill=rgba(fill) if fill else None,
            outline=rgba(outline) if outline else None,
            width=max(1, int(width * S)),
        )

    def pill(self, x, y, text, f, fg, bg, border, pad_x=18, pad_y=10) -> tuple[int, int]:
        bbox = self.draw.textbbox((0, 0), text, font=f)
        tw = (bbox[2] - bbox[0]) / S
        th = (bbox[3] - bbox[1]) / S
        w = tw + pad_x * 2
        h = th + pad_y * 2
        self.rect((x, y, x + w, y + h), fill=bg, outline=border, width=1, radius=h / 2)
        self.draw.text(
            ((x + pad_x) * S, (y + h / 2) * S),
            text,
            font=f,
            fill=rgba(fg),
            anchor="lm",
        )
        return int(w), int(h)

    def wordmark(self, x, y, color=CREAM, mark_color=TEAL) -> None:
        self.rect((x, y, x + 30, y + 30), fill=mark_color, radius=8)
        self.draw.line(
            [((x + 8) * S, (y + 16) * S), ((x + 14) * S, (y + 22) * S), ((x + 23) * S, (y + 10) * S)],
            fill=rgba("#FFFFFF"),
            width=3 * S,
            joint="curve",
        )
        self.tracked(x + 44, y + 24, "GROUNDTRUTH", font(SEGOE_BOLD, 22), color, 3.6)

    def save(self, name: str) -> None:
        out = self.image.resize((W, H), Image.LANCZOS)
        out.save(OUT / name, optimize=True)
        print("wrote", OUT / name)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=f) / S <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_paragraph(c: Canvas, x, y, text, f, fill, max_width, line_height) -> int:
    lines = wrap(c.draw, text, f, max_width)
    for i, line in enumerate(lines):
        c.text((x, y + i * line_height), line, f, fill)
    return y + len(lines) * line_height


def node(c: Canvas, x, y, r, color, label, sub=None, label_above=False) -> None:
    c.circle(x, y, r + 8, fill=rgba(color, 28), outline=None)
    c.circle(x, y, r, fill=color, outline=CREAM, width=1.5)
    f = font(CONSOLAS, 15)
    if label_above:
        c.text((x, y - r - 28), label, f, CREAM, anchor="ms")
        if sub:
            c.text((x, y - r - 10), sub, font(CONSOLAS, 11), MUTED, anchor="ms")
    else:
        c.text((x, y + r + 12), label, f, CREAM, anchor="ma")
        if sub:
            c.text((x, y + r + 32), sub, font(CONSOLAS, 11), MUTED, anchor="ma")


def hook_cards() -> None:
    # 01a: live in production
    c = Canvas(DARK)
    c.gradient("#1A1512", "#0F0D0C")
    c.glow(1500, 280, 620, 420, TEAL, 80)
    c.glow(300, 900, 500, 350, AMBER, 35)
    c.grid(80, 8)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 220), "01 / THE HOOK", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 300), "A Lambda is live", font(GEORGIA_BOLD, 104), CREAM)
    c.text((112, 424), "in production.", font(GEORGIA_BOLD, 104), CREAM)
    c.pill(116, 590, "LIVE  ·  ap-south-1", font(CONSOLAS, 18), "#052E2B", MINT, TEAL_LIGHT, 22, 12)
    c.text((116, 690), "arn:aws:lambda:ap-south-1:123456789012:function:orders-transformer", font(CONSOLAS, 19), MUTED)
    # Lambda node motif
    c.circle(1510, 520, 150, fill=rgba(TEAL, 20))
    c.circle(1510, 520, 106, fill=rgba(TEAL, 32), outline=TEAL_LIGHT, width=2)
    c.text((1510, 500), "lambda", font(CONSOLAS, 17), MINT, anchor="mm")
    c.text((1510, 548), "orders-transformer", font(CONSOLAS, 15), CREAM, anchor="mm")
    c.save("01a_hook_live.png")

    # 01b: not in the repo
    c = Canvas(DARK)
    c.gradient("#1A1512", "#0F0D0C")
    c.glow(1400, 720, 640, 420, RED, 55)
    c.grid(80, 8)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 220), "01 / THE HOOK", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 300), "It isn't in the", font(GEORGIA_BOLD, 104), CREAM)
    c.text((112, 424), "Terraform repo.", font(GEORGIA_BOLD, 104), CREAM)
    c.pill(116, 590, "NO EXACT MATCH", font(CONSOLAS_BOLD, 18), "#450A0A", "#FEE4E2", RED, 22, 12)
    c.text((116, 690), "state points somewhere else  ·  git history has no owner", font(CONSOLAS, 19), MUTED)
    # broken chain
    c.rect((1280, 380, 1660, 600), fill="#211B18", outline="#4A3F38", width=1, radius=16)
    c.text((1310, 410), "terraform/orders", font(CONSOLAS, 17), MUTED)
    c.text((1310, 448), "aws_lambda_function", font(CONSOLAS_BOLD, 22), CREAM)
    c.text((1310, 490), "not found", font(CONSOLAS, 17), RED_LIGHT)
    c.line([(1280, 520), (1660, 520)], "#4A3F38", 1)
    c.text((1310, 540), "last commit: unrelated", font(CONSOLAS, 15), MUTED)
    c.dashed([(1180, 500), (1260, 500)], RED_LIGHT, 2, (10, 8))
    c.line([(1090, 500), (1170, 500)], MUTED, 2, dash=(4, 10))
    c.circle(1268, 500, 7, fill=RED)
    c.save("01b_hook_repo.png")

    # 01c: nobody can tell you who owns it
    c = Canvas(DARK)
    c.gradient("#1A1512", "#0F0D0C")
    c.glow(1200, 760, 620, 420, RED, 65)
    c.grid(80, 8)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 220), "01 / THE HOOK", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 300), "And nobody can", font(GEORGIA_BOLD, 104), CREAM)
    c.text((112, 424), "tell you who", font(GEORGIA_BOLD, 104), CREAM)
    c.text((112, 548), "owns it.", font(GEORGIA_BOLD, 104), RED_LIGHT)
    # owner card
    c.rect((1180, 330, 1740, 700), fill="#211816", outline=RED, width=2, radius=18)
    c.text((1220, 370), "CURRENT OWNER", font(CONSOLAS_BOLD, 17), RED_LIGHT, spacing=2)
    c.text((1220, 430), "UNKNOWN", font(GEORGIA_BOLD, 78), CREAM)
    c.line([(1220, 540), (1700, 540)], "#4A2C28", 1)
    c.text((1220, 570), "No active Scalr binding.", font(SEGOE, 22), MUTED)
    c.text((1220, 606), "No exact ownership match.", font(SEGOE, 22), MUTED)
    c.text((1220, 642), "A change here is a guess.", font(SEGOE_SEMI, 22), RED_LIGHT)
    c.save("01c_hook_owner.png")


def title_card() -> None:
    c = Canvas(DARK)
    c.gradient("#191411", "#0D0B0A")
    c.glow(1520, 300, 700, 480, TEAL, 90)
    c.glow(350, 900, 550, 380, AMBER, 45)
    c.grid(80, 7)
    c.noise(4)
    c.wordmark(112, 74)

    # evidence graph motif
    graph_nodes = [
        ("lambda", 1450, 430, TEAL, "EV-001"),
        ("scalr workspace", 1720, 300, AMBER, "EV-004"),
        ("run", 1780, 520, PURPLE, "EV-006"),
        ("git commit", 1690, 740, BLUE, "EV-008"),
        ("cloudtrail", 1390, 790, RED, "EV-011"),
        ("state version", 1250, 590, "#8B5CF6", "EV-005"),
        ("evidence", 1540, 640, MINT, "EV-014"),
    ]
    edges = [(0, 1), (0, 2), (0, 5), (1, 4), (2, 3), (3, 6), (5, 6), (4, 6), (1, 5)]
    for a, b in edges:
        x0, y0 = graph_nodes[a][1], graph_nodes[a][2]
        x1, y1 = graph_nodes[b][1], graph_nodes[b][2]
        c.line([(x0, y0), (x1, y1)], "#5A4C42", 1.2, dash=(6, 8) if a in (1, 2) else None)
    for label, x, y, color, ev in graph_nodes:
        node(c, x, y, 11 if label != "lambda" else 17, color, label, ev)

    c.text((112, 300), "META GLOBAL AI DEVELOPER HACKATHON 2026", font(CONSOLAS_BOLD, 19), AMBER_LIGHT, spacing=2.2)
    c.text((112, 356), "Find the owner", font(GEORGIA_BOLD, 98), CREAM)
    c.text((112, 474), "before you touch it.", font(GEORGIA_BOLD, 98), CREAM)
    c.text((112, 640), "Resource lineage, with receipts.", font(GEORGIA_ITALIC, 42), MINT)
    draw_paragraph(
        c,
        112,
        710,
        "GroundTruth correlates AWS, Scalr, Git, CloudTrail, and CloudWatch evidence — then shows exactly where the evidence ends.",
        font(SEGOE, 25),
        "#CFC5B8",
        930,
        36,
    )
    x = 112
    for text in ["READ-ONLY", "DETERMINISTIC", "AUDITABLE"]:
        w, _ = c.pill(x, 850, text, font(CONSOLAS_BOLD, 16), MINT, "#122522", TEAL, 18, 10)
        x += w + 12
    c.pill(112, 940, "DEMO / FIXTURE DATA", font(CONSOLAS_BOLD, 18), "#3B2503", "#FEF3C7", AMBER_LIGHT, 20, 11)
    c.text((1808, 1028), "v1.0.0  ·  fixture-first  ·  local SQLite metadata", font(CONSOLAS, 15), MUTED, anchor="ra")
    c.save("00_title.png")


def problem_card() -> None:
    c = Canvas(DARK)
    c.gradient("#1A1512", "#0F0D0C")
    c.glow(300, 300, 500, 380, RED, 40)
    c.grid(80, 7)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 220), "02 / THE OWNERSHIP GAP", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 290), "Delete it.", font(GEORGIA_BOLD, 86), CREAM)
    c.line([(112, 386), (470, 386)], RED_LIGHT, 4)
    c.text((112, 410), "Re-import it.", font(GEORGIA_BOLD, 86), CREAM)
    c.line([(112, 506), (570, 506)], AMBER_LIGHT, 4)
    c.text((112, 530), "Change it.", font(GEORGIA_BOLD, 86), CREAM)
    c.line([(112, 626), (500, 626)], "#A78BFA", 4)
    c.text((112, 690), "What evidence exists —", font(GEORGIA_ITALIC, 44), MINT)
    c.text((112, 748), "and where does it end?", font(GEORGIA_ITALIC, 44), MINT)

    # broken evidence stack
    c.rect((1130, 210, 1800, 890), fill="#1F1A17", outline="#463A32", width=1, radius=20)
    c.text((1170, 246), "OWNERSHIP EVIDENCE", font(CONSOLAS_BOLD, 17), MUTED, spacing=2)
    rows = [
        ("AWS Lambda identity", "live · exact ARN", MINT, TEAL),
        ("Scalr resource usage", "no active binding", AMBER_LIGHT, AMBER),
        ("Git repository history", "candidate only", AMBER_LIGHT, AMBER),
        ("CloudTrail events", "90-day coverage gap", RED_LIGHT, RED),
        ("CloudWatch activity", "no ownership signal", MUTED, "#57534E"),
    ]
    y = 310
    for label, status, color, dot in rows:
        c.circle(1188, y + 22, 6, fill=dot)
        c.text((1210, y), label, font(SEGOE_SEMI, 22), CREAM)
        c.text((1210, y + 32), status, font(CONSOLAS, 16), color)
        c.line([(1170, y + 72), (1760, y + 72)], "#3B302A", 1)
        y += 96
    c.rect((1170, 790, 1760, 858), fill="#2A1512", outline=RED, width=1, radius=12)
    c.text((1194, 810), "CONCLUSION", font(CONSOLAS_BOLD, 15), RED_LIGHT, spacing=2)
    c.text((1194, 832), "Owner unknown  ·  adoption unsafe", font(SEGOE_SEMI, 20), CREAM)
    c.save("02_problem.png")


def underhood_card() -> None:
    c = Canvas(PAPER)
    c.gradient("#FBF9F4", "#F1ECE1")
    c.grid(80, 5)
    c.noise(3)
    c.wordmark(100, 64, INK, TEAL)
    c.text((100, 186), "09 / UNDER THE HOOD", font(CONSOLAS_BOLD, 17), TEAL, spacing=2)
    c.text((100, 232), "Eight read-only sources. One deterministic verdict.", font(GEORGIA_BOLD, 54), INK)
    c.text((100, 312), "The model never gets a vote on status, confidence, or ownership.", font(SEGOE, 24), MUTED)

    # Sources panel
    c.rect((100, 400, 690, 880), fill=PAPER_LIGHT, outline="#DED6C8", width=1, radius=18)
    c.text((130, 430), "READ-ONLY SOURCES", font(CONSOLAS_BOLD, 16), TEAL, spacing=2)
    sources = [
        ("AWS Lambda", TEAL),
        ("Scalr", AMBER),
        ("Git", BLUE),
        ("GitLab", BLUE),
        ("CloudTrail", RED),
        ("CloudWatch", "#0891B2"),
        ("CloudWatch Omni", PURPLE),
        ("Fixtures / MCP", "#57534E"),
    ]
    for i, (name, color) in enumerate(sources):
        col = i % 2
        row = i // 2
        x = 130 + col * 270
        y = 480 + row * 82
        c.rect((x, y, x + 250, y + 58), fill="#FFFFFF", outline="#E4DDD0", width=1, radius=10)
        c.circle(x + 22, y + 29, 5, fill=color)
        c.text((x + 40, y + 17), name, font(SEGOE_SEMI, 17), INK)
    c.text((130, 824), "8 connectors  ·  no apply, import, delete, or invoke", font(CONSOLAS, 14), MUTED)

    # Core panel
    c.rect((780, 400, 1250, 880), fill="#FFFFFF", outline=TEAL, width=2, radius=18)
    c.text((810, 430), "DETERMINISTIC CORE", font(CONSOLAS_BOLD, 16), TEAL, spacing=2)
    steps = [
        ("Exact identity", "ARN, account, region"),
        ("Match hierarchy", "exact > historical > candidate"),
        ("7 terminal statuses", "the engine owns the answer"),
        ("Coverage gaps", "missing data stays missing"),
    ]
    y = 486
    for i, (title, detail) in enumerate(steps):
        c.circle(820, y + 24, 14, fill=TEAL)
        c.text((820, y + 24), str(i + 1), font(CONSOLAS_BOLD, 14), "#FFFFFF", anchor="mm")
        c.text((850, y + 4), title, font(SEGOE_SEMI, 21), INK)
        c.text((850, y + 34), detail, font(CONSOLAS, 14), MUTED)
        if i < len(steps) - 1:
            c.line([(820, y + 42), (820, y + 82)], "#B9DED7", 2)
        y += 96

    # Receipts panel
    c.rect((1340, 400, 1820, 880), fill="#151210", outline="#151210", width=1, radius=18)
    c.text((1372, 430), "RECEIPTS", font(CONSOLAS_BOLD, 16), MINT, spacing=2)
    stats = [
        ("8", "read-only connectors"),
        ("7", "terminal statuses"),
        ("127", "tests passing"),
        ("0", "mutation tools"),
    ]
    y = 486
    for value, label in stats:
        c.text((1372, y), value, font(GEORGIA_BOLD, 50), CREAM)
        c.text((1500, y + 18), label, font(SEGOE, 19), "#CFC5B8")
        y += 86
    c.line([(1372, 806), (1788, 806)], "#4A3F38", 1)
    c.text((1372, 826), "JSON + Markdown", font(CONSOLAS, 16), MINT)
    c.text((1372, 850), "SHA-256 verified", font(CONSOLAS, 16), MINT)

    # Arrows
    c.arrow(700, 640, 770, 640, TEAL, 3, 11)
    c.text((735, 610), "exact IDs", font(CONSOLAS, 13), TEAL, anchor="mm")
    c.arrow(1260, 640, 1330, 640, TEAL, 3, 11)
    c.text((1295, 610), "bundle", font(CONSOLAS, 13), TEAL, anchor="mm")
    c.text(
        (100, 936),
        "No write path. Missing evidence is a coverage gap, not proof of absence.",
        font(SEGOE_SEMI, 22),
        RED,
    )
    c.save("05_underhood.png")


def guardrails_card() -> None:
    c = Canvas(DARK)
    c.gradient("#191411", "#0D0B0A")
    c.glow(900, 300, 650, 430, TEAL, 55)
    c.glow(1600, 800, 500, 350, PURPLE, 35)
    c.grid(80, 6)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 200), "06 / AI WITH A SEATBELT", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 246), "Muse Spark explains.", font(GEORGIA_BOLD, 72), CREAM)
    c.text((112, 326), "The engine decides.", font(GEORGIA_BOLD, 72), MINT)

    boxes = [
        (
            112,
            500,
            480,
            700,
            "SANITIZED EVIDENCE",
            "IDs, timestamps, match types",
            "no secrets, no tokens",
            TEAL_LIGHT,
            "#122522",
        ),
        (560, 500, 900, 700, "MUSE SPARK 1.3", "advisory narrative", "tool calls: 1", TEAL, "#0B2F2B"),
        (
            980,
            500,
            1330,
            700,
            "CITATION VALIDATOR",
            "every claim maps to",
            "a known evidence ID",
            AMBER_LIGHT,
            "#2B1B05",
        ),
        (1410, 500, 1800, 700, "ADVISORY OUTPUT", "explanation only", "status unchanged", CREAM, "#221D19"),
    ]
    for x0, y0, x1, y1, title, line1, line2, accent, fill in boxes:
        c.rect((x0, y0, x1, y1), fill=fill, outline=accent, width=1.5, radius=16)
        c.text((x0 + 24, y0 + 24), title, font(CONSOLAS_BOLD, 15), accent, spacing=1.5)
        c.text((x0 + 24, y0 + 66), line1, font(SEGOE_SEMI, 21), CREAM)
        c.text((x0 + 24, y0 + 98), line2, font(SEGOE, 18), "#BDB2A4")
    for x in (480, 900, 1330):
        c.arrow(x + 10, 600, x + 66, 600, "#8A7F70", 2.5, 10)

    # fallback branch
    c.line([(1155, 700), (1155, 790)], AMBER_LIGHT, 2, dash=(8, 7))
    c.arrow(1155, 790, 1155, 820, AMBER_LIGHT, 2, 9)
    c.rect((980, 820, 1330, 910), fill="#2B1B05", outline=AMBER, width=1, radius=14)
    c.text((1004, 838), "INVALID CITATION / MODEL FAILURE", font(CONSOLAS_BOLD, 14), AMBER_LIGHT, spacing=1.2)
    c.text((1004, 864), "deterministic fallback", font(SEGOE_SEMI, 20), CREAM)

    x = 112
    for text in ["CANNOT INVENT AN OWNER", "CANNOT CHANGE STATUS", "CANNOT AUTHORIZE A CHANGE"]:
        w, _ = c.pill(x, 830, text, font(CONSOLAS_BOLD, 14), "#FEE4E2", "#2A1512", RED, 16, 10)
        x += w + 10
    c.text(
        (112, 940),
        "Every factual claim cites an evidence ID.  The AI is advisory; the engine is authoritative.",
        font(SEGOE_SEMI, 24),
        MINT,
    )
    c.save("06_guardrails.png")


def receipts_card() -> None:
    c = Canvas(DARK)
    c.gradient("#191411", "#0D0B0A")
    c.glow(1500, 300, 600, 400, AMBER, 45)
    c.grid(80, 6)
    c.noise(4)
    c.wordmark(112, 74)
    c.text((112, 200), "09 / RECEIPTS, NOT VIBES", font(CONSOLAS_BOLD, 18), AMBER_LIGHT, spacing=2)
    c.text((112, 246), "A verdict you can attach", font(GEORGIA_BOLD, 70), CREAM)
    c.text((112, 326), "to a change request.", font(GEORGIA_BOLD, 70), CREAM)
    stats = [
        ("8", "read-only connectors"),
        ("7", "terminal statuses"),
        ("127", "tests passing"),
        ("0", "mutation tools"),
    ]
    x = 112
    for value, label in stats:
        c.rect((x, 480, x + 390, 700), fill="#211B18", outline="#4A3F38", width=1, radius=16)
        c.text((x + 28, 506), value, font(GEORGIA_BOLD, 92), MINT)
        c.text((x + 30, 626), label, font(SEGOE_SEMI, 20), "#CFC5B8")
        x += 420
    c.rect((112, 760, 1810, 920), fill="#211B18", outline="#4A3F38", width=1, radius=16)
    c.text((144, 786), "EVIDENCE BUNDLE", font(CONSOLAS_BOLD, 16), AMBER_LIGHT, spacing=2)
    c.text(
        (144, 824),
        "JSON  +  Markdown   ·   SHA-256 verified   ·   account IDs redacted by default",
        font(SEGOE_SEMI, 26),
        CREAM,
    )
    c.text((144, 872), "Attach to a change request, an incident review, or an audit.", font(SEGOE, 20), "#BDB2A4")
    c.save("07_receipts.png")


def end_card() -> None:
    c = Canvas(DARK)
    c.gradient("#191411", "#0B0908")
    c.glow(960, 480, 760, 480, TEAL, 55)
    c.grid(80, 6)
    c.noise(4)
    c.wordmark(112, 74)
    c.text(
        (960, 270), "READ-ONLY  ·  DETERMINISTIC  ·  AUDITABLE", font(CONSOLAS_BOLD, 18), MINT, anchor="ma", spacing=2.2
    )
    c.text((960, 340), "Find the owner", font(GEORGIA_BOLD, 96), CREAM, anchor="ma")
    c.text((960, 456), "before you touch it.", font(GEORGIA_BOLD, 96), CREAM, anchor="ma")
    c.text(
        (960, 620),
        "GroundTruth turns a scattered evidence hunt into a repeatable, auditable investigation.",
        font(SEGOE, 26),
        "#CFC5B8",
        anchor="ma",
    )
    x = 560
    for text in ["8 READ-ONLY CONNECTORS", "7 TERMINAL STATUSES", "127 TESTS"]:
        w, _ = c.pill(x, 700, text, font(CONSOLAS_BOLD, 15), MINT, "#122522", TEAL, 18, 10)
        x += w + 12
    c.pill(760, 800, "DEMO / FIXTURE DATA", font(CONSOLAS_BOLD, 18), "#3B2503", "#FEF3C7", AMBER_LIGHT, 20, 11)
    c.text(
        (960, 930),
        "Meta Global AI Developer Hackathon 2026  ·  GroundTruth v1.0.0",
        font(CONSOLAS, 17),
        MUTED,
        anchor="ma",
    )
    # faint graph
    pts = [(300, 850), (430, 760), (560, 820), (700, 720), (840, 780)]
    for i in range(len(pts) - 1):
        c.line([pts[i], pts[i + 1]], "#3A302A", 1, dash=(5, 9))
    for x, y in pts:
        c.circle(x, y, 5, fill="#3A302A")
    c.save("10_end_card.png")


def demo_chip() -> None:
    img = Image.new("RGBA", (360 * S, 58 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, 360 * S, 58 * S],
        radius=29 * S,
        fill=(20, 16, 14, 205),
        outline=rgba(AMBER_LIGHT),
        width=2 * S,
    )
    d.ellipse([20 * S, 24 * S, 30 * S, 34 * S], fill=rgba(AMBER_LIGHT))
    d.text((46 * S, 18 * S), "DEMO / FIXTURE DATA", font=font(CONSOLAS_BOLD, 18), fill=rgba(CREAM))
    img.resize((360, 58), Image.LANCZOS).save(OUT / "demo_chip.png")
    print("wrote", OUT / "demo_chip.png")


def stamp_blocked() -> None:
    w, h = 980, 300
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(
        [10 * S, 10 * S, (w - 10) * S, (h - 10) * S],
        radius=18 * S,
        fill=(120, 20, 14, 225),
        outline=rgba("#FFFFFF"),
        width=4 * S,
    )
    d.text((w / 2 * S, 96 * S), "ADOPTION BLOCKED", font=font(CONSOLAS_BOLD, 66), fill=rgba("#FFFFFF"), anchor="mm")
    d.text(
        (w / 2 * S, 182 * S),
        "TWO ACTIVE OWNERS  ·  NO WINNER PICKED",
        font=font(CONSOLAS_BOLD, 24),
        fill=rgba("#FFE4E1"),
        anchor="mm",
    )
    d.line([(80 * S, 228 * S), ((w - 80) * S, 228 * S)], fill=(255, 255, 255, 120), width=2 * S)
    d.text(
        (w / 2 * S, 258 * S),
        "GROUNDTRUTH  ·  DETERMINISTIC HARD STOP",
        font=font(CONSOLAS, 18),
        fill=rgba("#FFE4E1"),
        anchor="mm",
    )
    rotated = layer.rotate(-5, expand=True, resample=Image.BICUBIC)
    rotated = rotated.resize((rotated.width // S, rotated.height // S), Image.LANCZOS)
    rotated.save(OUT / "stamp_blocked.png")
    print("wrote", OUT / "stamp_blocked.png")


def callout_chips() -> None:
    specs = [
        ("exact_match", "EXACT ARN MATCH", MINT, "#122522", TEAL),
        ("inferred", "INFERRED / CANDIDATE", "#FEF3C7", "#3B2503", AMBER),
        ("coverage_gap", "COVERAGE GAP ≠ ABSENCE", "#FEE4E2", "#450A0A", RED),
        ("advisory", "ADVISORY ONLY", "#EDE9FE", "#2E1065", PURPLE),
        ("verified", "SHA-256 VERIFIED", MINT, "#122522", TEAL),
        ("readonly", "READ-ONLY", "#E0F2FE", "#082F49", "#0891B2"),
    ]
    for name, text, fg, bg, border in specs:
        f = font(CONSOLAS_BOLD, 18)
        tmp = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=f)
        w = int((bbox[2] - bbox[0]) / S) + 44
        h = 54
        img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [0, 0, w * S, h * S], radius=(h / 2) * S, fill=rgba(bg, 235), outline=rgba(border), width=2 * S
        )
        d.text((22 * S, (h / 2) * S), text, font=f, fill=rgba(fg), anchor="lm")
        img.resize((w, h), Image.LANCZOS).save(OUT / f"callout_{name}.png")
        print("wrote", OUT / f"callout_{name}.png")


def main() -> None:
    hook_cards()
    title_card()
    problem_card()
    underhood_card()
    guardrails_card()
    receipts_card()
    end_card()
    demo_chip()
    stamp_blocked()
    callout_chips()


if __name__ == "__main__":
    main()
