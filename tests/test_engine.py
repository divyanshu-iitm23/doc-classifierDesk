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
    assert validate_dl("MH1220110012345")[0]          # MH + 13 digits
    assert not validate_dl("123456789012345")[0]       # pure 15-digit now REJECTED (was a MICR false-positive source)
    assert not validate_dl("ZZ1220110012345")[0]       # ZZ not a valid state code
    assert not validate_dl("917020028130966")[0]       # a cheque MICR number must not pass as a DL

def test_passport_structure():
    # Format 1: 1 letter + 7 digits
    assert validate_passport("A1234567")[0]
    assert not validate_passport("Q1234567")[0]   # Q excluded
    # Format 2: 2 letters + 6 digits
    assert validate_passport("AB123456")[0]
    assert validate_passport("MA123456")[0]
    assert not validate_passport("QA123456")[0]   # Q excluded (first letter)
    # Invalid shapes
    assert not validate_passport("ABC12345")[0]   # 3 letters + 5 digits
    assert not validate_passport("A123456")[0]    # too short (7 chars)
    assert not validate_passport("A12345678")[0]  # too long (9 chars)


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

def test_account_number_not_mistaken_for_aadhaar():
    # The original "decoy": a 12-digit account number must NOT be read as Aadhaar
    # (fails Verhoeff, no Aadhaar keywords). This text IS now a valid bank statement
    # (says "ACCOUNT STATEMENT" + has a valid IFSC), so it classifies as such - but
    # the point still stands: it is not classified as AADHAAR.
    text = "STATE BANK ACCOUNT STATEMENT  Account Number: 3021 4455 6789  IFSC SBIN0001234"
    r = classify_text(text)
    assert r["decision"] != "AADHAAR"
    assert r["decision"] == "BANK_STATEMENT"

def test_bank_statement():
    text = ("STATE BANK OF INDIA  Statement of Account  IFSC: SBIN0001234  "
            "Statement Period 01-04-2026 to 30-04-2026  Opening Balance 1000  "
            "Closing Balance 2000  Narration Debit Credit Balance")
    r = classify_text(text)
    assert r["decision"] == "BANK_STATEMENT"

def test_bank_passbook():
    text = ("BANK OF BARODA  PASSBOOK  Customer ID 99201234  Savings Bank Account  "
            "IFSC: BARB0XANDHE  Branch Name Andheri  Account Holder Test  Nominee yes")
    r = classify_text(text)
    assert r["decision"] == "BANK_PASSBOOK"

def test_cheque():
    # real-cheque markers (from actual OCR): validity notice, payable at par,
    # A/C payee, date-box template, IFS code — and NO transaction table.
    text = ("ICICI BANK  VALID FOR THREE MONTHS ONLY  A/C PAYEE  MAYUR VIHAR BRANCH  "
            "PAYABLE AT PAR AT ALL BRANCHES  DDMMYYYY  OR ORDER  "
            "NEFT IFS CODE ICIC0006297  Pay TEST SUBJECT  Rupees One Lakh Only")
    assert classify_text(text)["decision"] == "CHEQUE"

def test_cheque_micr_not_misread_as_dl():
    # a cheque's 15-digit MICR-ish number must not win as a Driving Licence when
    # there's clear bank context (valid IFSC + cheque phrases).
    text = ("STATE BANK OF INDIA  VALID FOR THREE MONTHS ONLY  PAYABLE AT PAR  "
            "A/C PAYEE  NEFT IFS CODE SBIN0001234  917020028130966  OR BEARER")
    assert classify_text(text)["decision"] == "CHEQUE"

def test_statement_not_misread_as_cheque():
    # a statement with a transaction table must stay a statement, not a cheque.
    stmt = ("STATE BANK OF INDIA  Statement of Account  IFSC SBIN0108947  "
            "Statement Period 01-04-2026 to 30-04-2026  Opening Balance 45200.00  "
            "03-04-2026 UPI Grocery 1,200.00 44,000.00  "
            "08-04-2026 ATM Withdrawal 5,000.00 39,000.00  "
            "12-04-2026 Salary Credit 85,000.00 1,24,000.00  "
            "20-04-2026 NEFT Rent 18,000.00 1,06,000.00  Closing Balance 1,06,320.00")
    assert classify_text(stmt)["decision"] == "BANK_STATEMENT"

def test_bank_number_not_misread_as_aadhaar():
    # 370785939786 coincidentally PASSES the Aadhaar Verhoeff checksum, but it is a
    # CIF/account number on a passbook. Bank markers must suppress the Aadhaar match
    # so the document is not classified as an Aadhaar card.
    from engine.validators import verhoeff_validate
    assert verhoeff_validate("370785939786")  # confirm it really is a Verhoeff pass
    text = ("STATE BANK OF INDIA  SAVINGS BANK ACCOUNT  KINATHUKADAVU  "
            "370785939786  ACCOUNT NO  CUSTOMER NAME  IFS CODE SBIN0012656")
    r = classify_text(text)
    assert r["decision"] != "AADHAAR", f"got {r['decision']}"

# --- receipt-class documents (invoice / insurance / road-tax) ----------------
def test_invoice():
    text = ("TAX INVOICE  ABC Traders  GSTIN 27ABCDE1234F1Z5  Invoice No INV-42  "
            "Bill To XYZ  HSN 8471  Taxable Value 90000.00  CGST 8100.00 SGST 8100.00  "
            "Grand Total 106200.00")
    assert classify_text(text)["decision"] == "INVOICE"

def test_invoice_gstin_validates():
    from engine.validators import validate_gstin
    assert validate_gstin("27ABCDE1234F1Z5")[0]       # Maharashtra, valid
    assert not validate_gstin("00ABCDE1234F1Z5")[0]   # 00 invalid state code
    assert not validate_gstin("27ABCD1234F1Z5")[0]    # malformed embedded PAN (too short)

def test_insurance():
    text = ("STAR HEALTH INSURANCE  Premium Receipt  Policy No SH889912  "
            "Sum Insured 500000  Premium Paid 12450  Policyholder Test  IRDAI 129")
    assert classify_text(text)["decision"] == "INSURANCE"

def test_road_tax():
    text = ("TRANSPORT DEPARTMENT  Motor Vehicle Tax Receipt  Registration Number MH12AB1234  "
            "Road Tax Paid 9600  One Time Tax  RTO Andheri  Chassis MA3FHEB1S00123456")
    assert classify_text(text)["decision"] == "ROAD_TAX"

def test_invoice_with_bank_details_not_statement():
    # B2B invoices often print the seller's bank details (IFSC + A/C). The invoice
    # phrases must still win over the bank-statement path.
    text = ("TAX INVOICE  GSTIN 27ABCDE1234F1Z5  Invoice No INV-99  HSN 8471  "
            "CGST 900 SGST 900  Taxable Value 10000  Grand Total 11800  "
            "Bank Details A/C No 1234567890  IFSC HDFC0001234")
    assert classify_text(text)["decision"] == "INVOICE"

def test_receipt_number_not_misread_as_id():
    # an insurance/road-tax doc full of long numbers must not become an ID card.
    from engine.validators import verhoeff_validate
    # uses the known coincidental-Verhoeff number inside an insurance receipt
    text = ("LIFE INSURANCE  Premium Receipt  Policy No 370785939786  "
            "Sum Assured 1000000  Premium 25000  Policyholder Test  IRDAI 512")
    assert classify_text(text)["decision"] != "AADHAAR"

def test_statement_vs_passbook_disambiguation():
    # Same IFSC/bank context; only the distinctive phrases differ.
    stmt = "BANK IFSC HDFC0001234 statement period opening balance closing balance narration"
    pb = "BANK IFSC HDFC0001234 passbook customer id savings bank account branch name nominee"
    assert classify_text(stmt)["decision"] == "BANK_STATEMENT"
    assert classify_text(pb)["decision"] == "BANK_PASSBOOK"

def test_ifsc_validation():
    from engine.validators import validate_ifsc
    assert validate_ifsc("SBIN0001234")[0]
    assert not validate_ifsc("SBIN1001234")[0]   # 5th char not 0
    assert not validate_ifsc("SB1N0001234")[0]   # bank code not all letters
    assert not validate_ifsc("SBIN000123")[0]    # too short

def test_true_unknown():
    # A document that is none of the supported types -> UNKNOWN.
    text = "MAHARASHTRA STATE ELECTRICITY BILL  Consumer No 1234567  Units 250  Amount Due 1820"
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
