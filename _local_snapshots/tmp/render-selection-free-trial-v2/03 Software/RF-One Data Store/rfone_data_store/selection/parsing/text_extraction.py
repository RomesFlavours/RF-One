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

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    import docx as _python_docx
except ImportError:  # pragma: no cover - optional dependency
    _python_docx = None

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt")


def extract_text_from_pdf(path: str) -> str | None:
    """Best-effort embedded-text extraction. Returns None (never raises) if
    `pdfplumber` is unavailable or the PDF has no usable text layer —
    callers must treat that as "extraction unavailable," not as an empty
    résumé. A scanned/image-only PDF has no embedded text layer and is
    intentionally NOT OCR'd here (task §2: "scanned/image-only PDF handling
    may return an explicit 'no extractable text' result for now")."""

    if pdfplumber is None:
        return None
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = [p.extract_text() or "" for p in pdf.pages]
        combined = "\n".join(pages_text).strip()
        return combined or None
    except Exception:
        return None


def extract_text_from_docx(path: str) -> str | None:
    """Best-effort DOCX paragraph extraction (including table cell text, a
    common résumé layout choice). Returns None (never raises) if
    `python-docx` is unavailable or the file cannot be read as a DOCX."""

    if _python_docx is None:
        return None
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
