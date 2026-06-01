"""
store.py
--------
Persists classified document data into the SQLite database.

After the classifier identifies a document and the text is extracted, this
module parses the relevant fields from the raw OCR / text-layer output and
writes them to the appropriate table:

  • AADHAAR, PASSPORT, DL, VOTER_ID  →  id_documents
  • PAN                              →  pan_cards
  • BANK_STATEMENT, BANK_PASSBOOK, CHEQUE  →  bank_accounts

Usage:
    from engine.store import store_result
    result = classify_file("aadhaar.pdf")
    store_result(customer_id="cust-001", classification=result, raw_text=text)
"""

import re
import uuid
from datetime import date

from .model import (
    init_db, get_session,
    IDDocument, IDDocumentType,
    PANCard,
    BankAccount,
)


# ---------------------------------------------------------------------------
# Field extractors  (regex-based, from raw OCR / text-layer text)
# ---------------------------------------------------------------------------
# These are best-effort: OCR text is noisy, so we grab what we can and leave
# the rest as None. The classifier has already confirmed the document type.

def _search(pattern: str, text: str, flags=re.IGNORECASE) -> str | None:
    """Return first captured group or None."""
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_date(raw: str | None) -> date | None:
    """Try common Indian date formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY."""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


# --- Name -------------------------------------------------------------------
_FIELD_BOUNDARY = r"(?=\s{2,}|\b(?:DOB|D\.?O\.?B|Date|Father|Address|Addr|Gender|Male|Female|Issue|Expiry|Valid|S/O|D/O|W/O|C/O|Branch|Account|IFSC|IFS|Savings|Current|Opening|Closing|Statement|Passbook)\b|$)"

_NAME_PATTERNS = [
    # "Name: ..."  /  "Name ..."
    r"(?:name|given\s*name|holder(?:'?s)?\s*name)\s*[:\-]?\s*([A-Z][A-Za-z .']+'?)" + _FIELD_BOUNDARY,
    # "<Name>" on Aadhaar (line after DOB sometimes)
    r"(?:government|uidai).*\n.*\n\s*([A-Z][A-Za-z .']{3,}?)" + _FIELD_BOUNDARY,
]

def _extract_name(text: str) -> str | None:
    for pat in _NAME_PATTERNS:
        val = _search(pat, text)
        if val and len(val) > 2:
            return val
    return None


# --- DOB --------------------------------------------------------------------
_DOB_PATTERNS = [
    r"(?:date\s*of\s*birth|d\.?o\.?b\.?|born|birth)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
    r"(?:DOB|D\.O\.B)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
]

def _extract_dob(text: str) -> date | None:
    for pat in _DOB_PATTERNS:
        raw = _search(pat, text)
        d = _parse_date(raw)
        if d:
            return d
    return None


# --- Gender -----------------------------------------------------------------
def _extract_gender(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(female|महिला)\b", lower):
        return "FEMALE"
    if re.search(r"\b(male|पुरुष)\b", lower):
        return "MALE"
    return None


# --- Address ----------------------------------------------------------------
_ADDR_PATTERNS = [
    r"(?:address|addr|s/o|d/o|w/o|c/o)\s*[:\-]?\s*(.+?)(?:\n\n|\bpin\b|\bdate\b|\bissue\b|$)",
]

def _extract_address(text: str) -> str | None:
    for pat in _ADDR_PATTERNS:
        val = _search(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if val and len(val) > 5:
            # collapse multiple whitespace / newlines
            return re.sub(r"\s+", " ", val).strip()[:500]
    return None


# --- PAN-specific -----------------------------------------------------------
def _extract_father_name(text: str) -> str | None:
    return _search(r"(?:father(?:'?s)?\s*name)\s*[:\-]?\s*([A-Z][A-Za-z .']+'?)" + _FIELD_BOUNDARY, text)


# --- Issue / Expiry dates (DL, Passport) ------------------------------------
def _extract_issue_date(text: str) -> date | None:
    raw = _search(r"(?:date\s*of\s*issue|doi|issued?\s*on|issue\s*date)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", text)
    return _parse_date(raw)

def _extract_expiry_date(text: str) -> date | None:
    raw = _search(
        r"(?:valid\s*(?:till|until|upto|thru)|expiry|exp\.?\s*date|"
        r"date\s*of\s*expiry|validity)\s*[:\-]?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        text,
    )
    return _parse_date(raw)


# --- Bank-specific ----------------------------------------------------------
_BANK_NAMES = [
    "STATE BANK OF INDIA", "SBI", "HDFC BANK", "ICICI BANK", "AXIS BANK",
    "PUNJAB NATIONAL BANK", "PNB", "BANK OF BARODA", "BOB", "CANARA BANK",
    "UNION BANK", "INDIAN BANK", "BANK OF INDIA", "BOI", "KOTAK MAHINDRA",
    "IDBI BANK", "YES BANK", "INDUSIND BANK", "FEDERAL BANK",
    "SOUTH INDIAN BANK", "KARUR VYSYA BANK", "BANDHAN BANK",
    "CENTRAL BANK OF INDIA", "INDIAN OVERSEAS BANK", "IOB",
    "UCO BANK", "ALLAHABAD BANK", "ORIENTAL BANK",
]

def _extract_bank_name(text: str) -> str | None:
    upper = text.upper()
    for bank in _BANK_NAMES:
        if bank in upper:
            return bank.title()
    return None


def _extract_account_no(text: str) -> str | None:
    """Extract bank account number (typically 9-18 digits)."""
    pats = [
        r"(?:a/?c\s*(?:no\.?|number)|account\s*(?:no\.?|number))\s*[:\-]?\s*(\d[\d\s]{7,17}\d)",
        r"(?:account)\s*[:\-]?\s*(\d{9,18})",
    ]
    for pat in pats:
        val = _search(pat, text)
        if val:
            return re.sub(r"\s", "", val)
    return None


def _extract_account_name(text: str) -> str | None:
    return _search(
        r"(?:account\s*holder|a/?c\s*holder|customer\s*name|account\s*name)\s*[:\-]?\s*([A-Z][A-Za-z .']+'?)" + _FIELD_BOUNDARY,
        text,
    )


def _extract_ifsc(text: str) -> str | None:
    m = re.search(r"(?:IFSC|IFS\s*CODE)\s*[:\-]?\s*([A-Z]{4}0[A-Z0-9]{6})", text.upper())
    return m.group(1) if m else None


def _extract_branch(text: str) -> str | None:
    m = re.search(
        r"(?:branch\s*(?:name)?)\s*[:\-]?\s*([A-Za-z][A-Za-z ,.']+?)"
        r"(?=\s{2,}|\b(?:Savings|Current|Opening|Closing|Account|IFSC|Statement|Passbook)\b|$)",
        text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_account_type(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\b(savings|sb\s+account|savings\s+bank)\b", lower):
        return "Savings"
    if re.search(r"\b(current\s+account|current)\b", lower):
        return "Current"
    return None


# ---------------------------------------------------------------------------
# Main store functions
# ---------------------------------------------------------------------------
_ID_DOC_TYPES = {"AADHAAR", "PASSPORT", "DL", "VOTER_ID"}
_BANK_TYPES   = {"BANK_STATEMENT", "BANK_PASSBOOK", "CHEQUE"}


def store_result(
    customer_id: str,
    classification: dict,
    raw_text: str,
    *,
    session=None,
) -> dict:
    """
    Parse fields from `raw_text` and persist to the DB based on the
    classification result.

    Parameters
    ----------
    customer_id   : the customer this document belongs to
    classification: dict returned by classify() / classify_file()
    raw_text      : the raw OCR / text-layer text of the document
    session       : optional SQLAlchemy session (one is created if omitted)

    Returns
    -------
    dict with "stored": True/False, "table": table name, "record_id": PK value,
    and "fields": dict of what was saved.
    """
    decision = classification.get("decision", "UNKNOWN")
    identifier = classification.get("identifier")

    if decision == "UNKNOWN" or decision == "ERROR":
        return {"stored": False, "reason": f"document type is {decision}"}

    own_session = session is None
    if own_session:
        init_db()
        session = get_session()

    try:
        if decision in _ID_DOC_TYPES:
            result = _store_id_document(session, customer_id, decision, identifier, raw_text)
        elif decision == "PAN":
            result = _store_pan(session, customer_id, identifier, raw_text)
        elif decision in _BANK_TYPES:
            result = _store_bank_account(session, customer_id, identifier, raw_text)
        else:
            return {"stored": False, "reason": f"store not implemented for {decision}"}

        session.commit()
        return result

    except Exception as e:
        session.rollback()
        return {"stored": False, "reason": f"DB error: {e}"}
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# Per-type store helpers
# ---------------------------------------------------------------------------

def _store_id_document(session, customer_id: str, doc_type: str,
                       identifier: str, text: str) -> dict:
    """Store Aadhaar / Passport / DL / Voter ID."""
    doc_id = identifier or f"UNKNOWN-{uuid.uuid4().hex[:8]}"
    doc_type_enum = IDDocumentType(doc_type)

    name       = _extract_name(text)
    dob        = _extract_dob(text)
    address    = _extract_address(text)
    gender     = _extract_gender(text)
    issue_date = _extract_issue_date(text)
    expiry_date = _extract_expiry_date(text)

    # upsert: update if the document_id already exists
    existing = session.get(IDDocument, doc_id)
    if existing:
        existing.customer_id   = customer_id
        existing.document_type = doc_type_enum
        existing.name          = name or existing.name
        existing.date_of_birth = dob or existing.date_of_birth
        existing.address       = address or existing.address
        existing.gender        = gender or existing.gender
        existing.issue_date    = issue_date or existing.issue_date
        existing.expiry_date   = expiry_date or existing.expiry_date
        record = existing
    else:
        record = IDDocument(
            document_id   = doc_id,
            customer_id   = customer_id,
            document_type = doc_type_enum,
            name          = name,
            date_of_birth = dob,
            address       = address,
            gender        = gender,
            issue_date    = issue_date,
            expiry_date   = expiry_date,
        )
        session.add(record)

    fields = {
        "document_id": doc_id, "document_type": doc_type,
        "name": name, "date_of_birth": str(dob) if dob else None,
        "address": address, "gender": gender,
        "issue_date": str(issue_date) if issue_date else None,
        "expiry_date": str(expiry_date) if expiry_date else None,
    }
    return {"stored": True, "table": "id_documents", "record_id": doc_id, "fields": fields}


def _store_pan(session, customer_id: str, identifier: str, text: str) -> dict:
    """Store PAN card."""
    pan_no = identifier or f"UNKNOWN-{uuid.uuid4().hex[:8]}"

    name        = _extract_name(text)
    father_name = _extract_father_name(text)
    dob         = _extract_dob(text)
    holder_type = pan_no[3] if len(pan_no) >= 4 and pan_no[3].isalpha() else None

    existing = session.get(PANCard, pan_no)
    if existing:
        existing.customer_id = customer_id
        existing.name        = name or existing.name
        existing.father_name = father_name or existing.father_name
        existing.date_of_birth = dob or existing.date_of_birth
        existing.holder_type = holder_type or existing.holder_type
        record = existing
    else:
        record = PANCard(
            pan_no        = pan_no,
            customer_id   = customer_id,
            name          = name,
            father_name   = father_name,
            date_of_birth = dob,
            holder_type   = holder_type,
        )
        session.add(record)

    fields = {
        "pan_no": pan_no, "name": name, "father_name": father_name,
        "date_of_birth": str(dob) if dob else None, "holder_type": holder_type,
    }
    return {"stored": True, "table": "pan_cards", "record_id": pan_no, "fields": fields}


def _store_bank_account(session, customer_id: str, ifsc_identifier: str,
                        text: str) -> dict:
    """Store bank account from a statement / passbook / cheque."""
    account_no   = _extract_account_no(text)
    account_name = _extract_account_name(text)
    bank_name    = _extract_bank_name(text)
    ifsc_code    = _extract_ifsc(text) or ifsc_identifier
    branch       = _extract_branch(text)
    account_type = _extract_account_type(text)

    if not account_no:
        return {"stored": False, "reason": "could not extract account number from text"}

    existing = session.get(BankAccount, account_no)
    if existing:
        existing.customer_id  = customer_id
        existing.account_name = account_name or existing.account_name
        existing.bank_name    = bank_name or existing.bank_name
        existing.ifsc_code    = ifsc_code or existing.ifsc_code
        existing.branch       = branch or existing.branch
        existing.account_type = account_type or existing.account_type
        record = existing
    else:
        record = BankAccount(
            account_no   = account_no,
            customer_id  = customer_id,
            account_name = account_name,
            bank_name    = bank_name,
            ifsc_code    = ifsc_code,
            branch       = branch,
            account_type = account_type,
        )
        session.add(record)

    fields = {
        "account_no": account_no, "account_name": account_name,
        "bank_name": bank_name, "ifsc_code": ifsc_code,
        "branch": branch, "account_type": account_type,
    }
    return {"stored": True, "table": "bank_accounts", "record_id": account_no, "fields": fields}
