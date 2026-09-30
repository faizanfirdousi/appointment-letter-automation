#!/usr/bin/env python3
"""
scripts/create_sample_letterhead.py
Creates a simple placeholder letterhead PNG (A4, 2480x3508 px) so you can
test the pipeline without designing one first.

Usage:
    python scripts/create_sample_letterhead.py

Requires: Pillow  (pip install Pillow)
"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow is not installed.")
    print("Run:  pip install Pillow")
    raise SystemExit(1)

# A4 at 300 DPI
W, H = 2480, 3508

HEADER_H    = 500   # px
FOOTER_H    = 280   # px
SIDE_BORDER = 60    # px

AWS_DARK  = (35,  47,  62)   # #232F3E  — AWS dark navy
AWS_ORG   = (255, 153,  0)   # #FF9900  — AWS orange
WHITE     = (255, 255, 255)
LIGHT_GREY= (240, 240, 240)

def make_letterhead(out_path: Path) -> None:
    img  = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    # ── Header background ──────────────────────────────────────────────────
    draw.rectangle([(0, 0), (W, HEADER_H)], fill=AWS_DARK)

    # Club name in header (large text)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
        font_tiny  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    except OSError:
        font_large = font_small = font_tiny = ImageFont.load_default()

    draw.text((SIDE_BORDER + 30, 140), "AWS Student Builder Group", fill=WHITE, font=font_large)
    draw.text((SIDE_BORDER + 32, 290), "Indira Institute of Information Technology (I²IT)", fill=(200, 200, 200), font=font_small)

    # Orange accent line below header
    draw.rectangle([(0, HEADER_H), (W, HEADER_H + 12)], fill=AWS_ORG)

    # ── Sidebar border lines ────────────────────────────────────────────────
    draw.rectangle([(0, HEADER_H + 12), (8, H - FOOTER_H)], fill=AWS_ORG)
    draw.rectangle([(W - 8, HEADER_H + 12), (W, H - FOOTER_H)], fill=AWS_ORG)

    # ── Footer ──────────────────────────────────────────────────────────────
    # Orange line above footer
    draw.rectangle([(0, H - FOOTER_H), (W, H - FOOTER_H + 12)], fill=AWS_ORG)
    draw.rectangle([(0, H - FOOTER_H + 12), (W, H)], fill=AWS_DARK)

    footer_y = H - FOOTER_H + 60
    draw.text((SIDE_BORDER + 30, footer_y),
              "AWS Student Builder Group  |  I²IT Pune",
              fill=(200, 200, 200), font=font_tiny)

    # ── Signature area ───────────────────────────────────────────────────────
    sig_x  = W // 2 - 300
    sig_y  = H - FOOTER_H - 280

    # Signature line
    draw.rectangle([(sig_x, sig_y + 130), (sig_x + 600, sig_y + 136)], fill=AWS_DARK)
    draw.text((sig_x, sig_y + 145), "Authorized Signatory", fill=AWS_DARK, font=font_small)
    draw.text((sig_x, sig_y + 215), "AWS Student Builder Group Leader", fill=(100,100,100), font=font_tiny)

    # Simulated signature scrawl
    for i in range(30):
        import math
        x1 = sig_x + i * 20
        y1 = sig_y + 80 + int(20 * math.sin(i * 0.6))
        x2 = x1 + 18
        y2 = sig_y + 80 + int(20 * math.sin((i + 1) * 0.6))
        draw.line([(x1, y1), (x2, y2)], fill=AWS_DARK, width=5)

    # ── Save ────────────────────────────────────────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", dpi=(300, 300))
    print(f"✓ Letterhead saved to: {out_path}  ({W}x{H} px)")


if __name__ == "__main__":
    make_letterhead(Path("assets/letterhead.png"))
