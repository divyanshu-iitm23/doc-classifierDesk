"""
pipeline.py
-----------
End-to-end orchestrator: a file path goes in, a structured classification
result comes out.

Real-document strategy ("try several, keep the best"):
  - Ask the extractor for text candidates (text layer first, then OCR variants).
  - Classify each candidate as it arrives.
  - EARLY-EXIT the moment we get a confident result backed by a VALID identifier
    (so clean digital PDFs finish in milliseconds and good scans finish after the
    first decent OCR variant).
  - If nothing hits that bar, return the highest-scoring result we saw, so the
    caller still gets the engine's best guess (often flagged for human review).

This is what makes the engine robust on messy real cards: a preprocessing
variant that fails is simply skipped in favour of one that works.
"""

import os
import time

from .extractor import text_candidates, IMAGE_EXTS
from .classifier import classify

# A result we're happy to stop on: clearly above threshold AND the identifier
# passed its checksum/structure check.
_EARLY_EXIT_CONFIDENCE = 0.70

# If the digital text layer has at least this many characters, we treat it as a
# genuine text PDF: if it doesn't classify, OCR won't help, so we skip OCR.
_RICH_TEXT_LAYER = 80


def classify_file(path: str, ocr_lang: str = "eng", ocr: bool = True,
                  lenient: bool = False) -> dict:
    """Classify a single document (PDF or image). Never raises on bad input -
    returns an error result so batch runs don't crash on one bad file.

    lenient=True relaxes validation for testing with dummy documents."""
    started = time.time()
    base = os.path.basename(path)

    best = None
    best_method = None
    tried = 0

    try:
        for text, method in text_candidates(path, ocr_lang=ocr_lang, ocr=ocr):
            tried += 1
            result = classify(text, lenient=lenient)

            if best is None or result["confidence"] > best["confidence"]:
                best = result
                best_method = method

            # early exit on a confident, validated hit (strict mode), or a
            # confident shape match (lenient mode).
            confident = result["confidence"] >= _EARLY_EXIT_CONFIDENCE
            if confident and (result["identifier_valid"] or lenient):
                best = result
                best_method = method
                break

            # if the digital text layer was rich (a real text PDF) and it still
            # didn't classify, OCR won't do better - stop here instead of burning
            # ~20s OCR-ing a document that simply isn't one of our 5 types.
            if method == "text-layer" and len(text.strip()) >= _RICH_TEXT_LAYER:
                break
    except Exception as e:
        return {"file": base, "ok": False, "error": str(e), "decision": "ERROR"}

    if best is None:
        return {
            "file": base, "ok": False, "decision": "ERROR",
            "error": "no text could be extracted (empty or unreadable document)",
        }

    best.update({
        "file": base,
        "ok": True,
        "extraction_method": best_method,
        "candidates_tried": tried,
        "elapsed_ms": int((time.time() - started) * 1000),
    })
    return best


# backwards-compatible alias (older code/imports called it classify_pdf)
def classify_pdf(path: str, ocr_lang: str = "eng", ocr: bool = True,
                 lenient: bool = False) -> dict:
    return classify_file(path, ocr_lang=ocr_lang, ocr=ocr, lenient=lenient)


def classify_folder(folder: str, ocr_lang: str = "eng", ocr: bool = True,
                    lenient: bool = False):
    """Classify every PDF/image in a folder. Returns a list of results."""
    out = []
    exts = {".pdf"} | IMAGE_EXTS
    for name in sorted(os.listdir(folder)):
        if os.path.splitext(name)[1].lower() in exts:
            out.append(classify_file(os.path.join(folder, name), ocr_lang=ocr_lang,
                                     ocr=ocr, lenient=lenient))
    return out
