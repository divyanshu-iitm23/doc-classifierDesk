
import os

MIN_TEXT_CHARS = 20  # below this, assume it's a scan and switch to OCR


def _extract_text_layer(pdf_path: str) -> str:
    import pdfplumber
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            chunks.append(txt)
    return "\n".join(chunks)


def _extract_via_ocr(pdf_path: str, lang: str = "eng", dpi: int = 300) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            f"Install them, or supply a digital PDF. Original error: {e}"
        )
    images = convert_from_path(pdf_path, dpi=dpi)
    out = []
    for img in images:
        out.append(pytesseract.image_to_string(img, lang=lang))
    return "\n".join(out)


def extract_text(pdf_path: str, ocr_lang: str = "eng"):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)

    text = ""
    method = "text-layer"
    try:
        text = _extract_text_layer(pdf_path)
    except Exception:
        text = ""

    if len(text.strip()) < MIN_TEXT_CHARS:
        text = _extract_via_ocr(pdf_path, lang=ocr_lang)
        method = "ocr"

    return text, method
