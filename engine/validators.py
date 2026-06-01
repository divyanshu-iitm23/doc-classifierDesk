"""
validators.py
-------------
Validation raises a found identifier from "looks right" to "is structurally valid".

The standout is the Aadhaar Verhoeff checksum — the actual algorithm UIDAI uses.
A random 12-digit number passes the *pattern* but fails the *checksum*, which is
exactly how we separate a real Aadhaar number from any 12-digit string (a phone
number, an account number, etc.). This is the difference between a toy and an engine.
"""

# -----------------------------------------------------------------------------
# VERHOEFF ALGORITHM (used by UIDAI for the Aadhaar check digit)
# -----------------------------------------------------------------------------
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 9, 1, 2, 3, 4, 6, 7],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_validate(number: str) -> bool:
    """Return True if `number` (incl. its check digit) is Verhoeff-valid."""
    if not number.isdigit():
        return False
    c = 0
    for i, item in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(item)]]
    return c == 0


def verhoeff_generate(number: str) -> str:
    """Return the Verhoeff check digit for `number` (which has NO check digit yet)."""
    c = 0
    for i, item in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(item)]]
    return str(_VERHOEFF_INV[c])


# -----------------------------------------------------------------------------
# AADHAAR
# -----------------------------------------------------------------------------
def validate_aadhaar(num: str):
    """12 digits, first digit 2-9 (UIDAI never issues numbers starting 0 or 1),
    and a valid Verhoeff check digit."""
    reasons = []
    if len(num) != 12 or not num.isdigit():
        return False, "not 12 digits"
    if num[0] in "01":
        reasons.append("first digit is 0/1 (invalid)")
    if not verhoeff_validate(num):
        reasons.append("Verhoeff checksum failed")
    if reasons:
        return False, "; ".join(reasons)
    return True, "12 digits, first digit valid, Verhoeff checksum OK"


# -----------------------------------------------------------------------------
# PAN
# -----------------------------------------------------------------------------
# 4th char = holder type, 5th char = first letter of surname/name.
_PAN_HOLDER_TYPES = set("PCHFATBLJGK")  # P=Individual, C=Company, H=HUF, F=Firm, ...

def validate_pan(num: str):
    if len(num) != 10:
        return False, "not 10 characters"
    if not (num[:5].isalpha() and num[5:9].isdigit() and num[9].isalpha()):
        return False, "does not match AAAAA9999A shape"
    holder = num[3]
    if holder not in _PAN_HOLDER_TYPES:
        return False, f"4th char '{holder}' is not a valid PAN holder type"
    return True, f"AAAAA9999A shape OK, holder type '{holder}' valid"


# -----------------------------------------------------------------------------
# VOTER ID (EPIC)
# -----------------------------------------------------------------------------
def validate_voter(num: str):
    if len(num) != 10:
        return False, "not 10 characters"
    if not (num[:3].isalpha() and num[3:].isdigit()):
        return False, "does not match AAA9999999 shape"
    return True, "AAA9999999 shape OK"


# -----------------------------------------------------------------------------
# DRIVING LICENCE
# -----------------------------------------------------------------------------
# Valid Indian RTO state codes (2-letter). Used to sanity-check the prefix.
_DL_STATE_CODES = {
    "AP","AR","AS","BR","CG","CH","DD","DL","DN","GA","GJ","HP","HR","JH","JK",
    "KA","KL","LD","MH","ML","MN","MP","MZ","NL","OD","OR","PB","PY","RJ","SK",
    "TN","TR","TS","UK","UP","WB","AN","LA",
}

def validate_dl(num: str):
    if len(num) != 15:
        return False, "not 15 characters"
    # Real Indian DLs are: 2-letter state code + 13 digits (e.g. UP1320220003068).
    # We require the state-code prefix. The earlier "pure 15-digit" fallback was
    # removed because it matched unrelated 15-digit numbers — notably the MICR /
    # transaction code printed on cheques — causing false DL classifications.
    if num[:2].isalpha() and num[2:].isdigit():
        state = num[:2]
        if state not in _DL_STATE_CODES:
            return False, f"state code '{state}' not a valid RTO code"
        year = num[4:8]
        return True, f"state '{state}', RTO '{num[2:4]}', year '{year}' — structure OK"
    return False, "not a valid DL (needs 2-letter state code + 13 digits)"


# -----------------------------------------------------------------------------
# PASSPORT
# -----------------------------------------------------------------------------
# Indian passport: 1 letter + 7 digits  OR  2 letters + 6 digits.
# Letters Q, X, Z are not used as the first-letter prefix.
_PASSPORT_EXCLUDED = set("QXZ")

def validate_passport(num: str):
    if len(num) != 8:
        return False, "not 8 characters"
    # Format 1: 1 letter + 7 digits  (A9999999)
    fmt1 = num[0].isalpha() and num[1:].isdigit()
    # Format 2: 2 letters + 6 digits (AA999999)
    fmt2 = num[:2].isalpha() and num[2:].isdigit()
    if not (fmt1 or fmt2):
        return False, "does not match A9999999 or AA999999 shape"
    if num[0] in _PASSPORT_EXCLUDED:
        return False, f"prefix letter '{num[0]}' not used in Indian passports"
    if fmt2 and not fmt1:
        return True, f"AA999999 shape OK, prefix '{num[:2]}' valid"
    return True, f"A9999999 shape OK, prefix '{num[0]}' valid"


# -----------------------------------------------------------------------------
# IFSC  (Indian Financial System Code) - the shared identifier on bank documents
# -----------------------------------------------------------------------------
# 11 chars: 4-letter bank code + a mandatory '0' (5th char) + 6-char branch code.
# The 5th-position zero is a hard rule; any code with a non-zero 5th char is invalid.
def validate_ifsc(code: str):
    if len(code) != 11:
        return False, "not 11 characters"
    if not code[:4].isalpha():
        return False, "first 4 chars (bank code) must be letters"
    if code[4] != "0":
        return False, f"5th char must be '0', got '{code[4]}'"
    if not code[5:].isalnum():
        return False, "last 6 chars (branch code) must be alphanumeric"
    return True, f"IFSC OK - bank '{code[:4]}', branch '{code[5:]}'"


# -----------------------------------------------------------------------------
# GSTIN  (GST Identification Number) - the anchor on tax invoices
# -----------------------------------------------------------------------------
# 15 chars: 2-digit state code + 10-char PAN (AAAAA9999A) + entity digit + 'Z'
# + check char. The embedded PAN shape is itself a strong structural check.
_GST_STATE_CODES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}  # 01-38 + others

def validate_gstin(g: str):
    if len(g) != 15:
        return False, "not 15 characters"
    if not g[:2].isdigit():
        return False, "first 2 chars (state code) must be digits"
    if g[:2] not in _GST_STATE_CODES:
        return False, f"invalid GST state code '{g[:2]}'"
    pan = g[2:12]
    if not (pan[:5].isalpha() and pan[5:9].isdigit() and pan[9].isalpha()):
        return False, "embedded PAN (chars 3-12) malformed"
    if g[13] != "Z":
        # 14th char is 'Z' on standard GSTINs; accept but note (OCR may corrupt it)
        return True, f"GSTIN structure OK (state {g[:2]}, non-standard 14th char '{g[13]}')"
    return True, f"GSTIN OK - state {g[:2]}, PAN {pan}"


# -----------------------------------------------------------------------------
# VEHICLE REGISTRATION NUMBER - the anchor on road-tax receipts
# -----------------------------------------------------------------------------
# Common format: 2-letter state + 1-2 digit RTO + 1-3 letter series + 4-digit number
# e.g. MH12AB1234, DL3CAB1234, KA01A1234. State code reuses the RTO list.
import re as _re

_VEHICLE_RE = _re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})$")

def validate_vehicle_reg(v: str):
    v = _re.sub(r"[\s-]", "", v).upper()
    m = _VEHICLE_RE.match(v)
    if not m:
        return False, "does not match vehicle-registration shape"
    state = m.group(1)
    if state not in _DL_STATE_CODES:
        return False, f"state code '{state}' not a valid RTO code"
    return True, f"vehicle reg OK - state '{state}', RTO '{m.group(2)}'"


# -----------------------------------------------------------------------------
# DISPATCH
# -----------------------------------------------------------------------------
VALIDATORS = {
    "aadhaar_verhoeff": validate_aadhaar,
    "pan_structure": validate_pan,
    "voter_structure": validate_voter,
    "dl_structure": validate_dl,
    "passport_structure": validate_passport,
    "ifsc_structure": validate_ifsc,
    "gstin_structure": validate_gstin,
    "vehicle_reg_structure": validate_vehicle_reg,
}


def validate(validator_key: str, number: str):
    """Returns (is_valid: bool, reason: str)."""
    fn = VALIDATORS.get(validator_key)
    if not fn:
        return False, "no validator"
    return fn(number)
