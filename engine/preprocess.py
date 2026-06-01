"""
preprocess.py
-------------
The piece that makes OCR work on REAL documents instead of just clean text PDFs.

A real Aadhaar/PAN/passport scan is a photograph: coloured bands, a guilloche
security pattern in the background, a logo, a face photo, faded or low-contrast
ink, and often a few degrees of rotation. Tesseract does badly on that raw.

This module produces several cleaned-up VARIANTS of a page image. The extractor
OCRs each variant and the pipeline keeps whichever one yields a valid identifier —
so a preprocessing step that helps one document but hurts another can never make
the overall result worse. That "try several, keep the best" idea is the core trick.

Variants produced (cheap/best first, so early-exit fires fast):
  1. otsu          — grayscale + upscale + denoise + CLAHE + Otsu binarisation
  2. adaptive      — grayscale + upscale + adaptive (local) threshold
  3. gray_upscaled — grayscale + upscale + contrast only (no thresholding)
  4. deskewed_otsu — the otsu variant with rotation corrected
  5. raw           — the untouched image (sometimes the cleanest scans need nothing)
"""

import numpy as np
import cv2
from PIL import Image


# target long-edge resolution; small/low-DPI scans get upscaled to this
_TARGET_LONG_EDGE = 2200
_MAX_LONG_EDGE = 3500  # don't blow memory on already-huge images


def _to_gray(pil_img: Image.Image) -> np.ndarray:
    arr = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _upscale(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    long_edge = max(h, w)
    if long_edge < _TARGET_LONG_EDGE:
        scale = _TARGET_LONG_EDGE / long_edge
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_CUBIC)
    elif long_edge > _MAX_LONG_EDGE:
        scale = _MAX_LONG_EDGE / long_edge
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_AREA)
    return gray


def _denoise_and_contrast(gray: np.ndarray) -> np.ndarray:
    # light denoise to kill scan/JPEG speckle without smearing thin strokes
    den = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7,
                                   searchWindowSize=21)
    # CLAHE = local contrast boost; rescues faded ink and uneven lighting
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    return clahe.apply(den)


def _otsu(gray: np.ndarray) -> np.ndarray:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th


def _adaptive(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
        blockSize=31, C=15,
    )


def _deskew(binary: np.ndarray) -> np.ndarray:
    """Correct small page rotation. Conservative: only acts on 0.3-30 deg skew.
    If anything looks off, returns the input unchanged (the raw/otsu variants
    still cover the no-deskew case)."""
    try:
        inv = cv2.bitwise_not(binary)
        coords = np.column_stack(np.where(inv > 0))
        if len(coords) < 50:
            return binary
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if angle > 45:
            angle = angle - 90
        if abs(angle) < 0.3 or abs(angle) > 30:
            return binary
        h, w = binary.shape
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE, borderValue=255)
    except Exception:
        return binary


def _np_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr)


def _gentle(gray: np.ndarray) -> np.ndarray:
    """Upscale + mild sharpen, NO binarisation. Heavy thresholding can destroy
    the thin/stylised digit fonts used on Aadhaar and passport number lines;
    this variant keeps grayscale detail and often reads those numbers best."""
    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharp = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)
    return sharp


def ocr_variants(pil_img: Image.Image):
    """
    Yield (variant_name, PIL.Image) preprocessing variants, ordered best-first
    for card-style documents so the pipeline's early-exit triggers quickly.
    """
    gray = _to_gray(pil_img)
    gray = _upscale(gray)
    enhanced = _denoise_and_contrast(gray)

    otsu = _otsu(enhanced)
    adaptive = _adaptive(enhanced)
    deskewed = _deskew(otsu)
    gentle = _gentle(gray)

    # 'gentle' first: it preserves stylised number fonts (Aadhaar/passport) that
    # hard binarisation can smear, and tends to win the common cases fast.
    yield "gentle", _np_to_pil(gentle)
    yield "otsu", _np_to_pil(otsu)
    yield "adaptive", _np_to_pil(adaptive)
    yield "gray_upscaled", _np_to_pil(enhanced)
    yield "deskewed_otsu", _np_to_pil(deskewed)
    yield "raw", pil_img
