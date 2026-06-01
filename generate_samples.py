"""
generate_samples.py
-------------------
Creates SYNTHETIC test documents so the engine can be exercised without any real
personal data.

Two tiers:
  --simple   : clean text-only PDFs (the original fixtures; fast sanity check)
  (default)  : REALISTIC card images that mimic real documents - coloured bands,
               a logo blob, a face-photo box, a guilloche-style background
               pattern, scan noise, and a few degrees of rotation. Rendered as
               image-only PDFs so they force the full OCR + preprocessing path.

All identifiers are randomly generated test fixtures with valid structure (and a
valid Verhoeff check digit for Aadhaar) purely so the validation path can run.
They are NOT real documents and must not be presented as anyone's identity.

Usage:
    python generate_samples.py             # realistic card-like PDFs -> samples/
    python generate_samples.py --simple    # clean text-only PDFs (original set)
    python generate_samples.py --all        # both
"""

import os
import random
import string
import argparse
import math

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from engine.validators import verhoeff_generate

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "samples")


# -----------------------------------------------------------------------------
# synthetic-but-valid-structure identifiers
# -----------------------------------------------------------------------------
def fake_aadhaar():
    first = str(random.randint(2, 9))
    body = first + "".join(str(random.randint(0, 9)) for _ in range(10))
    return body + verhoeff_generate(body)

def fake_pan():
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    return L(3) + random.choice("PCHFAT") + L(1) + f"{random.randint(0,9999):04d}" + L(1)

def fake_voter():
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    return L(3) + "".join(str(random.randint(0, 9)) for _ in range(7))

def fake_dl():
    state = random.choice(["MH", "DL", "KA", "TN", "UP", "GJ", "RJ", "WB"])
    return f"{state}{random.randint(1,99):02d}{random.randint(1995,2024)}{random.randint(0,9999999):07d}"

def fake_passport():
    first = random.choice("ABCDEFGHJKLMNPRSTUVWY")
    return first + "".join(str(random.randint(0, 9)) for _ in range(7))


# bank identifiers
_BANK_CODES = ["SBIN", "HDFC", "ICIC", "BARB", "PUNB", "UBIN", "CNRB", "KKBK", "UTIB", "IDIB"]
_BANK_NAMES = {
    "SBIN": "STATE BANK OF INDIA", "HDFC": "HDFC BANK", "ICIC": "ICICI BANK",
    "BARB": "BANK OF BARODA", "PUNB": "PUNJAB NATIONAL BANK", "UBIN": "UNION BANK OF INDIA",
    "CNRB": "CANARA BANK", "KKBK": "KOTAK MAHINDRA BANK", "UTIB": "AXIS BANK",
    "IDIB": "INDIAN BANK",
}

def fake_ifsc():
    bank = random.choice(_BANK_CODES)
    branch = f"{random.randint(0, 999999):06d}"
    return bank, f"{bank}0{branch}"     # 4 letters + 0 + 6 chars

def fake_account_no():
    return "".join(str(random.randint(0, 9)) for _ in range(random.choice([11, 12, 14, 16])))

def fake_micr():
    return "".join(str(random.randint(0, 9)) for _ in range(9))


# -----------------------------------------------------------------------------
# fonts
# -----------------------------------------------------------------------------
def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# -----------------------------------------------------------------------------
# background "security" pattern (guilloche-ish) + scan noise
# -----------------------------------------------------------------------------
def _draw_guilloche(draw, w, h, colour, density=40):
    """Faint overlapping sine curves, like the anti-copy pattern on real cards."""
    for k in range(density):
        pts = []
        phase = k * 0.5
        amp = 12 + (k % 5) * 4
        for x in range(0, w, 6):
            y = int(h / 2 + amp * math.sin(x / 28.0 + phase) + (k - density / 2) * (h / density))
            pts.append((x, y))
        if len(pts) > 1:
            draw.line(pts, fill=colour, width=1)

def _add_scan_noise(img, amount=0.06):
    """Sprinkle salt-and-pepper-ish noise + a slight blur to mimic a real scan."""
    px = img.load()
    w, h = img.size
    n = int(w * h * amount * 0.15)
    for _ in range(n):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        v = random.choice([(0, 0, 0), (255, 255, 255), (180, 180, 180)])
        px[x, y] = v
    return img.filter(ImageFilter.GaussianBlur(0.4))


# -----------------------------------------------------------------------------
# realistic card renderer
# -----------------------------------------------------------------------------
def _render_card(spec):
    """spec: dict with bands(list of (colour, frac)), title lines, fields, number_line,
    logo_colour, photo. Returns a PIL image of a card-like document."""
    W, H = 1000, 640
    img = Image.new("RGB", (W, H), spec.get("bg", (250, 250, 248)))
    draw = ImageDraw.Draw(img)

    # coloured top/bottom bands (Aadhaar-style)
    y = 0
    for colour, frac in spec.get("bands", []):
        bh = int(H * frac)
        draw.rectangle([0, y, W, y + bh], fill=colour)
        y += bh

    # faint guilloche pattern across the middle
    _draw_guilloche(draw, W, H, spec.get("pattern_colour", (225, 225, 235)),
                    density=46)

    # logo blob (emblem stand-in) top-left
    lc = spec.get("logo_colour", (120, 90, 40))
    draw.ellipse([34, 24, 96, 86], fill=lc)
    draw.ellipse([50, 40, 80, 70], fill=spec.get("bg", (250, 250, 248)))

    # face-photo box (bottom-left), with a head/shoulders silhouette
    px0, py0, px1, py1 = 40, 360, 250, 600
    draw.rectangle([px0, py0, px1, py1], fill=(210, 214, 220), outline=(90, 90, 90), width=3)
    cx = (px0 + px1) // 2
    draw.ellipse([cx - 42, py0 + 35, cx + 42, py0 + 119], fill=(150, 156, 165))   # head
    draw.ellipse([cx - 78, py0 + 130, cx + 78, py1 + 40], fill=(150, 156, 165))   # shoulders

    # title lines (top)
    ty = 30
    for i, line in enumerate(spec["title"]):
        f = _font(34 if i == 0 else 24, bold=(i == 0))
        draw.text((120, ty), line, fill=spec.get("title_colour", (20, 20, 20)), font=f)
        ty += (44 if i == 0 else 32)

    # fields (right of the photo)
    fy = 360
    for label, value in spec["fields"]:
        draw.text((290, fy), f"{label}: {value}", fill=(15, 15, 15), font=_font(26))
        fy += 40

    # the all-important number line - rendered in a heavier font, like real cards
    draw.text((290, fy + 14), spec["number_line"], fill=(0, 0, 0), font=_font(40, bold=True))

    # tiny disclaimer
    draw.text((40, H - 26), spec["disclaimer"], fill=(120, 30, 30), font=_font(16))

    # rotate a few degrees to test deskew, then add scan noise
    angle = spec.get("rotate", 0)
    if angle:
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)
    img = _add_scan_noise(img, amount=spec.get("noise", 0.05))
    return img


def realistic_specs():
    a = fake_aadhaar(); p = fake_pan(); v = fake_voter(); d = fake_dl(); pp = fake_passport()
    return {
        "aadhaar_card": {
            "bg": (252, 250, 244),
            "bands": [((232, 116, 58), 0.10)],     # orange top band
            "pattern_colour": (243, 221, 205),
            "logo_colour": (200, 70, 40),
            "title": ["Government of India",
                      "Unique Identification Authority of India"],
            "title_colour": (120, 40, 20),
            "fields": [("Name", "Test Subject (SAMPLE)"),
                       ("DOB", "01/01/1990"), ("Gender", "Male")],
            "number_line": f"{a[:4]} {a[4:8]} {a[8:]}",
            "disclaimer": "*** SYNTHETIC TEST - NOT A REAL AADHAAR ***",
            "rotate": 1.5, "noise": 0.05,
        },
        "pan_card": {
            "bg": (224, 234, 246),                 # bluish PAN card
            "bands": [((52, 92, 156), 0.08)],
            "pattern_colour": (205, 217, 235),
            "logo_colour": (40, 70, 130),
            "title": ["INCOME TAX DEPARTMENT", "GOVT. OF INDIA"],
            "title_colour": (25, 45, 95),
            "fields": [("Name", "TEST SUBJECT (SAMPLE)"),
                       ("Father", "TEST FATHER"), ("DOB", "01/01/1990")],
            "number_line": f"PAN: {p}",
            "disclaimer": "*** SYNTHETIC TEST - NOT A REAL PAN ***",
            "rotate": -2.0, "noise": 0.06,
        },
        "voter_id": {
            "bg": (245, 248, 240),
            "bands": [((86, 142, 70), 0.09)],      # green band
            "pattern_colour": (214, 230, 210),
            "logo_colour": (60, 110, 50),
            "title": ["Election Commission of India",
                      "Elector Photo Identity Card"],
            "title_colour": (35, 80, 30),
            "fields": [("Elector", "Test Subject (SAMPLE)"),
                       ("Father", "Test Father"), ("Sex", "M")],
            "number_line": f"EPIC: {v}",
            "disclaimer": "*** SYNTHETIC TEST - NOT A REAL VOTER ID ***",
            "rotate": 1.0, "noise": 0.05,
        },
        "driving_licence": {
            "bg": (244, 240, 250),
            "bands": [((110, 70, 150), 0.10)],     # purple band
            "pattern_colour": (224, 214, 236),
            "logo_colour": (90, 55, 130),
            "title": ["UNION OF INDIA", "DRIVING LICENCE"],
            "title_colour": (70, 40, 110),
            "fields": [("Name", "TEST SUBJECT (SAMPLE)"),
                       ("DOB", "01-01-1990"), ("Valid", "31-12-2030")],
            "number_line": f"DL No: {d[:2]}{d[2:4]} {d[4:]}",
            "disclaimer": "*** SYNTHETIC TEST - NOT A REAL DL ***",
            "rotate": -1.2, "noise": 0.06,
        },
        "passport": {
            "bg": (236, 226, 222),                 # passport beige/maroon
            "bands": [((110, 30, 40), 0.12)],
            "pattern_colour": (220, 205, 200),
            "logo_colour": (90, 25, 30),
            "title": ["REPUBLIC OF INDIA", "PASSPORT"],
            "title_colour": (90, 25, 30),
            "fields": [("Surname", "SUBJECT (SAMPLE)"), ("Given Name", "TEST"),
                       ("Type", "P  Code: IND")],
            "number_line": f"Passport No: {pp}",
            "disclaimer": "*** SYNTHETIC TEST - NOT A REAL PASSPORT ***",
            "rotate": 2.2, "noise": 0.05,
        },
    }


# -----------------------------------------------------------------------------
# simple text layouts (original fixtures)
# -----------------------------------------------------------------------------
def simple_layouts():
    a = fake_aadhaar(); p = fake_pan(); v = fake_voter(); d = fake_dl(); pp = fake_passport()
    return {
        "aadhaar_card": ["Government of India",
                         "Unique Identification Authority of India (UIDAI)", "",
                         "Name: Test Subject (SAMPLE)", "DOB: 01/01/1990  Gender: M", "",
                         f"Aadhaar No: {a[:4]} {a[4:8]} {a[8:]}", "VID: 9100 0000 0000 0000",
                         "*** SYNTHETIC TEST DOCUMENT - NOT A REAL AADHAAR ***"],
        "pan_card": ["INCOME TAX DEPARTMENT      GOVT. OF INDIA",
                     "Permanent Account Number Card", "",
                     "Name: TEST SUBJECT (SAMPLE)", "Date of Birth: 01/01/1990", "",
                     f"Permanent Account Number: {p}",
                     "*** SYNTHETIC TEST DOCUMENT - NOT A REAL PAN ***"],
        "voter_id": ["Election Commission of India",
                     "Elector Photo Identity Card (EPIC)", "",
                     "Elector's Name: Test Subject (SAMPLE)", "Sex: M", "",
                     f"EPIC No: {v}", "*** SYNTHETIC TEST DOCUMENT - NOT A REAL VOTER ID ***"],
        "driving_licence": ["Transport Department", "DRIVING LICENCE", "",
                            "Name: TEST SUBJECT (SAMPLE)", "DOB: 01-01-1990", "",
                            f"DL No: {d[:2]}{d[2:4]} {d[4:]}",
                            "*** SYNTHETIC TEST DOCUMENT - NOT A REAL DL ***"],
        "passport": ["REPUBLIC OF INDIA", "PASSPORT", "Type: P  Country Code: IND", "",
                     "Surname: SUBJECT (SAMPLE)", "Given Name: TEST", "",
                     f"Passport No: {pp}",
                     "*** SYNTHETIC TEST DOCUMENT - NOT A REAL PASSPORT ***"],
    }


# -----------------------------------------------------------------------------
# realistic bank document renderer (full page, not a card)
# -----------------------------------------------------------------------------
def _render_bank_document(kind):
    """Render a full-page bank document image. kind = 'statement' or 'passbook'."""
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), (252, 252, 250))
    draw = ImageDraw.Draw(img)

    bank_code, ifsc = fake_ifsc()
    bank_name = _BANK_NAMES[bank_code]
    acct = fake_account_no()
    micr = fake_micr()

    # header band + logo blob
    draw.rectangle([0, 0, W, 110], fill=(30, 60, 120))
    draw.ellipse([34, 28, 90, 84], fill=(255, 255, 255))
    draw.ellipse([48, 42, 76, 70], fill=(30, 60, 120))
    draw.text((110, 30), bank_name, fill=(255, 255, 255), font=_font(34, bold=True))
    draw.text((110, 74), "Internet Banking", fill=(220, 225, 235), font=_font(18))

    if kind == "statement":
        draw.text((40, 140), "Statement of Account", fill=(20, 20, 20), font=_font(30, bold=True))
        rows = [
            ("Account Holder", "TEST SUBJECT (SAMPLE)"),
            ("Account Number", acct),
            ("IFSC Code", ifsc),
            ("MICR Code", micr),
            ("Branch", "Andheri East, Mumbai"),
            ("Statement Period", "01-04-2026 to 30-04-2026"),
            ("Opening Balance", "Rs. 45,200.00"),
        ]
        y = 200
        for label, value in rows:
            draw.text((40, y), f"{label}:", fill=(80, 80, 80), font=_font(22))
            draw.text((340, y), value, fill=(10, 10, 10), font=_font(22, bold=True))
            y += 38
        y += 20
        draw.rectangle([40, y, W - 40, y + 40], fill=(225, 230, 240))
        for tx, label in zip([50, 200, 470, 630, 810],
                             ["Date", "Narration", "Debit", "Credit", "Balance"]):
            draw.text((tx, y + 9), label, fill=(20, 20, 20), font=_font(20, bold=True))
        y += 50
        txns = [
            ("03-04-2026", "UPI/Payment/Grocery", "1,200.00", "", "44,000.00"),
            ("08-04-2026", "ATM Withdrawal", "5,000.00", "", "39,000.00"),
            ("12-04-2026", "Salary Credit", "", "85,000.00", "1,24,000.00"),
            ("20-04-2026", "NEFT/Rent", "18,000.00", "", "1,06,000.00"),
            ("28-04-2026", "Interest Credit", "", "320.00", "1,06,320.00"),
        ]
        for d, n, dr, cr, bal in txns:
            draw.text((50, y), d, fill=(20, 20, 20), font=_font(18))
            draw.text((200, y), n, fill=(20, 20, 20), font=_font(18))
            draw.text((470, y), dr, fill=(150, 30, 30), font=_font(18))
            draw.text((630, y), cr, fill=(30, 120, 30), font=_font(18))
            draw.text((810, y), bal, fill=(20, 20, 20), font=_font(18))
            y += 34
        y += 12
        draw.text((40, y), "Closing Balance: Rs. 1,06,320.00", fill=(10, 10, 10), font=_font(22, bold=True))
        y += 34
        draw.text((40, y), "Available Balance: Rs. 1,06,320.00", fill=(10, 10, 10), font=_font(20))
        disclaimer = "*** SYNTHETIC TEST - NOT A REAL BANK STATEMENT ***"

    else:  # passbook
        draw.text((40, 140), "PASSBOOK", fill=(20, 20, 20), font=_font(30, bold=True))
        draw.text((40, 182), "Savings Bank Account", fill=(60, 60, 60), font=_font(22))
        rows = [
            ("Customer ID", str(random.randint(10000000, 99999999))),
            ("Account Holder", "TEST SUBJECT (SAMPLE)"),
            ("Account Number", acct),
            ("Account Type", "SAVINGS BANK ACCOUNT"),
            ("IFSC Code", ifsc),
            ("MICR Code", micr),
            ("Branch Name", "Andheri West, Mumbai"),
            ("Branch Code", str(random.randint(1000, 9999))),
            ("Nominee", "Registered"),
            ("Mode of Operation", "Single"),
            ("Date of Issue", "15-03-2026"),
        ]
        y = 240
        for label, value in rows:
            draw.text((60, y), f"{label}:", fill=(80, 80, 80), font=_font(24))
            draw.text((430, y), value, fill=(10, 10, 10), font=_font(24, bold=True))
            y += 46
        disclaimer = "*** SYNTHETIC TEST - NOT A REAL PASSBOOK ***"

    draw.text((40, H - 34), disclaimer, fill=(120, 30, 30), font=_font(16))
    img = _add_scan_noise(img, amount=0.03)
    return img


def _render_cheque():
    """Render a realistic bank cheque (wide, short) with the distinctive markers:
    payee line, amount box, A/C payee, validity notice, and the MICR band."""
    W, H = 1300, 560
    img = Image.new("RGB", (W, H), (236, 240, 233))   # pale green cheque tint
    draw = ImageDraw.Draw(img)
    _draw_guilloche(draw, W, H, (214, 224, 212), density=30)

    bank_code, ifsc = fake_ifsc()
    bank_name = _BANK_NAMES[bank_code]
    acct = fake_account_no()
    micr = fake_micr()
    cheque_no = str(random.randint(100000, 999999))

    # top-right validity notice (this survives OCR best)
    draw.text((W - 360, 24), "VALID FOR THREE MONTHS ONLY", fill=(90, 90, 90), font=_font(18, bold=True))
    # A/C payee crossing (top-left diagonal box)
    draw.text((40, 30), "A/C PAYEE", fill=(60, 60, 60), font=_font(18, bold=True))
    draw.line([30, 24, 150, 70], fill=(60, 60, 60), width=2)
    draw.line([60, 24, 180, 70], fill=(60, 60, 60), width=2)

    draw.text((200, 26), bank_name, fill=(20, 40, 90), font=_font(32, bold=True))
    draw.text((200, 70), "MAYUR VIHAR BRANCH, ACHARYA NIKETAN", fill=(50, 50, 50), font=_font(18))

    # date box (DD MM YYYY template)
    draw.text((W - 330, 70), "D D M M Y Y Y Y", fill=(40, 40, 40), font=_font(22, bold=True))

    # payee line
    draw.text((40, 150), "Pay", fill=(20, 20, 20), font=_font(24))
    draw.line([110, 178, W - 320, 178], fill=(120, 120, 120), width=1)
    draw.text((130, 150), "TEST SUBJECT (SAMPLE)", fill=(10, 10, 10), font=_font(22))
    draw.text((W - 300, 150), "OR ORDER", fill=(20, 20, 20), font=_font(22, bold=True))

    # rupees line + amount box
    draw.text((40, 220), "Rupees", fill=(20, 20, 20), font=_font(24))
    draw.line([150, 248, W - 360, 248], fill=(120, 120, 120), width=1)
    draw.text((170, 220), "One Lakh Six Thousand Only", fill=(10, 10, 10), font=_font(22))
    draw.rectangle([W - 330, 210, W - 40, 262], outline=(40, 40, 40), width=2)
    draw.text((W - 320, 222), "Rs. 1,06,320.00", fill=(10, 10, 10), font=_font(22, bold=True))

    draw.text((40, 300), "PAYABLE AT PAR AT ALL BRANCHES", fill=(70, 70, 70), font=_font(18))
    draw.text((40, 330), f"NEFT IFS CODE {ifsc}", fill=(40, 40, 40), font=_font(20, bold=True))
    draw.text((40, 362), f"A/C No: {acct}", fill=(40, 40, 40), font=_font(20))

    # account-holder name + signature area (bottom-right)
    draw.text((W - 360, 400), "MIKROZ INFOSECURITY PVT LTD", fill=(20, 20, 20), font=_font(18, bold=True))
    draw.text((W - 300, 440), "Authorised Signatory", fill=(60, 60, 60), font=_font(16))

    # MICR band along the very bottom (the white strip with the special font)
    draw.rectangle([0, H - 70, W, H - 20], fill=(248, 248, 245))
    micr_band = f"⑈ {cheque_no} ⑈  {micr} ⑆  {acct} ⑆  31"
    draw.text((60, H - 60), micr_band, fill=(15, 15, 15), font=_font(26, bold=True))

    draw.text((40, H - 16), "*** SYNTHETIC TEST - NOT A REAL CHEQUE ***", fill=(120, 30, 30), font=_font(14))
    img = _add_scan_noise(img, amount=0.03)
    return img


# -----------------------------------------------------------------------------
# writers
# -----------------------------------------------------------------------------
def write_text_pdf(path, lines):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica", 13)
    y = 270 * mm
    for line in lines:
        c.drawString(25 * mm, y, line)
        y -= 9 * mm
    c.showPage(); c.save()

def write_image_pdf(path, pil_img):
    pil_img.convert("RGB").save(path, "PDF", resolution=200.0)


# -----------------------------------------------------------------------------
# receipt-class document renderers (full page, force OCR)
# -----------------------------------------------------------------------------
def _fake_gstin():
    state = random.choice(["27", "07", "29", "33", "06", "19", "24"])
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    pan = L(5) + f"{random.randint(0,9999):04d}" + L(1)
    return f"{state}{pan}{random.randint(1,9)}Z{random.randint(0,9)}"

def _fake_vehicle_reg():
    state = random.choice(["MH", "DL", "KA", "TN", "UP", "GJ", "RJ", "WB"])
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    return f"{state}{random.randint(1,99):02d}{L(random.choice([1,2]))}{random.randint(1000,9999)}"

def _render_invoice():
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), (253, 253, 251))
    draw = ImageDraw.Draw(img)
    gstin = _fake_gstin()
    draw.rectangle([0, 0, W, 90], fill=(40, 60, 100))
    draw.text((40, 26), "TAX INVOICE", fill=(255, 255, 255), font=_font(36, bold=True))
    draw.text((40, 110), "ABC Traders Pvt Ltd", fill=(20, 20, 20), font=_font(26, bold=True))
    rows = [
        ("GSTIN", gstin), ("Invoice No", f"INV-2026-{random.randint(1000,9999)}"),
        ("Invoice Date", "12-04-2026"), ("Place of Supply", "Maharashtra (27)"),
        ("Bill To", "XYZ Industries Pvt Ltd"),
    ]
    y = 156
    for label, value in rows:
        draw.text((40, y), f"{label}:", fill=(80, 80, 80), font=_font(22))
        draw.text((300, y), value, fill=(10, 10, 10), font=_font(22, bold=True))
        y += 36
    y += 20
    draw.rectangle([40, y, W - 40, y + 40], fill=(225, 230, 240))
    for tx, label in zip([50, 330, 520, 660, 820], ["HSN", "Description", "Qty", "Unit Price", "Amount"]):
        draw.text((tx, y + 9), label, fill=(20, 20, 20), font=_font(20, bold=True))
    y += 50
    for hsn, desc, qty, rate, amt in [("8471", "Laptop Computer", "2", "45,000.00", "90,000.00"),
                                      ("8523", "Software License", "5", "2,000.00", "10,000.00")]:
        draw.text((50, y), hsn, fill=(20, 20, 20), font=_font(18))
        draw.text((330, y), desc, fill=(20, 20, 20), font=_font(18))
        draw.text((520, y), qty, fill=(20, 20, 20), font=_font(18))
        draw.text((660, y), rate, fill=(20, 20, 20), font=_font(18))
        draw.text((820, y), amt, fill=(20, 20, 20), font=_font(18))
        y += 34
    y += 20
    for label, value in [("Taxable Value", "1,00,000.00"), ("CGST 9%", "9,000.00"),
                         ("SGST 9%", "9,000.00"), ("Grand Total", "1,18,000.00")]:
        draw.text((600, y), f"{label}:", fill=(40, 40, 40), font=_font(20, bold=(label == "Grand Total")))
        draw.text((830, y), value, fill=(10, 10, 10), font=_font(20, bold=(label == "Grand Total")))
        y += 34
    draw.text((40, y + 20), "Amount in words: One Lakh Eighteen Thousand Rupees Only", fill=(60, 60, 60), font=_font(18))
    draw.text((40, H - 34), "*** SYNTHETIC TEST - NOT A REAL INVOICE ***", fill=(120, 30, 30), font=_font(16))
    return _add_scan_noise(img, amount=0.03)

def _render_insurance():
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), (250, 252, 253))
    draw = ImageDraw.Draw(img)
    _draw_guilloche(draw, W, H, (225, 232, 238), density=36)
    draw.rectangle([0, 0, W, 100], fill=(20, 90, 80))
    draw.text((40, 30), "STAR HEALTH INSURANCE", fill=(255, 255, 255), font=_font(30, bold=True))
    draw.text((40, 130), "Premium Receipt", fill=(20, 20, 20), font=_font(30, bold=True))
    rows = [
        ("Policy No", f"SH/2026/{random.randint(100000,999999)}"),
        ("Policyholder", "TEST SUBJECT (SAMPLE)"),
        ("Policy Period", "01-04-2026 to 31-03-2027"),
        ("Sum Insured", "Rs. 5,00,000"),
        ("Premium Paid", "Rs. 12,450"),
        ("Mode", "Annual"),
        ("Nominee", "Registered"),
        ("IRDAI Registration No.", "129"),
    ]
    y = 200
    for label, value in rows:
        draw.text((60, y), f"{label}:", fill=(80, 80, 80), font=_font(24))
        draw.text((460, y), value, fill=(10, 10, 10), font=_font(24, bold=True))
        y += 48
    draw.text((60, y + 30), "This is a health insurance premium payment receipt.", fill=(60, 60, 60), font=_font(20))
    draw.text((60, y + 60), "Coverage subject to policy terms. Renewal due before expiry.", fill=(60, 60, 60), font=_font(20))
    draw.text((40, H - 34), "*** SYNTHETIC TEST - NOT A REAL INSURANCE RECEIPT ***", fill=(120, 30, 30), font=_font(16))
    return _add_scan_noise(img, amount=0.03)

def _render_road_tax():
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), (252, 251, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 100], fill=(90, 70, 30))
    draw.text((40, 18), "GOVERNMENT OF MAHARASHTRA", fill=(255, 255, 255), font=_font(26, bold=True))
    draw.text((40, 56), "Transport Department", fill=(235, 230, 220), font=_font(20))
    draw.text((40, 130), "Motor Vehicle Tax Receipt", fill=(20, 20, 20), font=_font(30, bold=True))
    rows = [
        ("Registration Number", _fake_vehicle_reg()),
        ("Owner Name", "TEST SUBJECT (SAMPLE)"),
        ("Vehicle Class", "Motor Car (LMV)"),
        ("Chassis No", "MA3FHEB1S00" + f"{random.randint(100000,999999)}"),
        ("Engine Number", "K12M" + f"{random.randint(1000000,9999999)}"),
        ("RTO", "MH12 - Pune"),
        ("Road Tax Paid", "Rs. 9,600"),
        ("Tax Type", "One Time Tax (Lifetime)"),
        ("Validity", "11-04-2041"),
    ]
    y = 200
    for label, value in rows:
        draw.text((60, y), f"{label}:", fill=(80, 80, 80), font=_font(24))
        draw.text((470, y), value, fill=(10, 10, 10), font=_font(24, bold=True))
        y += 48
    draw.text((60, y + 30), "Road tax received against the above motor vehicle.", fill=(60, 60, 60), font=_font(20))
    draw.text((40, H - 34), "*** SYNTHETIC TEST - NOT A REAL ROAD TAX RECEIPT ***", fill=(120, 30, 30), font=_font(16))
    return _add_scan_noise(img, amount=0.03)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simple", action="store_true", help="clean text-only PDFs (original set)")
    ap.add_argument("--all", action="store_true", help="generate both realistic and simple")
    args = ap.parse_args()

    os.makedirs(SAMPLE_DIR, exist_ok=True)
    make_realistic = args.all or not args.simple
    make_simple = args.all or args.simple

    if make_realistic:
        print("Realistic card-like documents (force OCR + preprocessing):")
        for name, spec in realistic_specs().items():
            img = _render_card(spec)
            path = os.path.join(SAMPLE_DIR, f"{name}.pdf")
            write_image_pdf(path, img)
            print(f"  wrote {path}")

        print("Realistic bank documents (full-page, force OCR):")
        for kind, fname in [("statement", "bank_statement"), ("passbook", "bank_passbook")]:
            img = _render_bank_document(kind)
            path = os.path.join(SAMPLE_DIR, f"{fname}.pdf")
            write_image_pdf(path, img)
            print(f"  wrote {path}")
        cheque_img = _render_cheque()
        cheque_path = os.path.join(SAMPLE_DIR, "cheque.pdf")
        write_image_pdf(cheque_path, cheque_img)
        print(f"  wrote {cheque_path}")

        print("Realistic receipt documents (full-page, force OCR):")
        for renderer, fname in [(_render_invoice, "invoice"),
                                (_render_insurance, "insurance_receipt"),
                                (_render_road_tax, "road_tax_receipt")]:
            path = os.path.join(SAMPLE_DIR, f"{fname}.pdf")
            write_image_pdf(path, renderer())
            print(f"  wrote {path}")

    if make_simple:
        print("Simple text-only documents:")
        for name, lines in simple_layouts().items():
            path = os.path.join(SAMPLE_DIR, f"{name}_simple.pdf")
            write_text_pdf(path, lines)
            print(f"  wrote {path}")

    # decoy: a document that is NONE of the supported types (an electricity bill).
    # It should classify as UNKNOWN - proving the engine doesn't force every
    # document into one of its known buckets.
    decoy = ["MAHARASHTRA STATE ELECTRICITY DISTRIBUTION CO. LTD.",
             "ELECTRICITY BILL", "", "Consumer Name: Test Subject",
             "Consumer Number: 1234567890", "Billing Period: Apr 2026",
             "Units Consumed: 250", "Amount Due: Rs. 1,820.00",
             "Due Date: 15-05-2026"]
    decoy_path = os.path.join(SAMPLE_DIR, "decoy_electricity_bill.pdf")
    write_text_pdf(decoy_path, decoy)
    print(f"\n  wrote {decoy_path}  (decoy - should be UNKNOWN)")
    print(f"\nDone. Samples in: {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
