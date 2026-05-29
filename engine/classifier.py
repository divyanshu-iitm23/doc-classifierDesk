import re
from . import identifiers
from . import validators

W_PATTERN = 0.55
W_VALID = 0.30
W_KEYWORD = 0.15
DECISION_THRESHOLD = 0.60 

def _find_candidates(text: str, spec, doc_type):
    found = []
    target_len = spec["length"]
    shape = identifiers.SHAPES[doc_type]
    for m in spec["raw_regex"].finditer(text):
        raw = m.group(1)
        token = identifiers.normalise(raw)
        if spec["token_regex"].match(token):
            found.append((raw, token, False))
    if found:
        return found
    has_context = any(_kw_present(text.lower(), kw) for kw in spec["keywords"])
    if not has_context:
        return found
    for m in re.finditer(r"[A-Z0-9][A-Z0-9/.,|\\ -]{4,}[A-Z0-9]", text):
        run = re.sub(r"[/.,|\\ -]", "", m.group(0))  # strip internal junk
        if len(run) != target_len:
            continue
        repaired = identifiers.ocr_repair(run, shape)
        if spec["token_regex"].match(repaired):
            ok, _ = validators.validate(spec["validator"], repaired)
            if ok:
                found.append((m.group(0).strip(), repaired, True))
    return found


def _keyword_ratio(text_lower: str, keywords) -> float:
    if not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if _kw_present(text_lower, kw))
    return min(hits / 2.0, 1.0)


def _kw_present(text_lower: str, kw: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", text_lower) is not None


def score_document(text: str):
    text_upper = text.upper()
    text_lower = text.lower()

    results = []
    for doc_type, spec in identifiers.DOCUMENT_SPECS.items():
        candidates = _find_candidates(text_upper, spec, doc_type)
        pattern_hit = len(candidates) > 0
        best_token = None
        valid = False
        valid_reason = "no identifier found"
        repaired = False
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
            W_PATTERN * (1.0 if pattern_hit else 0.0)
            + W_VALID * (1.0 if valid else 0.0)
            + W_KEYWORD * kw_ratio
        )

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
    return results


def classify(text: str):
    ranked = score_document(text)
    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    if top["score"] < DECISION_THRESHOLD:
        decision = "UNKNOWN"
        needs_review = True
    else:
        decision = top["doc_type"]
        needs_review = bool(runner_up and (top["score"] - runner_up["score"]) < 0.15)

    return {
        "decision": decision,
        "display_name": top["display_name"] if decision != "UNKNOWN" else "Unknown / Needs Review",
        "confidence": top["score"],
        "identifier": top["identifier"] if decision != "UNKNOWN" else None,
        "identifier_valid": top["identifier_valid"] if decision != "UNKNOWN" else False,
        "needs_human_review": needs_review,
        "ranked": ranked,
    }
