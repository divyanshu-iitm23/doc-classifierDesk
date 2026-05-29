import re

DOCUMENT_SPECS = {
    "AADHAAR": {
        "display_name": "Aadhaar Card",
        "raw_regex": re.compile(r"(?<!\d)(\d{4}\s?\d{4}\s?\d{4})(?!\d)"),
        "token_regex": re.compile(r"^\d{12}$"),
        "length": 12,
        "validator": "aadhaar_verhoeff",
        "keywords": [
            "aadhaar", "aadhar", "uidai", "unique identification",
            "government of india", "vid", "मेरा आधार", "आधार",
        ],
    },
    "PAN": {
        "display_name": "PAN Card",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{5}\d{4}[A-Z])(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{5}\d{4}[A-Z]$"),
        "length": 10,
        "validator": "pan_structure",
        "keywords": [
            "income tax", "permanent account number", "pan",
            "आयकर", "govt. of india", "department",
        ],
    },
    "VOTER_ID": {
        "display_name": "Voter ID (EPIC)",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{3}\d{7})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{3}\d{7}$"),
        "length": 10,
        "validator": "voter_structure",
        "keywords": [
            "election commission", "elector", "epic", "identity card",
            "निर्वाचन", "voter",
        ],
    },
    "DL": {
        "display_name": "Driving Licence",
        "raw_regex": re.compile(
            r"(?<![A-Z0-9])([A-Z]{2}[\s-]?\d{2}[\s-]?\d{4}[\s-]?\d{7}|\d{15})(?![A-Z0-9])"
        ),
        "token_regex": re.compile(r"^([A-Z]{2}\d{13}|\d{15})$"),
        "length": 15,
        "validator": "dl_structure",
        "keywords": [
            "driving licence", "driving license", "transport", "motor vehicle",
            "dl no", "licence to drive", "validity", "doi",
        ],
    },
    "PASSPORT": {
        "display_name": "Passport",
        "raw_regex": re.compile(r"(?<![A-Z0-9])(?:[A-Z]\d{7}|[A-Z]{2}\d{6})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^(?:[A-Z]\d{7}|[A-Z]{2}\d{6})$"),
        "length": 8,
        "validator": "passport_structure",
        "keywords": [
            "passport", "republic of india", "place of issue", "country code",
            "type", "nationality", "ind",
        ],
    },
}


def normalise(raw_match: str) -> str:
    return re.sub(r"[\s-]", "", raw_match).upper()
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
                            "Z": "2", "S": "5", "B": "8", "G": "6", "T": "7"})
_TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "6": "G", "2": "Z"})


def ocr_repair(token: str, shape: str) -> str:
    if len(token) != len(shape):
        return token
    out = []
    for ch, kind in zip(token, shape):
        if kind == "9" and ch.isalpha():
            out.append(ch.translate(_TO_DIGIT))
        elif kind == "A" and ch.isdigit():
            out.append(ch.translate(_TO_LETTER))
        else:
            out.append(ch)
    return "".join(out)

SHAPES = {
    "AADHAAR":  "999999999999",
    "PAN":      "AAAAA9999A",
    "VOTER_ID": "AAA9999999",
    "DL":       "AA9999999999999",   
    "PASSPORT": ["A9999999", "AA999999"]
}
