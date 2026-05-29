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
    if not number.isdigit():
        return False
    c = 0
    for i, item in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(item)]]
    return c == 0


def verhoeff_generate(number: str) -> str:
    c = 0
    for i, item in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(item)]]
    return str(_VERHOEFF_INV[c])

def validate_aadhaar(num: str):
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


_PAN_HOLDER_TYPES = set("PCHFATBLJGK")  
def validate_pan(num: str):
    if len(num) != 10:
        return False, "not 10 characters"
    if not (num[:5].isalpha() and num[5:9].isdigit() and num[9].isalpha()):
        return False, "does not match AAAAA9999A shape"
    holder = num[3]
    if holder not in _PAN_HOLDER_TYPES:
        return False, f"4th char '{holder}' is not a valid PAN holder type"
    return True, f"AAAAA9999A shape OK, holder type '{holder}' valid"

def validate_voter(num: str):
    if len(num) != 10:
        return False, "not 10 characters"
    if not (num[:3].isalpha() and num[3:].isdigit()):
        return False, "does not match AAA9999999 shape"
    return True, "AAA9999999 shape OK"

_DL_STATE_CODES = {
    "AP","AR","AS","BR","CG","CH","DD","DL","DN","GA","GJ","HP","HR","JH","JK",
    "KA","KL","LD","MH","ML","MN","MP","MZ","NL","OD","OR","PB","PY","RJ","SK",
    "TN","TR","TS","UK","UP","WB","AN","LA",
}

def validate_dl(num: str):
    if len(num) != 15:
        return False, "not 15 characters"
    if num[:2].isalpha() and num[2:].isdigit():
        state = num[:2]
        if state not in _DL_STATE_CODES:
            return False, f"state code '{state}' not a valid RTO code"
        year = num[4:8]
        return True, f"state '{state}', RTO '{num[2:4]}', year '{year}' — structure OK"
    if num.isdigit():
        return True, "15-digit numeric DL (no state prefix)"
    return False, "does not match AA+13digits or 15-digit shape"

_PASSPORT_EXCLUDED = set("QXZ")
def validate_passport(num: str):
    if len(num) != 8:
        return False, "not 8 characters"
    if not (num[0].isalpha() and num[2:].isdigit()):
        return False, "does not match A9999999 shape"
    if num[0] in _PASSPORT_EXCLUDED:
        return False, f"prefix letter '{num[0]}' not used in Indian passports"
    return True, f"A9999999 shape OK, prefix '{num[0]}' valid"


VALIDATORS = {
    "aadhaar_verhoeff": validate_aadhaar,
    "pan_structure": validate_pan,
    "voter_structure": validate_voter,
    "dl_structure": validate_dl,
    "passport_structure": validate_passport,
}


def validate(validator_key: str, number: str):
    fn = VALIDATORS.get(validator_key)
    if not fn:
        return False, "no validator"
    return fn(number)
