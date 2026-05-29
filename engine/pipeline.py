import os
import time
from .extractor import extract_text
from .classifier import classify


def classify_pdf(pdf_path: str, ocr_lang: str = "eng") -> dict:
    started = time.time()
    base = os.path.basename(pdf_path)

    try:
        text, method = extract_text(pdf_path, ocr_lang=ocr_lang)
    except Exception as e:
        return {
            "file": base,
            "ok": False,
            "error": str(e),
            "decision": "ERROR",
        }

    result = classify(text)
    result.update({
        "file": base,
        "ok": True,
        "extraction_method": method,
        "chars_extracted": len(text),
        "elapsed_ms": int((time.time() - started) * 1000),
    })
    return result


def classify_folder(folder: str, ocr_lang: str = "eng"):
    out = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf"):
            out.append(classify_pdf(os.path.join(folder, name), ocr_lang=ocr_lang))
    return out
