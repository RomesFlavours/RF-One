"""
OCR / text extraction engine for Invoice Intake.

Strategy:
- PDF: try to extract the embedded text layer first (fast, accurate, no OCR
  needed) using pdfplumber. If the PDF has no usable text layer (it's a
  scanned image), fall back to rendering pages to images and running
  Tesseract on them.
- Images (jpg/png/...): preprocess (grayscale, autocontrast, threshold) and
  run Tesseract OCR.

This is a best-effort extraction. Real-world photographed invoices are often
skewed, folded or low contrast, so OCR output will frequently need manual
correction in the review step. That review step is mandatory by design,
consistent with the Purchasing Module principle that human validation always
prevails over AI extraction.
"""
import io
import os

import pytesseract
from PIL import Image, ImageOps

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None


def _preprocess_image(img: Image.Image) -> Image.Image:
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.point(lambda x: 0 if x < 140 else 255)
    return img


def extract_from_image(path: str) -> str:
    img = Image.open(path)
    img = _preprocess_image(img)
    # Different page-segmentation modes pick up different parts of a
    # photographed invoice (headers/logos vs. tabular item lines). Try a
    # couple and keep whichever captured more text, rather than committing
    # to a single mode.
    candidates = []
    for psm in (6, 4, 11):
        try:
            candidates.append(pytesseract.image_to_string(img, config=f"--psm {psm}"))
        except Exception:
            continue
    if not candidates:
        return ""
    return max(candidates, key=lambda t: len(t.strip()))


def extract_from_pdf(path: str) -> tuple[str, str]:
    """Returns (text, method) where method is 'PDF-Text' or 'OCR'."""
    if pdfplumber is not None:
        try:
            with pdfplumber.open(path) as pdf:
                pages_text = [p.extract_text() or "" for p in pdf.pages]
            combined = "\n".join(pages_text).strip()
            if len(combined) > 40:
                return combined, "PDF-Text"
        except Exception:
            pass

    if convert_from_path is not None:
        try:
            images = convert_from_path(path)
            texts = []
            for img in images:
                img = _preprocess_image(img)
                texts.append(pytesseract.image_to_string(img, config="--psm 4"))
            return "\n".join(texts), "OCR"
        except Exception as exc:
            return f"(Impossibile leggere il PDF: {exc})", "OCR"

    return "(Nessun motore disponibile per leggere questo PDF)", "OCR"


def extract_text(path: str) -> tuple[str, str]:
    """Dispatch based on file extension. Returns (text, acquisition_method)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_from_pdf(path)
    return extract_from_image(path), "OCR"
