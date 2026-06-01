"""
Vastu Document Classification Engine
------------------------------------
Classifies Indian KYC documents (Aadhaar, PAN, Voter ID, Driving Licence,
Passport) from single-document PDFs by detecting and validating each document's
unique identifier.

Public API:
    from engine import classify_pdf, classify_folder, classify_text

    classify_pdf("aadhaar.pdf")        -> result dict
    classify_folder("samples/")        -> list of result dicts
"""

from .pipeline import classify_file, classify_pdf, classify_folder
from .classifier import classify as classify_text

__all__ = ["classify_file", "classify_pdf", "classify_folder", "classify_text"]
__version__ = "2.0.0"
