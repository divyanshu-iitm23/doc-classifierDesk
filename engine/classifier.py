"""
classifier.py
-------------
Given the raw text of ONE document, decide which of the five Indian KYC types
it is, and how confident we are.

The "intelligence" is a multi-signal confidence model. For each candidate type:

    score =  0.55 * (a structurally-shaped identifier was found)
          +  0.30 * (that identifier passed validation / checksum)
          +  0.15 * (fraction of expected context keywords present)

The type with the highest score wins. If even the best score is below
DECISION_THRESHOLD, we return UNKNOWN and route to a human — which is exactly
the human-in-the-loop behaviour the BRD's Classification + HITL engines call for.

Why this design beats naive pattern matching:
  - A bank statement with a 12-digit account number will match the Aadhaar
    *pattern* (0.55) but FAIL the Verhoeff checksum (no +0.30) and carry no
    Aadhaar keywords (no +0.15) -> it won't be misclassified as Aadhaar.
  - A real Aadhaar scan scores pattern + checksum + keywords -> ~0.85-1.0.
"""

import re
from . import identifiers
from . import validators

# Weights (strict mode — production default)
W_PATTERN = 0.55
W_VALID = 0.30
W_KEYWORD = 0.15

# A bare pattern match scores W_PATTERN (0.55). We deliberately set the bar just
# above that, so a pattern alone is NOT enough — it must be corroborated by either
# a passed validation (+0.30) or context keywords (+up to 0.15). This is what keeps
# a 12-digit bank-account number from being mistaken for an Aadhaar number.
DECISION_THRESHOLD = 0.60  # below this -> UNKNOWN / human review

# Lenient mode (for TESTING with dummy/fabricated documents, where the checksum
# can't pass and OCR may garble the headers so keywords don't match). It classifies
# on the identifier SHAPE alone, without requiring a valid checksum or keywords.
# A correctly-shaped identifier scores ~0.80 here, comfortably above the lenient bar.
# NOT for production — a fabricated Aadhaar number will be accepted in this mode.
W_PATTERN_LENIENT = 0.80
LENIENT_THRESHOLD = 0.60

# --- Bank documents (statement / passbook) -----------------------------------
# Bank docs are scored differently: there is no unique-format ID to validate, so
# we combine "is this a bank document at all" (IFSC present + generic bank words)
# with "which kind" (distinctive statement vs passbook phrases).
#   bank_context = IFSC found (0.45) OR >=2 generic bank keywords (0.30)
#   type_signal  = up to 0.55 from the fraction of distinctive phrases matched
# A doc with an IFSC + a couple of "statement"/"passbook" phrases lands ~0.8-1.0.
WB_IFSC = 0.45
WB_KEYWORDS = 0.30          # generic bank keywords (capped contribution)
WB_DISTINCTIVE = 0.55       # distinctive statement/passbook phrases
# Minimum evidence to even be considered a bank document (else it's not bank).
WB_MIN_BANK_CONTEXT = 0.30


def _find_candidates(text: str, spec, doc_type, lenient: bool = False):
    """
    Return list of (raw_match, token, repaired_bool) for one document type.

    Pass 1 — strict: the identifier appears cleanly (allowing only space/hyphen
             grouping) and matches the exact shape.
    Pass 2 — fuzzy (OCR repair): pull every alphanumeric run of the right length,
             strip stray internal punctuation, and coerce OCR-confused glyphs
             toward the expected shape. In strict mode a repaired token is kept
             only if it then VALIDATES (so repair can't invent a false positive);
             in lenient mode a shape-matching repaired token is kept even if the
             checksum fails (for testing with dummy/fabricated numbers).
    """
    found = []
    target_len = spec["length"]
    shape = identifiers.SHAPES.get(doc_type)

    # ---- Pass 1: strict ----
    for m in spec["raw_regex"].finditer(text):
        raw = m.group(1)
        token = identifiers.normalise(raw)
        if spec["token_regex"].match(token):
            found.append((raw, token, False))
    if found:
        return found

    # ---- Pass 2: fuzzy OCR repair ----
    # Skip if the document type has no single shape (e.g. PASSPORT with two
    # possible formats) — repair needs a fixed shape to coerce toward.
    if shape is None:
        return found

    # GUARD (strict only): a repaired token is trusted only if the document also
    # carries a context keyword for THIS type, so a misread date can't become a
    # fake passport number. In lenient mode (dummy-doc testing) we drop this guard.
    has_context = any(_kw_present(text.lower(), kw) for kw in spec["keywords"])
    if not has_context and not lenient:
        return found

    # 2a) Aadhaar-specific: OCR frequently mis-spaces the 4-4-4 grouping
    # (e.g. "71442 2817 9457"). Pull any window of 12 digits while ignoring
    # internal whitespace. In strict mode keep it only if Verhoeff-valid; in
    # lenient mode keep any clean 12-digit window.
    if doc_type == "AADHAAR":
        for m in re.finditer(r"(?<!\d)(?:\d[ \t]*){12}(?!\d)", text):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) == 12:
                ok, _ = validators.validate(spec["validator"], digits)
                if ok or lenient:
                    found.append((m.group(0).strip(), digits, True))
        if found:
            return found

    for m in re.finditer(r"[A-Z0-9][A-Z0-9/.,|\\ -]{4,}[A-Z0-9]", text):
        run = re.sub(r"[/.,|\\ -]", "", m.group(0))  # strip internal junk
        if len(run) != target_len:
            continue
        repaired = identifiers.ocr_repair(run, shape)
        if spec["token_regex"].match(repaired):
            ok, _ = validators.validate(spec["validator"], repaired)
            if ok or lenient:
                found.append((m.group(0).strip(), repaired, True))
    return found


def _keyword_ratio(text_lower: str, keywords) -> float:
    if not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if _kw_present(text_lower, kw))
    # saturate quickly: 2+ keyword hits already counts as full context signal
    return min(hits / 2.0, 1.0)


def _kw_present(text_lower: str, kw: str) -> bool:
    """Word-boundary keyword match so short tokens like 'ind' don't match 'india'."""
    return re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text_lower) is not None


def _count_phrases(text_lower: str, phrases):
    """Return (matched_list, fraction) of phrases present (word-boundary aware)."""
    matched = [p for p in phrases if _kw_present(text_lower, p)]
    # saturate: 3+ distinctive phrases already counts as full type signal
    frac = min(len(matched) / 3.0, 1.0)
    return matched, frac


# Bank-document marker phrases that essentially NEVER appear on the 5 ID cards.
# Deliberately excludes "account number" (a PAN card says "Permanent Account
# Number") and other ID-ambiguous terms. Used only to detect "this is a bank
# document" so coincidental ID-number matches can be suppressed.
_BANK_MARKERS = [
    "ifsc", "ifs code", "micr", "savings bank", "passbook", "pass book",
    "customer id", "customer name", "cif", "a/c no", "account no",
    "withdrawal", "deposit", "branch", "neft", "rtgs", "cheque",
    "closing balance", "opening balance", "available balance",
    "payable at par", "valid for three months", "statement of account",
    "account holder", "or bearer", "transaction", "current account",
]

def _bank_marker_count(text_lower: str) -> int:
    """How many distinct bank-document markers are present (word-boundary aware)."""
    return sum(1 for m in _BANK_MARKERS if _kw_present(text_lower, m))


# Receipt-document markers that essentially never appear on the 5 ID cards.
# Used (together with bank markers) to suppress ID-card false positives on
# invoices / insurance receipts / road-tax receipts.
_RECEIPT_MARKERS = [
    "tax invoice", "invoice", "invoice no", "hsn", "sac", "cgst", "sgst", "igst",
    "taxable value", "gstin", "place of supply", "e-invoice",
    "policy", "premium", "sum insured", "sum assured", "insurer", "irdai",
    "policyholder", "insurance",
    "road tax", "motor vehicle tax", "mv tax", "rto", "transport department",
    "tax token", "chassis", "engine number", "registration number", "vahan",
]

def _receipt_marker_count(text_lower: str) -> int:
    """How many distinct receipt-document markers are present (word-boundary aware)."""
    return sum(1 for m in _RECEIPT_MARKERS if _kw_present(text_lower, m))


def _count_transaction_rows(text: str) -> int:
    """
    Count lines that look like a bank-statement transaction row: a date together
    with a monetary amount on the same line. This is the structural fingerprint of
    a STATEMENT (many such rows) and is absent on a cheque or a passbook cover —
    which is the most OCR-robust way to tell them apart, since it survives even
    when the header phrases are garbled.

    Matches dates like 03-04-2026, 03/04/26, 03.04.2026 AND an amount like
    1,200.00 / 45000.00 / 1,06,320.00 on the same physical line.
    """
    date_re = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
    amount_re = re.compile(r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\b|\b\d{3,}\.\d{2}\b")
    rows = 0
    for line in text.splitlines():
        if date_re.search(line) and amount_re.search(line):
            rows += 1
    return rows


# how strongly a transaction table pulls toward STATEMENT / away from cheque+passbook
WB_TXN_TABLE = 0.45          # statement gets this when >=4 transaction rows seen
TXN_ROWS_FOR_STATEMENT = 4   # rows needed to call it a real transaction table


def _score_bank(text_upper, text_lower, doc_type, spec, lenient=False, txn_rows=0):
    """
    Scoring path for bank documents (statement / passbook / cheque).

    Step 1 - is this a bank document at all? Look for an IFSC (validated) and/or
             generic bank keywords. If neither, this type scores ~0.
    Step 2 - which kind? Combine:
             (a) distinctive phrases for the type, and
             (b) the transaction-table signal: a statement HAS a dated-amount
                 table (many rows); a cheque/passbook does NOT. This is the
                 user-identified discriminator and the most OCR-robust one.
    """
    # find an IFSC (shared identifier). Pass 1 strict, Pass 2 OCR-repair.
    candidates = _find_candidates(text_upper, spec, doc_type, lenient=lenient)
    ifsc_token = None
    ifsc_valid = False
    ifsc_reason = "no IFSC found"
    repaired = False
    for raw, token, was_repaired in candidates:
        ok, reason = validators.validate(spec["validator"], token)
        if ok:
            ifsc_token, ifsc_valid, ifsc_reason, repaired = token, True, reason, was_repaired
            break
    if ifsc_token is None and candidates:
        ifsc_token = candidates[0][1]
        repaired = candidates[0][2]
        _, ifsc_reason = validators.validate(spec["validator"], ifsc_token)

    # generic bank context keywords (shared across all bank docs)
    bank_kw, bank_kw_frac = _count_phrases(text_lower, spec["keywords"])

    bank_context = max(
        WB_IFSC if ifsc_valid else 0.0,
        WB_KEYWORDS * bank_kw_frac,
    )
    if ifsc_valid and bank_kw_frac > 0:
        bank_context = min(WB_IFSC + 0.15 * bank_kw_frac, 0.60)

    # distinctive type phrases
    distinctive, dist_frac = _count_phrases(text_lower, spec["distinctive"])

    # transaction-table signal (the user's discriminator)
    has_table = txn_rows >= TXN_ROWS_FOR_STATEMENT
    table_signal = 0.0
    if doc_type == "BANK_STATEMENT":
        # a real transaction table is strong positive evidence for a statement
        table_signal = WB_TXN_TABLE if has_table else 0.0
    else:
        # cheque / passbook: a transaction table argues AGAINST this type
        table_signal = -WB_TXN_TABLE if has_table else 0.0

    if bank_context < WB_MIN_BANK_CONTEXT and not lenient:
        score = 0.0
    else:
        score = bank_context + WB_DISTINCTIVE * dist_frac + table_signal
        score = max(0.0, min(score, 1.0))

    return {
        "doc_type": doc_type,
        "display_name": spec["display_name"],
        "score": round(score, 4),
        "identifier": ifsc_token,
        "identifier_valid": ifsc_valid,
        "validation_reason": ifsc_reason,
        "ocr_repaired": repaired,
        "pattern_found": ifsc_token is not None,
        "keyword_ratio": round(dist_frac, 3),
        "matched_keywords": distinctive,
        "transaction_rows": txn_rows,
    }


# --- Receipt-class documents (invoice / insurance / road-tax) ----------------
# No single rigid identifier, so scored by distinctive phrases, with an optional
# structured anchor (GSTIN for invoice, vehicle-reg for road tax). Insurance has
# no anchor and is phrase-only.
#   type_signal = up to 0.75 from the fraction of distinctive phrases (saturate at 3)
#   anchor      = 0.35 when a valid GSTIN / vehicle-reg is found
# A doc with a valid anchor + 2 distinctive phrases lands ~0.85; 3 phrases alone
# (the insurance case) lands 0.75 — both above the 0.60 decision threshold.
WR_TYPE = 0.75
WR_ANCHOR = 0.35


def _score_receipt(text_upper, text_lower, doc_type, spec):
    """Scoring path for receipt-class documents (invoice / insurance / road-tax)."""
    distinctive, dist_frac = _count_phrases(text_lower, spec["distinctive"])

    # optional structured anchor (GSTIN / vehicle registration)
    anchor_token = None
    anchor_valid = False
    anchor_reason = "no anchor for this type"
    anchor_re = spec.get("anchor_regex")
    if anchor_re is not None:
        anchor_reason = "no anchor found"
        for m in anchor_re.finditer(text_upper):
            tok = re.sub(r"[\s-]", "", m.group(1)).upper()
            ok, reason = validators.validate(spec["anchor_validator"], tok)
            if ok:
                anchor_token, anchor_valid, anchor_reason = tok, True, reason
                break
            if anchor_token is None:
                anchor_token, anchor_reason = tok, reason

    anchor_signal = WR_ANCHOR if anchor_valid else 0.0
    type_signal = WR_TYPE * dist_frac

    # require minimum evidence so a single stray phrase can't classify a document
    if not anchor_valid and len(distinctive) == 0:
        score = 0.0
    elif not anchor_valid and len(distinctive) == 1:
        score = min(type_signal, 0.40)        # one phrase alone is too weak
    else:
        score = min(anchor_signal + type_signal, 1.0)

    return {
        "doc_type": doc_type,
        "display_name": spec["display_name"],
        "score": round(score, 4),
        "identifier": anchor_token,
        "identifier_valid": anchor_valid,
        "validation_reason": anchor_reason,
        "ocr_repaired": False,
        "pattern_found": anchor_token is not None,
        "keyword_ratio": round(dist_frac, 3),
        "matched_keywords": distinctive,
    }


def score_document(text: str, lenient: bool = False):
    """
    Score the text against every document type.
    Returns a sorted list of result dicts (highest score first).

    lenient=True scores on identifier SHAPE alone (no checksum/keyword needed) —
    use it only for testing with dummy documents, never in production.
    """
    # uppercase copy for identifier matching (PAN/DL/etc. are uppercase);
    # lowercase copy for keyword matching.
    text_upper = text.upper()
    text_lower = text.lower()

    w_pattern = W_PATTERN_LENIENT if lenient else W_PATTERN

    # transaction-table row count is computed once and shared across the bank types
    txn_rows = _count_transaction_rows(text)

    results = []
    for doc_type, spec in identifiers.DOCUMENT_SPECS.items():
        # Bank documents use a separate scoring path (IFSC + distinctive phrases +
        # transaction-table signal); the 5 ID-card types keep their original
        # identifier-based logic untouched.
        if doc_type in identifiers.BANK_TYPES:
            results.append(_score_bank(text_upper, text_lower, doc_type, spec,
                                       lenient=lenient, txn_rows=txn_rows))
            continue

        # Receipt documents (invoice / insurance / road-tax): phrase-based scoring
        # with an optional structured anchor. Also separate from the ID-card path.
        if doc_type in identifiers.RECEIPT_TYPES:
            results.append(_score_receipt(text_upper, text_lower, doc_type, spec))
            continue

        candidates = _find_candidates(text_upper, spec, doc_type, lenient=lenient)

        pattern_hit = len(candidates) > 0
        best_token = None
        valid = False
        valid_reason = "no identifier found"
        repaired = False

        # pick the first candidate that validates; else keep the first found
        for raw, token, was_repaired in candidates:
            ok, reason = validators.validate(spec["validator"], token)
            if ok:
                best_token, valid, valid_reason, repaired = token, True, reason, was_repaired
                break
        if best_token is None and candidates:
            best_token = candidates[0][1]
            repaired = candidates[0][2]
            _, valid_reason = validators.validate(spec["validator"], best_token)

        kw_ratio = _keyword_ratio(text_lower, spec["keywords"])
        matched_keywords = [kw for kw in spec["keywords"] if _kw_present(text_lower, kw)]

        score = (
            w_pattern * (1.0 if pattern_hit else 0.0)
            + W_VALID * (1.0 if valid else 0.0)
            + W_KEYWORD * kw_ratio
        )
        score = min(score, 1.0)

        results.append({
            "doc_type": doc_type,
            "display_name": spec["display_name"],
            "score": round(score, 4),
            "identifier": best_token,
            "identifier_valid": valid,
            "validation_reason": valid_reason,
            "ocr_repaired": repaired,
            "pattern_found": pattern_hit,
            "keyword_ratio": round(kw_ratio, 3),
            "matched_keywords": matched_keywords,
        })

    results.sort(key=lambda r: r["score"], reverse=True)

    # --- Document-context gate (suppress ID-card false positives) -------------
    # A bank/receipt document is full of long numbers (account, CIF, GSTIN, policy,
    # chassis, transaction amounts) and OCR invents more from noise. A random
    # 12-digit string passes the Aadhaar Verhoeff checksum ~10% of the time, so on
    # almost any such document SOME number will coincidentally "validate" as an
    # Aadhaar (or DL/PAN/etc.). Since a real ID card never carries bank/invoice/
    # insurance/road-tax wording, the presence of >=2 such markers means any
    # ID-card match here is a coincidental number collision — so we cap ID-card
    # scores below the decision threshold. (Bank and receipt types are exempt.)
    # This also stops the pipeline early-exiting on a false Aadhaar before it
    # reaches the variant that reads the real document correctly.
    non_id_context = (_bank_marker_count(text_lower) >= 2
                      or _receipt_marker_count(text_lower) >= 2)
    if non_id_context:
        for r in results:
            if (r["doc_type"] not in identifiers.BANK_TYPES
                    and r["doc_type"] not in identifiers.RECEIPT_TYPES):
                r["score"] = round(min(r["score"], 0.40), 4)
                r["suppressed_by_doc_context"] = True
        results.sort(key=lambda r: r["score"], reverse=True)

    # Safeguard against ID-card false positives on bank documents.
    # A cheque/statement carries an IFSC and an MICR line; the 15-digit MICR or a
    # cheque number can be misread as a DL/passport number (which then "validates"
    # structurally). So: if any bank type found a VALID IFSC, a bank document is
    # almost certainly what this is — it should not lose to an ID-card type that
    # rests only on a number match. Promote the best bank candidate when it has
    # real bank evidence (valid IFSC, or >=2 distinctive phrases) and is within
    # reach of the top card hit.
    top = results[0]
    if top["doc_type"] not in identifiers.BANK_TYPES:
        best_bank = next((r for r in results if r["doc_type"] in identifiers.BANK_TYPES), None)
        if best_bank is not None:
            bank_has_ifsc = best_bank.get("identifier_valid", False)
            bank_has_phrases = len(best_bank["matched_keywords"]) >= 2
            card_is_flimsy = not top["identifier_valid"]
            # promote the bank type if either:
            #  - the top card hit is a flimsy (unvalidated) number match, OR
            #  - the bank doc has an unmistakable valid IFSC (real bank document)
            if (bank_has_ifsc or bank_has_phrases) and \
               (card_is_flimsy or bank_has_ifsc) and \
               best_bank["score"] >= top["score"] - 0.20:
                results.remove(best_bank)
                results.insert(0, best_bank)

    return results


def classify(text: str, lenient: bool = False):
    """
    Top-level classification for one document's text.
    Returns the winning result plus the full ranked breakdown.

    lenient=True relaxes validation for testing with dummy documents.
    """
    ranked = score_document(text, lenient=lenient)
    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    threshold = LENIENT_THRESHOLD if lenient else DECISION_THRESHOLD

    if top["score"] < threshold:
        decision = "UNKNOWN"
        needs_review = True
    else:
        decision = top["doc_type"]
        # ambiguity check: if the runner-up is very close, flag for review
        needs_review = bool(runner_up and (top["score"] - runner_up["score"]) < 0.15)

    return {
        "decision": decision,
        "display_name": top["display_name"] if decision != "UNKNOWN" else "Unknown / Needs Review",
        "confidence": top["score"],
        "identifier": top["identifier"] if decision != "UNKNOWN" else None,
        "identifier_valid": top["identifier_valid"] if decision != "UNKNOWN" else False,
        "needs_human_review": needs_review,
        "lenient_mode": lenient,
        "ranked": ranked,
    }
