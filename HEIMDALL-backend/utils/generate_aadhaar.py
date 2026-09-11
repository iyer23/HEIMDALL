"""
Generate realistic-looking DUMMY Aadhaar card images for demo purposes.
These are clearly labeled SPECIMEN/DEMO cards — NOT real government documents.

Run: python utils/generate_aadhaar.py
Outputs: demo_docs/aadhaar_valid.png  and  demo_docs/aadhaar_tampered.png
"""
import os, math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("Pillow not found. Installing...")
    os.system("python -m pip install pillow")
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = Path(__file__).parent.parent / "demo_docs"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Colour palette matching real Aadhaar card ─────────────────────────────────
BG_WHITE       = (255, 255, 255)
UIDAI_ORANGE   = (255, 103, 31)   # #FF671F — official UIDAI saffron-orange
UIDAI_BLUE     = (0, 56, 168)     # #0038A8 — Ashoka-blue accent
DARK_TEXT      = (30, 30, 30)
MUTED_TEXT     = (100, 100, 100)
LIGHT_GREY     = (240, 240, 240)
BORDER_GREY    = (200, 200, 200)
DEMO_WATERMARK = (220, 60, 60)    # red stamp for SPECIMEN

W, H = 856, 540   # standard credit-card-ish aspect at 96 dpi


def _get_font(size: int, bold: bool = False):
    """Try system fonts; fall back to PIL default."""
    candidates = [
        "C:/Windows/Fonts/arial.ttf"          if not bold else "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibri.ttf"         if not bold else "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/segoeui.ttf"         if not bold else "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_qr_placeholder(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color=(30,30,30)):
    """Draw a simple QR-code-like grid placeholder."""
    cell = size // 10
    import random
    rng = random.Random(42)
    for row in range(10):
        for col in range(10):
            if rng.random() > 0.45:
                cx = x + col * cell
                cy = y + row * cell
                draw.rectangle([cx, cy, cx + cell - 1, cy + cell - 1], fill=color)
    # Corner position markers
    for corner_x, corner_y in [(x, y), (x + size - 3*cell, y), (x, y + size - 3*cell)]:
        draw.rectangle([corner_x, corner_y, corner_x + 3*cell, corner_y + 3*cell], outline=color, width=2)
        draw.rectangle([corner_x+cell, corner_y+cell, corner_x+2*cell, corner_y+2*cell], fill=color)


def _draw_photo_placeholder(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, tampered: bool = False):
    """Draw a person silhouette placeholder in the photo box."""
    draw.rectangle([x, y, x+w, y+h], fill=LIGHT_GREY, outline=BORDER_GREY, width=1)
    # Head
    head_r = w // 5
    hx = x + w // 2
    hy = y + int(h * 0.32)
    draw.ellipse([hx - head_r, hy - head_r, hx + head_r, hy + head_r],
                 fill=(190, 190, 190))
    # Body
    draw.ellipse([hx - w//3, hy + head_r + 2, hx + w//3, y + h + w//3],
                 fill=(190, 190, 190))
    if tampered:
        # Red X overlay to indicate photo swap
        draw.line([x+4, y+4, x+w-4, y+h-4], fill=(220, 50, 50), width=3)
        draw.line([x+w-4, y+4, x+4, y+h-4], fill=(220, 50, 50), width=3)
        draw.rectangle([x, y, x+w, y+h], outline=(220, 50, 50), width=2)


def _draw_fingerprint(draw: ImageDraw.ImageDraw, x: int, y: int, r: int):
    """Draw concentric arc lines resembling a fingerprint."""
    for i in range(1, r, 5):
        bb = [x - i, y - i, x + i, y + i]
        draw.arc(bb, start=200, end=520, fill=(180, 180, 180), width=1)


def _watermark(img: Image.Image, text: str):
    """Stamp diagonal SPECIMEN watermark."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    font = _get_font(72, bold=True)
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # Rotate and centre
    txt_img = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text((10, 10), text, font=font, fill=(220, 60, 60, 60))
    txt_rot = txt_img.rotate(30, expand=True)
    cx = (img.width - txt_rot.width) // 2
    cy = (img.height - txt_rot.height) // 2
    overlay.paste(txt_rot, (cx, cy), txt_rot)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ── Main card builder ─────────────────────────────────────────────────────────

def build_aadhaar(
    name: str,
    dob: str,
    gender: str,
    aadhaar_masked: str,
    vid: str,
    address: str,
    tampered: bool = False,
) -> Image.Image:
    img   = Image.new("RGB", (W, H), BG_WHITE)
    draw  = ImageDraw.Draw(img)

    # ── Background subtle grid ────────────────────────────────────────────────
    for gx in range(0, W, 20):
        draw.line([(gx, 0), (gx, H)], fill=(245, 245, 245), width=1)
    for gy in range(0, H, 20):
        draw.line([(0, gy), (W, gy)], fill=(245, 245, 245), width=1)

    # ── Top header bar ────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 80], fill=UIDAI_ORANGE)
    # Ashoka chakra placeholder (blue circle with spokes)
    cx_chakra, cy_chakra = 46, 40
    draw.ellipse([cx_chakra-24, cy_chakra-24, cx_chakra+24, cy_chakra+24],
                 outline=UIDAI_BLUE, width=3)
    draw.ellipse([cx_chakra-5, cy_chakra-5, cx_chakra+5, cy_chakra+5],
                 fill=UIDAI_BLUE)
    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x1 = cx_chakra + int(5 * math.cos(rad))
        y1 = cy_chakra + int(5 * math.sin(rad))
        x2 = cx_chakra + int(22 * math.cos(rad))
        y2 = cy_chakra + int(22 * math.sin(rad))
        draw.line([(x1, y1), (x2, y2)], fill=UIDAI_BLUE, width=1)

    # Header title — Hindi + English
    f_header_hi = _get_font(18, bold=True)
    f_header_en = _get_font(15, bold=True)
    f_sub       = _get_font(10)
    draw.text((80, 8),  "भारत सरकार / Government of India", font=f_header_hi, fill=BG_WHITE)
    draw.text((80, 34), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA (UIDAI)", font=f_header_en, fill=BG_WHITE)
    draw.text((80, 56), "Aadhaar — आधार", font=f_sub, fill=(255, 230, 210))

    # ── Left section: photo + fingerprint ────────────────────────────────────
    photo_x, photo_y, photo_w, photo_h = 24, 100, 130, 160
    _draw_photo_placeholder(draw, photo_x, photo_y, photo_w, photo_h, tampered=tampered)
    # Fingerprint below photo
    _draw_fingerprint(draw, photo_x + photo_w//2, photo_y + photo_h + 30, 20)
    f_tiny = _get_font(8)
    draw.text((photo_x + 8, photo_y + photo_h + 52), "Biometric", font=f_tiny, fill=MUTED_TEXT)

    # ── Middle section: personal details ─────────────────────────────────────
    mid_x = 175
    f_label   = _get_font(9)
    f_value   = _get_font(13, bold=True)
    f_value_s = _get_font(11, bold=True)

    fields = [
        ("Name / नाम",           name),
        ("Date of Birth / जन्म तिथि", dob),
        ("Gender / लिंग",        gender),
        ("Address / पता",        address),
    ]
    y_cursor = 105
    for label, value in fields:
        draw.text((mid_x, y_cursor), label, font=f_label, fill=MUTED_TEXT)
        # Wrap address
        if label.startswith("Address") and len(value) > 40:
            line1 = value[:42]
            line2 = value[42:]
            draw.text((mid_x, y_cursor + 13), line1, font=_get_font(11, bold=True), fill=DARK_TEXT)
            draw.text((mid_x, y_cursor + 26), line2, font=_get_font(10), fill=DARK_TEXT)
            y_cursor += 50
        else:
            draw.text((mid_x, y_cursor + 13), value, font=f_value_s, fill=DARK_TEXT)
            y_cursor += 38

    # ── Aadhaar number bar ────────────────────────────────────────────────────
    bar_y = H - 110
    draw.rectangle([0, bar_y, W, bar_y + 2], fill=UIDAI_ORANGE)
    draw.rectangle([0, bar_y + 2, W, H - 55], fill=(250, 248, 245))

    f_aadhaar_lbl = _get_font(10)
    f_aadhaar_num = _get_font(26, bold=True)
    draw.text((24, bar_y + 8), "Aadhaar Number / आधार संख्या", font=f_aadhaar_lbl, fill=MUTED_TEXT)

    # Highlight tampered number in red
    num_color = (200, 30, 30) if tampered else UIDAI_BLUE
    draw.text((24, bar_y + 22), aadhaar_masked, font=f_aadhaar_num, fill=num_color)

    # VID
    f_vid = _get_font(9)
    draw.text((24, bar_y + 56), f"VID: {vid}", font=f_vid, fill=MUTED_TEXT)

    # ── QR Code (right side) ─────────────────────────────────────────────────
    qr_x = W - 155
    qr_y = 95
    qr_s = 130
    draw.rectangle([qr_x - 4, qr_y - 4, qr_x + qr_s + 4, qr_y + qr_s + 4],
                   fill=BG_WHITE, outline=BORDER_GREY, width=1)
    qr_color = (180, 30, 30) if tampered else (30, 30, 30)
    _draw_qr_placeholder(draw, qr_x, qr_y, qr_s, color=qr_color)
    draw.text((qr_x + 18, qr_y + qr_s + 6), "Scan QR / QR स्कैन करें", font=_get_font(8), fill=MUTED_TEXT)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    draw.rectangle([0, H - 52, W, H], fill=UIDAI_BLUE)
    draw.text((12, H - 44), "uidai.gov.in  |  1947  |  help@uidai.gov.in", font=_get_font(10), fill=(180, 200, 255))
    draw.text((12, H - 26), "This Aadhaar is issued by UIDAI on behalf of the Government of India",
              font=_get_font(9), fill=(150, 175, 220))

    # ── Outer border ─────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W - 1, H - 1], outline=UIDAI_ORANGE, width=3)

    # ── SPECIMEN watermark ────────────────────────────────────────────────────
    img = _watermark(img, "SPECIMEN")

    # ── Tampered card: add visible red warning band ───────────────────────────
    if tampered:
        draw2 = ImageDraw.Draw(img)
        draw2.rectangle([0, 80, W, 98], fill=(200, 30, 30))
        draw2.text((W//2 - 120, 82),
                   "⚠  DEMO — SIMULATED TAMPERED DOCUMENT  ⚠",
                   font=_get_font(11, bold=True), fill=BG_WHITE)

    return img


# ── Generate both cards ───────────────────────────────────────────────────────

def main():
    print("Generating dummy Aadhaar card images...")

    # Valid Aadhaar
    valid_card = build_aadhaar(
        name            = "Arjun Mehta",
        dob             = "14/08/1998",
        gender          = "MALE",
        aadhaar_masked  = "XXXX  XXXX  4821",
        vid             = "9876 5432 1098 7654",
        address         = "12, MG Road, Pune, Maharashtra - 411001",
        tampered        = False,
    )
    valid_path = OUTPUT_DIR / "aadhaar_valid.png"
    valid_card.save(valid_path, "PNG", dpi=(150, 150))
    print(f"  ✅ Saved: {valid_path}")

    # Tampered Aadhaar
    tampered_card = build_aadhaar(
        name            = "Suresh Kumar",
        dob             = "01/01/2000",
        gender          = "MALE",
        aadhaar_masked  = "XXXX  XXXX  0001",
        vid             = "NOT DETECTED",
        address         = "Unknown Address, Delhi",
        tampered        = True,
    )
    tampered_path = OUTPUT_DIR / "aadhaar_tampered.png"
    tampered_card.save(tampered_path, "PNG", dpi=(150, 150))
    print(f"  ✅ Saved: {tampered_path}")

    print("\nDone! Images saved to demo_docs/")
    print("NOTE: These are SPECIMEN cards for demonstration only.")


if __name__ == "__main__":
    main()
