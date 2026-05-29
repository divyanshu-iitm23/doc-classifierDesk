from .pipeline import classify_pdf, classify_folder
from .classifier import classify as classify_text

__all__ = ["classify_pdf", "classify_folder", "classify_text"]
__version__ = "1.0.0"
