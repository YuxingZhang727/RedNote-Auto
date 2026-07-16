import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"

CANVAS_SIZE = (900, 1200)  # 3:4, XHS's common image-note ratio
PADDING = 80
BG_COLOR = (253, 249, 240)
TITLE_COLOR = (30, 30, 30)
ACCENT_COLOR = (220, 140, 90)

TITLE_FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
TITLE_FONT_SIZE = 72
LINE_HEIGHT = 92

# The CJK system font used here has no emoji glyphs (PIL also can't render
# Apple's color emoji), so they'd otherwise draw as tofu boxes. Strip them only
# for the rendered card — the actual post text sent to XHS keeps its emoji.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"  # variation selector-16 (emoji presentation)
    "\U000020E3"  # combining enclosing keycap (used in 1️⃣ 2️⃣ ...)
    "]+"
)


def _strip_emoji(text):
    return _EMOJI_PATTERN.sub("", text)


def _wrap_to_width(draw, text, font, max_width):
    lines = []
    line = ""
    for ch in text:
        if ch == "\n":
            lines.append(line)
            line = ""
            continue
        candidate = line + ch
        if draw.textlength(candidate, font=font) > max_width and line:
            lines.append(line)
            line = ch
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def generate_text_card(title, out_dir_name):
    """Render a title-only card (no body text) as a fallback cover image when
    no real photos are available (e.g. synthesized/multi-source drafts).
    Returns [path]."""
    img = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)
    max_width = CANVAS_SIZE[0] - 2 * PADDING

    title_font = ImageFont.truetype(TITLE_FONT_PATH, TITLE_FONT_SIZE)
    lines = _wrap_to_width(draw, _strip_emoji(title).strip(), title_font, max_width)

    block_height = len(lines) * LINE_HEIGHT
    accent_gap = 56
    top = (CANVAS_SIZE[1] - block_height - accent_gap) / 2

    accent_width = 90
    draw.rectangle(
        [
            (CANVAS_SIZE[0] - accent_width) / 2,
            top,
            (CANVAS_SIZE[0] + accent_width) / 2,
            top + 8,
        ],
        fill=ACCENT_COLOR,
    )

    y = top + accent_gap
    for line in lines:
        line_width = draw.textlength(line, font=title_font)
        x = (CANVAS_SIZE[0] - line_width) / 2
        draw.text((x, y), line, font=title_font, fill=TITLE_COLOR)
        y += LINE_HEIGHT

    out_dir = DRAFTS_DIR / str(out_dir_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "0.jpg"
    img.save(out_path, "JPEG", quality=92)
    return [str(out_path)]
