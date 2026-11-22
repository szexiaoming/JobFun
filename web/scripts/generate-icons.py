"""Generate deterministic PWA PNG icons from the JobFun code-native mark."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT_CANDIDATES = (Path("C:/Windows/Fonts/arialbd.ttf"), "DejaVuSans-Bold.ttf")


def font_for(size: int):
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def create_icon(size: int) -> None:
    image = Image.new("RGB", (size, size), "#0b1530")
    draw = ImageDraw.Draw(image)
    inset = round(size * 0.18)
    radius = round(size * 0.16)
    draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=radius,
        fill="#48d7b5",
    )
    font = font_for(round(size * 0.27))
    draw.text(
        (size / 2, size / 2),
        "JF",
        font=font,
        fill="#0b1530",
        anchor="mm",
        stroke_width=max(1, size // 256),
    )
    image.save(ROOT / "public" / f"icon-{size}.png", optimize=True)


for dimension in (192, 512):
    create_icon(dimension)
