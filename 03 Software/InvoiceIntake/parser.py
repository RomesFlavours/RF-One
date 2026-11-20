"""
Best-effort heuristic parsing of raw invoice text into header fields and
candidate line items.

This is intentionally simple (regex-based, no ML). It is meant to give the
user a head start, not a finished result. Every field it produces is shown
in an editable review form before anything is saved -- nothing here is
trusted blindly.
"""
import re

DATE_PATTERNS = [
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{4}-\d{2}-\d{2})\b",
]

DOC_NUMBER_PATTERNS = [
    r"invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    r"invoice\s*[:\-]?\s*#\s*([A-Za-z0-9\-]+)",
]

TOTAL_KEYWORDS = ["balance due", "total due", "amount due", "grand total", "total"]

MONEY = r"\$?\s?(\d{1,3}(?:[,.]\d{3})*(?:\.\d{2}))"

LINE_ITEM_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?P<desc>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"\$?\s?(?P<price>\d+(?:[,.]\d{3})*\.\d{2})\s+"
    r"\$?\s?(?P<amount>\d+(?:[,.]\d{3})*\.\d{2})\s*$"
)

SKIP_SUPPLIER_WORDS = {"invoice", "receipt", "bill", "fattura", "page", "bill to", "ship to"}


def _clean_number(raw: str) -> str:
    return raw.replace(",", "")


def guess_supplier(lines: list[str]) -> str:
    for line in lines[:8]:
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.lower() in SKIP_SUPPLIER_WORDS:
            continue
        if re.fullmatch(r"[\d\s\-+()]+", candidate):
            continue
        # strip a trailing email or phone number, keep the company name part
        candidate = re.sub(r"\s*\S+@\S+", "", candidate).strip()
        candidate = re.sub(r"\+?\d[\d\-\s()]{6,}$", "", candidate).strip()
        if candidate:
            return candidate
    return ""


def guess_document_number(text: str) -> str:
    for pat in DOC_NUMBER_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def guess_date(text: str) -> str:
    # Prefer a date on a line that explicitly mentions "invoice date"
    for line in text.splitlines():
        if "invoice date" in line.lower():
            for pat in DATE_PATTERNS:
                m = re.search(pat, line)
                if m:
                    return m.group(1)
    for pat in DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return ""


def guess_total(text: str) -> str:
    lines = text.splitlines()
    for keyword in TOTAL_KEYWORDS:
        for line in lines:
            if keyword in line.lower():
                m = re.search(MONEY, line)
                if m:
                    return _clean_number(m.group(1))
    # fallback: last money-looking number in the whole text
    all_amounts = re.findall(MONEY, text)
    if all_amounts:
        return _clean_number(all_amounts[-1])
    return ""


def guess_currency(text: str) -> str:
    if "$" in text or re.search(r"\busd\b", text, re.IGNORECASE):
        return "USD"
    if "€" in text or re.search(r"\beur\b", text, re.IGNORECASE):
        return "EUR"
    return ""


def parse_header(text: str) -> dict:
    lines = [l for l in text.splitlines()]
    return {
        "supplier_name": guess_supplier(lines),
        "document_number": guess_document_number(text),
        "issue_date": guess_date(text),
        "currency": guess_currency(text),
        "total_amount": guess_total(text),
    }


def parse_lines(text: str) -> list[dict]:
    candidates = []
    for raw_line in text.splitlines():
        m = LINE_ITEM_RE.match(raw_line.strip())
        if not m:
            continue
        candidates.append(
            {
                "description": m.group("desc").strip(),
                "quantity": m.group("qty"),
                "unit_price": _clean_number(m.group("price")),
                "line_amount": _clean_number(m.group("amount")),
            }
        )
    return candidates
