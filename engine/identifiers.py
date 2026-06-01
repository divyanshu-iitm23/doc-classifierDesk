"""
identifiers.py
--------------
The single source of truth for every supported Indian KYC document type.

Each document type is defined by:
  - a strict regex for its unique identifier (matched against whole tokens),
  - a normaliser that strips spaces/hyphens so "XXXX XXXX XXXX" -> "XXXXXXXXXXXX",
  - a validator key (which checksum / structural rule to apply),
  - context keywords that boost confidence when present.

This is what makes the engine document-type-aware rather than a blind OCR dump.
"""

import re

# -----------------------------------------------------------------------------
# IDENTIFIER FORMATS  (Indian documents)
# -----------------------------------------------------------------------------
#  Aadhaar  : 12 digits          e.g. 2345 6789 0123   (Verhoeff checksum, 1st digit 2-9)
#  PAN      : 10 chars  AAAAA9999A   5 letters + 4 digits + 1 letter
#  VoterID  : 10 chars  AAA9999999   3 letters + 7 digits   (EPIC number)
#  DL       : 15 chars  AA9999999999999  2-letter state + 13 digits  (real-world format)
#             (the BRD says "15 digits"; real DLs always carry a 2-letter state code,
#              so we require the state-code prefix — a pure 15-digit number is rejected
#              because it collides with the MICR / transaction code printed on cheques)
#  Passport : 8 chars   A9999999    1 letter + 7 digits  OR  AA999999  2 letters + 6 digits
# -----------------------------------------------------------------------------

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
            r"(?<![A-Z0-9])([A-Z]{2}[\s-]?\d{2}[\s-]?\d{4}[\s-]?\d{7})(?![A-Z0-9])"
        ),
        "token_regex": re.compile(r"^[A-Z]{2}\d{13}$"),
        "length": 15,
        "validator": "dl_structure",
        "keywords": [
            "driving licence", "driving license", "transport", "motor vehicle",
            "dl no", "licence to drive", "validity", "doi",
        ],
    },
    "PASSPORT": {
        "display_name": "Passport",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{1,2}\d{6,7})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{1,2}\d{6,7}$"),
        "length": 8,
        "validator": "passport_structure",
        "keywords": [
            "passport", "republic of india", "place of issue", "country code",
            "nationality", "given name", "surname",
        ],
    },
    "BANK_STATEMENT": {
        "display_name": "Bank Statement",
        "doc_class": "bank",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{4}0[A-Z0-9]{6})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
        "length": 11,
        "validator": "ifsc_structure",
        "keywords": [
            "ifsc", "account number", "a/c no", "branch", "micr",
            "bank", "savings", "current account",
        ],
        "distinctive": [
            "statement of account", "account statement", "statement period",
            "opening balance", "closing balance", "transaction details",
            "withdrawal", "deposit", "debit", "credit", "balance",
            "from date", "to date", "narration", "value date", "cheque no",
            "statement of transactions", "available balance",
        ],
    },
    "BANK_PASSBOOK": {
        "display_name": "Bank Passbook",
        "doc_class": "bank",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{4}0[A-Z0-9]{6})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
        "length": 11,
        "validator": "ifsc_structure",
        "keywords": [
            "ifsc", "account number", "a/c no", "branch", "micr",
            "bank", "savings", "current account",
        ],
        "distinctive": [
            "passbook", "pass book", "customer id", "cust id",
            "savings bank account", "sb account", "account holder",
            "nominee", "branch name", "branch code", "date of issue",
            "mode of operation", "scheme", "joint holder",
        ],
    },
    "CHEQUE": {
        "display_name": "Bank Cheque",
        "doc_class": "bank",
        "raw_regex": re.compile(r"(?<![A-Z0-9])([A-Z]{4}0[A-Z0-9]{6})(?![A-Z0-9])"),
        "token_regex": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
        "length": 11,
        "validator": "ifsc_structure",
        "keywords": [
            "ifsc", "bank", "branch", "micr", "neft", "payable",
        ],
        "distinctive": [
            "valid for three months", "three months only", "months only",
            "payable at par", "ac payee", "a/c payee", "account payee",
            "or bearer", "or order", "ddmmyyyy", "neft ifs code",
            "ifs code", "pay ", "rupees",
        ],
    },

    # -------------------------------------------------------------------------
    # RECEIPT-CLASS DOCUMENTS (invoice / insurance / road-tax)
    # -------------------------------------------------------------------------
    # These have no single rigid identifier, so they are scored by distinctive
    # phrases (see classifier._score_receipt), with an optional structured anchor
    # where one exists: GSTIN for invoices, vehicle-registration for road tax.
    # Insurance receipts have no standard identifier, so they are phrase-only.
    "INVOICE": {
        "display_name": "Invoice",
        "doc_class": "receipt",
        # GSTIN anchor: 2-digit state + 10-char PAN + entity + Z + check
        "anchor_regex": re.compile(
            r"(?<![A-Z0-9])(\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z][A-Z][0-9A-Z])(?![A-Z0-9])"
        ),
        "anchor_validator": "gstin_structure",
        "distinctive": [
            "tax invoice", "invoice", "invoice no", "invoice number",
            "invoice date", "bill to", "ship to", "billed to", "hsn", "sac",
            "cgst", "sgst", "igst", "taxable value", "place of supply",
            "purchase order", "po no", "po number", "quantity", "qty",
            "unit price", "amount in words", "e-invoice", "irn", "gstin",
            "total amount", "grand total", "sub total", "subtotal",
        ],
    },
    "INSURANCE": {
        "display_name": "Insurance Receipt",
        "doc_class": "receipt",
        "anchor_regex": None,           # no standardised policy-number format
        "anchor_validator": None,
        "distinctive": [
            "policy", "policy no", "policy number", "premium", "premium receipt",
            "sum assured", "sum insured", "insured", "insurer", "policyholder",
            "policy holder", "nominee", "irdai", "irda", "renewal", "maturity",
            "life insurance", "health insurance", "motor insurance",
            "vehicle insurance", "general insurance", "proposal", "coverage",
            "policy period", "assurance", "underwriting", "no claim bonus",
        ],
    },
    "ROAD_TAX": {
        "display_name": "Road Tax Receipt",
        "doc_class": "receipt",
        # vehicle-registration anchor: SS NN L(1-3) NNNN
        "anchor_regex": re.compile(
            r"(?<![A-Z0-9])([A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4})(?![A-Z0-9])"
        ),
        "anchor_validator": "vehicle_reg_structure",
        "distinctive": [
            "road tax", "motor vehicle tax", "mv tax", "vehicle tax", "tax token",
            "registration number", "regn no", "regn number", "rto",
            "transport department", "regional transport", "chassis", "engine number",
            "fitness", "permit", "vehicle class", "tax receipt", "one time tax",
            "lifetime tax", "validity", "registration mark", "owner name",
            "fee receipt", "tax paid", "vahan",
        ],
    },
}

# Document types that use the bank scoring path rather than the identifier path.
BANK_TYPES = {k for k, v in DOCUMENT_SPECS.items() if v.get("doc_class") == "bank"}

# Document types that use the receipt scoring path (phrases + optional anchor).
RECEIPT_TYPES = {k for k, v in DOCUMENT_SPECS.items() if v.get("doc_class") == "receipt"}


def normalise(raw_match: str) -> str:
    """Strip spaces and hyphens so a spaced/grouped identifier becomes a clean token."""
    return re.sub(r"[\s-]", "", raw_match).upper()


# -----------------------------------------------------------------------------
# OCR-NOISE TOLERANCE
# -----------------------------------------------------------------------------
# OCR confuses visually similar glyphs. When a near-miss token doesn't fit a
# document's shape, we try swapping these into the position the shape expects.
# These cover the letter<->digit confusions that actually occur in practice.
_TO_DIGIT = str.maketrans({
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "|": "1",
    "Z": "2",
    "E": "3",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
    "g": "9", "q": "9",
})
_TO_LETTER = str.maketrans({
    "0": "O", "1": "I", "2": "Z", "3": "E", "4": "A",
    "5": "S", "6": "G", "7": "T", "8": "B",
})


def ocr_repair(token: str, shape: str) -> str:
    """
    Coerce each character of `token` toward the expected `shape`, where shape is a
    string of 'A' (letter expected) and '9' (digit expected), same length as token.
    Returns the repaired token (may still be invalid; the validator decides).
    """
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


# expected character shape per document type, used by ocr_repair
SHAPES = {
    "AADHAAR":  "9" * 12,
    "PAN":      "AAAAA9999A",
    "VOTER_ID": "AAA9999999",
    "DL":       "AA9999999999999",   # canonical 2-letter + 13-digit form
    "PASSPORT": None,          # two shapes possible (A9999999 / AA999999), handled specially
    "BANK_STATEMENT": "AAAA0AAAAAA",  # IFSC: 4 letters + 0 + 6 alnum
    "BANK_PASSBOOK":  "AAAA0AAAAAA",
    "CHEQUE":         "AAAA0AAAAAA",
}
