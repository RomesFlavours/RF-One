"""Résumé text extraction (TASK_SELECTION_002; formats extended by Task 2A).
Real, deterministic text extraction (not AI) — mirrors `03 Software/
InvoiceIntake/ocr_engine.py`'s "try the embedded PDF text layer first"
strategy, using the same `pdfplumber` dependency where available, so an
uploaded résumé's raw text is genuine regardless of which parser (real AI or
the rule-based fallback — see `resolve.py`) ultimately structures it (task
§18: never disguise mock parsing as real — extracting the actual text of a
real upload is not mock, and is shown to the evaluator as Evidence
regardless of parsing mode).

One function per supported format (task §5: "Keep extraction and parsing
sufficiently separated so later improvements can replace either component
without rewriting the whole import pipeline") — `extract_text(path, ext)` is
the single dispatch point callers should use.
"""

from __future__ import annotations

import threading

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    import docx as _python_docx
except ImportError:  # pragma: no cover - optional dependency
    _python_docx = None

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")
_ocr_reader = None
_ocr_lock = threading.Lock()


class TextExtractionError(RuntimeError):
    """Missing reader, distinct from a document without a text layer."""


def require_readers() -> None:
    missing = [name for name, reader in (("pdfplumber", pdfplumber),
                                         ("python-docx", _python_docx)) if reader is None]
    if missing:
        raise TextExtractionError("Lettori CV non disponibili nel server: " + ", ".join(missing)
                                  + ". Installare le dipendenze di Selection e riavviare il server.")


def _ocr_page(path: str, index: int) -> str:
    """Local OCR for a page with no embedded text; never changes the original."""
    global _ocr_reader
    try:
        import numpy as np
        import pypdfium2 as pdfium
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise TextExtractionError("Lettore OCR locale non disponibile nel server. Installare le dipendenze di Selection.") from exc
    with _ocr_lock:
        if _ocr_reader is None:
            _ocr_reader = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        document = pdfium.PdfDocument(path)
        try:
            page = document[index]
            try:
                bitmap = page.render(scale=2.5)
                try:
                    pixels = np.array(bitmap.to_pil().convert('RGB'))
                finally:
                    bitmap.close()
            finally:
                page.close()
            result, _ = _ocr_reader(pixels)
            return '\n'.join(line[1] for line in (result or []))
        finally:
            document.close()


def extract_text_from_pdf(path: str) -> str | None:
    """Read embedded text first, then local OCR for image-only pages.

    Missing readers raise TextExtractionError; an empty document returns None.
    """

    if pdfplumber is None:
        raise TextExtractionError("Lettore PDF non disponibile nel server (pdfplumber). Il problema non riguarda il CV.")
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for index, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if not text.strip() and page.images:
                    text = _ocr_page(path, index)
                pages_text.append(text)
        combined = "\n".join(pages_text).strip()
        return combined or None
    except TextExtractionError:
        raise
    except Exception:
        import logging
        logging.getLogger(__name__).exception("PDF text extraction failed")
        return None


def extract_text_from_docx(path: str) -> str | None:
    """Best-effort DOCX paragraph extraction (including table cell text, a
    common résumé layout choice). A missing reader raises TextExtractionError;
    an unreadable DOCX returns None."""

    if _python_docx is None:
        raise TextExtractionError("Lettore DOCX non disponibile nel server (python-docx). Il problema non riguarda il CV.")
    try:
        document = _python_docx.Document(path)
        parts = [p.text for p in document.paragraphs if p.text and p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text)
        combined = "\n".join(parts).strip()
        return combined or None
    except Exception:
        return None


def extract_text_from_txt(path: str) -> str | None:
    """Safe plain-text decoding. Tries UTF-8 (with/without BOM) first, then
    falls back to Latin-1, which never raises on arbitrary bytes — so an
    unusual encoding degrades to imperfect characters rather than a failed
    import. Returns None only if the file is empty/whitespace-only."""

    raw_bytes = None
    try:
        with open(path, "rb") as f:
            raw_bytes = f.read()
    except OSError:
        return None

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        text = raw_bytes.decode("latin-1")

    text = text.strip()
    return text or None


def extract_text(path: str, ext: str) -> str | None:
    """Single dispatch point: extension (lowercase, with leading dot) ->
    the appropriate extractor. Returns None for an unsupported extension —
    callers must check `SUPPORTED_EXTENSIONS` before calling if they need to
    distinguish "unsupported format" from "supported but empty."""

    if ext == ".pdf":
        return extract_text_from_pdf(path)
    if ext == ".docx":
        return extract_text_from_docx(path)
    if ext == ".txt":
        return extract_text_from_txt(path)
    return None
