"""
extractor.py
------------
Turns a PDF (or an image file) into one or more TEXT CANDIDATES for the
classifier to try.

Strategies, cheapest first:
  1. DIGITAL TEXT LAYER  - pdfplumber reads embedded text (instant, exact).
  2. OCR + PREPROCESSING - render each page at high DPI, then run Tesseract over
                           several cleaned-up image variants (see preprocess.py)
                           with two page-segmentation modes.

The extractor doesn't decide which candidate is "right" - it returns all of them
and lets the pipeline classify each and keep the best. This is what lets the
engine handle real documents: one of the preprocessing variants will usually
produce text clean enough for the identifier to be detected and validated.

Also accepts image inputs (.jpg/.png/.tiff/.bmp/.webp) directly, since real
documents are often phone photos rather than PDFs.
"""

import os

MIN_TEXT_CHARS = 25          # a text layer thinner than this is treated as "no text"
OCR_RENDER_DPI = 400         # real cards need high DPI to resolve the number font
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

# Tesseract page-segmentation modes worth trying for ID documents:
#   6 = assume a single uniform block of text  (good for cropped cards)
#   3 = fully automatic page segmentation       (good for full-page scans)
_PSM_MODES = (6, 3)


# -----------------------------------------------------------------------------
# digital text layer
# -----------------------------------------------------------------------------
def _extract_text_layer(pdf_path: str) -> str:
    import pdfplumber
    chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text() or "")
    except Exception:
        return ""
    return "\n".join(chunks)


# -----------------------------------------------------------------------------
# page rendering (PDF -> PIL images)
# -----------------------------------------------------------------------------
def _render_pdf_pages(pdf_path: str, dpi: int):
    from pdf2image import convert_from_path
    return convert_from_path(pdf_path, dpi=dpi)


def _load_image(image_path: str):
    from PIL import Image
    return [Image.open(image_path)]


# -----------------------------------------------------------------------------
# OCR over preprocessing variants
# -----------------------------------------------------------------------------
def _ocr_image_variants(pil_img, lang: str):
    """Yield (text, method_label) for each preprocessing variant x PSM mode."""
    import pytesseract
    from .preprocess import ocr_variants

    for variant_name, variant_img in ocr_variants(pil_img):
        for psm in _PSM_MODES:
            config = f"--oem 3 --psm {psm}"
            try:
                text = pytesseract.image_to_string(variant_img, lang=lang, config=config)
            except Exception:
                continue
            if text and text.strip():
                yield text, f"ocr:{variant_name}/psm{psm}"


def _pick_lang(requested: str) -> str:
    """Use the requested language(s) if the packs are installed; else fall back
    to 'eng'. Identifiers are Latin, so 'eng' alone still reads the number."""
    try:
        import pytesseract
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    wanted = [l for l in requested.split("+") if l]
    usable = [l for l in wanted if l in available]
    return "+".join(usable) if usable else "eng"


# -----------------------------------------------------------------------------
# public API
# -----------------------------------------------------------------------------
def text_candidates(path: str, ocr_lang: str = "eng", ocr: bool = True):
    """
    Generator of (text, method) candidates for `path`.

    For a PDF with a good text layer, the first candidate is usually enough and
    the pipeline early-exits before any OCR runs. For a scanned/photo document,
    this yields the preprocessing-variant OCR results.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    ext = os.path.splitext(path)[1].lower()
    is_image = ext in IMAGE_EXTS

    # 1) digital text layer (PDF only)
    if not is_image:
        layer = _extract_text_layer(path)
        if len(layer.strip()) >= MIN_TEXT_CHARS:
            yield layer, "text-layer"

    if not ocr:
        return

    # 2) OCR path - render pages (or load the image) then OCR variants
    lang = _pick_lang(ocr_lang)
    try:
        pages = _load_image(path) if is_image else _render_pdf_pages(path, OCR_RENDER_DPI)
    except Exception as e:
        raise RuntimeError(
            "Could not render the file for OCR. For PDFs this needs Poppler "
            "(`sudo apt install poppler-utils`); OCR needs Tesseract "
            f"(`sudo apt install tesseract-ocr`). Original error: {e}"
        )

    for page_img in pages:
        for text, method in _ocr_image_variants(page_img, lang):
            yield text, method
