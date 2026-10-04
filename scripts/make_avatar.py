"""Generate docs/avatar.png: a gradient tile with a calendar-and-graduation-cap style icon.

Usage:  python scripts/make_avatar.py [output.png]      (requires: pip install pillow)

The picture is drawn at 2x and downsampled for smooth edges. Telegram crops bot photos to a
circle, so everything important stays inside the central ~80% of the square.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 1024
SCALE = 2
S = SIZE * SCALE

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def gradient() -> Image.Image:
    """Diagonal indigo -> violet -> cyan gradient."""
    stops = [(0.0, (67, 56, 202)), (0.55, (124, 58, 237)), (1.0, (6, 182, 212))]
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / 510
            for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
                if t <= t1:
                    px[x, y] = lerp(c0, c1, (t - t0) / (t1 - t0))
                    break
    return small.resize((S, S), Image.Resampling.BICUBIC)


def rounded(draw: ImageDraw.ImageDraw, box, radius, **kwargs) -> None:
    draw.rounded_rectangle(box, radius=radius, **kwargs)


def build() -> Image.Image:
    img = gradient().convert("RGBA")

    # soft glow blobs for depth
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-S * 0.2, -S * 0.25, S * 0.6, S * 0.45), fill=(255, 255, 255, 60))
    gd.ellipse((S * 0.55, S * 0.65, S * 1.2, S * 1.25), fill=(255, 255, 255, 40))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(S * 0.06)))

    # calendar geometry (in 2x pixels)
    left, top, right, bottom = int(S * 0.20), int(S * 0.27), int(S * 0.80), int(S * 0.80)
    radius = int(S * 0.07)

    # drop shadow
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    rounded(
        sd,
        (left, top + int(S * 0.025), right, bottom + int(S * 0.025)),
        radius,
        fill=(20, 10, 70, 150),
    )
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(S * 0.025)))

    d = ImageDraw.Draw(img)
    # page
    rounded(d, (left, top, right, bottom), radius, fill=(255, 255, 255, 255))
    # header band (rounded top, square bottom)
    header_h = int(S * 0.15)
    band = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    rounded(bd, (left, top, right, top + header_h + radius), radius, fill=(244, 63, 94, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rectangle((left, top, right, top + header_h), fill=255)
    img.paste(band, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # binder rings
    for cx in (left + (right - left) * 0.28, left + (right - left) * 0.72):
        r = int(S * 0.018)
        rounded(
            d,
            (cx - r, top - int(S * 0.045), cx + r, top + int(S * 0.055)),
            r,
            fill=(255, 255, 255, 255),
            outline=(76, 29, 149, 255),
            width=int(S * 0.006),
        )

    # month label in the header
    label = "ЗАНЯТИЯ"
    f = font(int(S * 0.06))
    box = d.textbbox((0, 0), label, font=f)
    d.text(
        (
            (left + right) / 2 - (box[2] - box[0]) / 2 - box[0],
            top + header_h / 2 - (box[3] - box[1]) / 2 - box[1],
        ),
        label,
        font=f,
        fill=(255, 255, 255, 255),
    )

    # grid of days: 5 columns x 3 rows, one highlighted
    pad = int(S * 0.055)
    gx0, gx1 = left + pad, right - pad
    gy0, gy1 = top + header_h + int(S * 0.045), bottom - pad
    cols, rows = 5, 3
    gap = int(S * 0.018)
    cw = (gx1 - gx0 - gap * (cols - 1)) / cols
    ch = (gy1 - gy0 - gap * (rows - 1)) / rows
    highlight = (1, 2)  # row, col
    for row in range(rows):
        for col in range(cols):
            x0 = gx0 + col * (cw + gap)
            y0 = gy0 + row * (ch + gap)
            box = (x0, y0, x0 + cw, y0 + ch)
            if (row, col) == highlight:
                rounded(d, box, int(S * 0.02), fill=(124, 58, 237, 255))
                num = font(int(ch * 0.62))
                tb = d.textbbox((0, 0), "5", font=num)
                d.text(
                    (
                        x0 + cw / 2 - (tb[2] - tb[0]) / 2 - tb[0],
                        y0 + ch / 2 - (tb[3] - tb[1]) / 2 - tb[1],
                    ),
                    "5",
                    font=num,
                    fill=(255, 255, 255, 255),
                )
            else:
                tone = (237, 233, 254, 255) if (row + col) % 2 == 0 else (224, 242, 254, 255)
                rounded(d, box, int(S * 0.02), fill=tone)

    # clock badge (bottom-right) for "reminders"
    cx, cy, r = int(S * 0.78), int(S * 0.78), int(S * 0.115)
    badge_shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(badge_shadow).ellipse(
        (cx - r, cy - r + 14, cx + r, cy + r + 14), fill=(20, 10, 70, 140)
    )
    img = Image.alpha_composite(img, badge_shadow.filter(ImageFilter.GaussianBlur(S * 0.015)))
    d = ImageDraw.Draw(img)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(250, 204, 21, 255))
    d.ellipse(
        (cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82), fill=(255, 255, 255, 255)
    )
    hand = int(S * 0.012)
    d.line((cx, cy, cx, cy - r * 0.55), fill=(76, 29, 149, 255), width=hand)
    d.line((cx, cy, cx + r * 0.38, cy + r * 0.12), fill=(244, 63, 94, 255), width=hand)
    d.ellipse((cx - hand, cy - hand, cx + hand, cy + hand), fill=(76, 29, 149, 255))

    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS).convert("RGB")


def main() -> None:
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).parent.parent / "docs" / "avatar.png"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    build().save(out, optimize=True)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
