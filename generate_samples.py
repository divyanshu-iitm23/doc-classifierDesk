import os
import random
import string
import argparse

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from engine.validators import verhoeff_generate

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "samples")
def fake_aadhaar():
    body = str(random.randint(2, 9))
    body += "".join(random.choice("0123456789") for _ in range(10))
    check_digit = verhoeff_generate(body)
    return body + check_digit         # + Verhoeff check digit

def fake_pan():
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    holder = random.choice("PCHFAT")                        # valid holder type
    return L(3) + holder + L(1) + f"{random.randint(0,9999):04d}" + L(1)

def fake_voter():
    L = lambda n: "".join(random.choice(string.ascii_uppercase) for _ in range(n))
    return L(3) + "".join(str(random.randint(0, 9)) for _ in range(7))

def fake_dl():
    states = ["MH", "DL", "KA", "TN", "UP", "GJ", "RJ", "WB"]
    state = random.choice(states)
    rto = f"{random.randint(1,99):02d}"
    year = str(random.randint(1995, 2024))
    serial = f"{random.randint(0, 9999999):07d}"
    return f"{state}{rto}{year}{serial}"                    # 2 letters + 13 digits

def fake_passport():
    first = random.choice("ABCDEFGHJKLMNPRSTUVWY")           # excludes Q, X, Z
    return random.choice([first + "".join(str(random.randint(0, 9)) for _ in range(7)),first + first + "".join(str(random.randint(0, 9)) for _ in range(6)),])


def doc_layouts():
    aadhaar = fake_aadhaar()
    pan = fake_pan()
    voter = fake_voter()
    dl = fake_dl()
    passport = fake_passport()

    return {
        "aadhaar_card": [
            "Government of India",
            "Unique Identification Authority of India (UIDAI)",
            "",
            "Name: Test Subject (SAMPLE)",
            "DOB: 01/01/1990    Gender: M",
            "",
            f"{aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}",
            "VID: 9100 0000 0000 0000",
            "मेरा आधार, मेरी पहचान",
            "*** SYNTHETIC TEST DOCUMENT — NOT A REAL AADHAAR ***",
        ],
        "pan_card": [
            "INCOME TAX DEPARTMENT          GOVT. OF INDIA",
            "Permanent Account Number Card",
            "",
            "Name: TEST SUBJECT (SAMPLE)",
            "Father's Name: TEST FATHER",
            "Date of Birth: 01/01/1990",
            "",
            f"{pan}",
            "*** SYNTHETIC TEST DOCUMENT — NOT A REAL PAN ***",
        ],
        "voter_id": [
            "Election Commission of India",
            "Elector Photo Identity Card (EPIC)",
            "",
            "Elector's Name: Test Subject (SAMPLE)",
            "Father's Name: Test Father",
            "Sex: M    Age as on 01.01.2024: 34",
            "",
            f"{voter}",
            "*** SYNTHETIC TEST DOCUMENT — NOT A REAL VOTER ID ***",
        ],
        "driving_licence": [
            "INDIA — UNION OF INDIA",
            "Transport Department",
            "DRIVING LICENCE",
            "",
            "Name: TEST SUBJECT (SAMPLE)",
            "DOB: 01-01-1990    BG: O+",
            "Valid Till (NT): 31-12-2030",
            "",
            f"{dl[:2]}{dl[2:4]} {dl[4:]}",
            "*** SYNTHETIC TEST DOCUMENT — NOT A REAL DL ***",
        ],
        "passport": [
            "REPUBLIC OF INDIA",
            "PASSPORT",
            "Type: P    Country Code: IND",
            "",
            "Surname: SUBJECT (SAMPLE)",
            "Given Name: TEST",
            "Nationality: INDIAN",
            "Place of Issue: MUMBAI",
            "",
            f"{passport}",
            "*** SYNTHETIC TEST DOCUMENT — NOT A REAL PASSPORT ***",
        ],
    }
def write_digital_pdf(path, lines):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica", 13)
    y = 270 * mm
    for line in lines:
        c.drawString(25 * mm, y, line)
        y -= 9 * mm
    c.showPage()
    c.save()


def write_scanned_pdf(path, lines):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1240, 1754  # ~150 dpi A4
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    y = 120
    for line in lines:
        draw.text((90, y), line, fill="black", font=font)
        y += 60
    img.save(path, "PDF", resolution=150.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scanned", action="store_true",
                    help="also generate image-only (OCR-path) PDFs")
    args = ap.parse_args()

    os.makedirs(SAMPLE_DIR, exist_ok=True)
    layouts = doc_layouts()

    for name, lines in layouts.items():
        digital_path = os.path.join(SAMPLE_DIR, f"{name}.pdf")
        write_digital_pdf(digital_path, lines)
        print(f"  wrote {digital_path}")
        if args.scanned:
            scanned_path = os.path.join(SAMPLE_DIR, f"{name}_scanned.pdf")
            write_scanned_pdf(scanned_path, lines)
            print(f"  wrote {scanned_path}  (image-only, forces OCR)")

    decoy = [
        "STATE BANK — ACCOUNT STATEMENT",
        "Branch: Andheri East",
        "",
        "Account Holder: Test Subject",
        "Account Number: 3021 4455 6789",   
        "IFSC: SBIN0001234",
        "Statement period: 01-04-2026 to 30-04-2026",
    ]
    decoy_path = os.path.join(SAMPLE_DIR, "decoy_bank_statement.pdf")
    write_digital_pdf(decoy_path, decoy)
    print(f"  wrote {decoy_path}  (decoy — should be UNKNOWN)")

    print(f"\nDone. Samples in: {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
