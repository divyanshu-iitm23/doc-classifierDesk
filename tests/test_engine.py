"""
test_engine.py
--------------
Unit tests covering the validators and the text classifier.
Run:  python -m pytest tests/ -v     (or)     python tests/test_engine.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import classify_text
from engine.validators import (
    verhoeff_validate, verhoeff_generate,
    validate_aadhaar, validate_pan, validate_voter, validate_dl, validate_passport,
)


# ---------------------------------------------------------------- Verhoeff
def test_verhoeff_roundtrip():
    body = "23456789012"            # 11 digits
    check = verhoeff_generate(body)
    full = body + check
    assert verhoeff_validate(full), "generated check digit should validate"

def test_verhoeff_rejects_corruption():
    body = "23456789012"
    full = body + verhoeff_generate(body)
    # flip a digit -> should fail
    bad = ("0" if full[0] != "0" else "9") + full[1:]
    assert not verhoeff_validate(bad)


# ---------------------------------------------------------------- validators
def test_aadhaar_valid():
    body = "29876543210"
    full = body + verhoeff_generate(body)
    ok, _ = validate_aadhaar(full)
    assert ok

def test_aadhaar_rejects_leading_zero():
    body = "09876543210"
    full = body + verhoeff_generate(body)
    ok, _ = validate_aadhaar(full)
    assert not ok

def test_pan_structure():
    assert validate_pan("ABCPK1234L")[0]      # P = individual, valid
    assert not validate_pan("ABCXK1234L")[0]  # X not a valid holder type
    assert not validate_pan("AB1PK1234L")[0]  # digits in letter zone

def test_voter_structure():
    assert validate_voter("ABC1234567")[0]
    assert not validate_voter("AB12345678")[0]

def test_dl_structure():
    assert validate_dl("MH1220110012345")[0]      # MH + 13 digits
    assert validate_dl("123456789012345")[0]       # pure 15-digit form
    assert not validate_dl("ZZ1220110012345")[0]   # ZZ not a valid state code

def test_passport_structure():
    assert validate_passport("A1234567")[0]
    assert not validate_passport("Q1234567")[0]   # Q excluded
    assert not validate_passport("AA123456")[0]


# ---------------------------------------------------------------- classifier
def _aadhaar_number():
    body = "29876543210"
    return body + verhoeff_generate(body)

def test_classify_aadhaar_text():
    num = _aadhaar_number()
    text = f"Government of India  UIDAI  Aadhaar No: {num[:4]} {num[4:8]} {num[8:]}"
    r = classify_text(text)
    assert r["decision"] == "AADHAAR"
    assert r["identifier_valid"]

def test_classify_pan_text():
    text = "INCOME TAX DEPARTMENT  Permanent Account Number: ABCPK1234L"
    r = classify_text(text)
    assert r["decision"] == "PAN"

def test_classify_voter_text():
    text = "Election Commission of India  Elector Photo Identity Card  EPIC No: ABC1234567"
    r = classify_text(text)
    assert r["decision"] == "VOTER_ID"

def test_classify_dl_text():
    text = "Transport Department  DRIVING LICENCE  DL No: MH12 20110012345  Valid Till 2030"
    r = classify_text(text)
    assert r["decision"] == "DL"

def test_classify_passport_text():
    text = "REPUBLIC OF INDIA  PASSPORT  Country Code IND  Passport No: A1234567"
    r = classify_text(text)
    assert r["decision"] == "PASSPORT"

def test_decoy_is_unknown():
    # 12-digit account number, no Aadhaar keywords, invalid checksum
    text = "STATE BANK ACCOUNT STATEMENT  Account Number: 3021 4455 6789  IFSC SBIN0001234"
    r = classify_text(text)
    assert r["decision"] == "UNKNOWN"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}  {e}")
        except Exception as e:
            print(f"  ERR   {t.__name__}  {type(e).__name__}: {e}")
    print(f"\n  {passed}/{len(tests)} tests passed")
