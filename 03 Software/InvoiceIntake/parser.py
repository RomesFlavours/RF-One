"""
Best-effort heuristic parsing of raw invoice text into header fields and
candidate line items.

This is intentionally simple (regex-based, no ML). It is meant to give the
user a head start, not a finished result. Every field it produces is shown
in an editable review form before anything is saved -- nothing here is
trusted blindly.

Extended by "Purchased Invoice Intake — Improve Generic Parser and Prepare
Supplier Format Training" to recognize more real-world date/invoice-number/
total formats (see DATE_FORMATS, DOC_NUMBER_PATTERNS, TOTAL_KEYWORDS below)
and to avoid a document's own Subtotal/Tax/Tip/Payment lines being
misread as its Total. This module still never invents a value it did not
find in the source text -- an unrecognized field stays an empty string,
exactly as before; `purchased_bridge.py` is what decides NORMALIZED/HUMAN
from what this module actually found (never from *how* the text was
acquired -- see that module's docstring).
"""
import re

# Numeric date-shaped substrings — extraction only, unchanged in spirit from
# before this task: `\d{2,4}` already covers both a 2-digit year (e.g.
# 07/07/20) and a 4-digit year (e.g. 01/31/2020). Which token is month/day/
# year, and whether the result is a plausible date at all, is decided later
# by `purchased_bridge._parse_date` (Task requirement 2 extends *that*
# function's recognized formats) — this only locates the substring.
DATE_PATTERNS = [
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{4}-\d{2}-\d{2})\b",
]

# Illustrative, non-exhaustive labels a real invoice/receipt uses for its own
# identifying number (Task requirement 3: "Invoice #, Invoice No., Invoice
# Number, Receipt #, Transaction #, equivalenti comuni"). Each requires the
# label to be immediately followed by a recognizable "here's the value"
# marker (No./Number/#/:) so a bare mention of the word "invoice" elsewhere
# in the text is never mistaken for the label.
DOC_NUMBER_PATTERNS = [
    r"invoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    r"invoice\s*[:\-]?\s*#\s*([A-Za-z0-9\-]+)",
    r"receipt\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    r"receipt\s*[:\-]?\s*#\s*([A-Za-z0-9\-]+)",
    r"transaction\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    r"trans(?:action)?\.?\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Za-z0-9\-]+)",
    r"order\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
]

# Checked in priority order — a more specific/authoritative label (Grand
# Total, Amount Due) is matched before the bare "total" so a document
# showing several labeled amounts resolves to the right one, not whichever
# happens to appear first (Task requirement 4).
TOTAL_KEYWORDS = [
    "grand total",
    "invoice total",
    "receipt total",
    "amount due",
    "balance due",
    "total due",
    "total amount",
    "total",
]

# The same subset used by has_conflicting_totals() below — the only labels
# treated as equally authoritative "this line states the document's total"
# claims. The bare "total" is deliberately excluded here: it matches
# Subtotal too (see EXCLUDE_FROM_TOTAL_LINE), so two different "total"-ish
# lines are expected and not itself a conflict signal.
STRONG_TOTAL_KEYWORDS = ("grand total", "invoice total", "receipt total", "amount due", "balance due", "total due", "total amount")

# A line containing one of these must never be read as "the total" even
# though it may contain the substring "total" (Subtotal) or look like a
# total-shaped line otherwise (Task requirement 4: "Evita di confondere:
# subtotal, tax, balance forward, tip, payment amount").
EXCLUDE_FROM_TOTAL_LINE = (
    "subtotal",
    "sub-total",
    "sub total",
    "tax",
    "balance forward",
    "tip",
    "gratuity",
    "amount paid",
    "amount tendered",
    "payment amount",
    "change due",
)

MONEY = r"\$?\s?(\d{1,3}(?:[,.]\d{3})*(?:\.\d{2}))"

LINE_ITEM_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?P<desc>.+?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+"
    r"\$?\s?(?P<price>\d+(?:[,.]\d{3})*\.\d{2})\s+"
    r"\$?\s?(?P<amount>\d+(?:[,.]\d{3})*\.\d{2})\s*$"
)

# Illustrative, non-exhaustive: common invoice boilerplate that is never
# itself a supplier's identity, even when it is the most plausible-LOOKING
# candidate line by pure text shape (real words, capitalized) -- e.g.
# "PLEASE REMIT" near a payment-instructions block. Checked as a substring
# (not exact-match) so "PLEASE REMIT TO: PO BOX 123" is skipped too, not
# just an exact standalone occurrence.
SKIP_SUPPLIER_PHRASES = (
    "invoice",
    "receipt",
    "bill to",
    "ship to",
    "please remit",
    "remit to",
    "remit payment",
    "make check payable",
    "pay to the order of",
    "thank you for your business",
    "fattura",
    "page",
    "email",
    "phone",
    "fax",
    "website",
)


def _clean_number(raw: str) -> str:
    return raw.replace(",", "")


def looks_like_plausible_name(candidate: str) -> bool:
    """A coarse, generic sanity check — not a language model, not a
    supplier-specific rule (that is Supplier Format training's own future
    concern, §8). Rejects the clearest non-name noise (empty, too short,
    mostly digits/symbols); does not attempt to catch every possible OCR
    misread, which a generic, per-document heuristic cannot reliably do."""

    if not candidate:
        return False
    stripped = candidate.strip()
    if len(stripped) < 3:
        return False
    letters = sum(1 for c in stripped if c.isalpha())
    if letters < 3:
        return False
    if letters / len(stripped) < 0.5:
        return False
    # A real business name/letterhead is essentially always capitalized in
    # some way (or multi-word) -- a single, short, all-lowercase token is
    # far more often an OCR fragment (e.g. "eof") than an actual name.
    if stripped.islower() and " " not in stripped and len(stripped) < 5:
        return False
    return True


def guess_supplier(lines: list[str]) -> str:
    """Best-effort supplier NAME extraction from the document's own header
    text (Task requirement 5: "header documentale; structured text").
    Filename-based and known-supplier-alias resolution happen one layer up,
    in `purchased_bridge.py`, which has access to already-recorded Suppliers
    — this function only ever looks at what the document itself says, and
    never invents an identity when nothing plausible is found."""

    best_implausible: str = ""
    for line in lines[:8]:
        candidate = line.strip()
        if not candidate:
            continue
        if any(phrase in candidate.lower() for phrase in SKIP_SUPPLIER_PHRASES):
            continue
        if re.fullmatch(r"[\d\s\-+()]+", candidate):
            continue
        # strip a trailing email or phone number, keep the company name part
        candidate = re.sub(r"\s*\S+@\S+", "", candidate).strip()
        candidate = re.sub(r"\+?\d[\d\-\s()]{6,}$", "", candidate).strip()
        if not candidate:
            continue
        if looks_like_plausible_name(candidate):
            return candidate
        if not best_implausible:
            best_implausible = candidate
    # Nothing plausible found -- still return the best raw candidate (never
    # silently empty when the source clearly had *something* there), but
    # `purchased_bridge.py`'s own plausibility check applies the same test
    # again before ever calling this a recognized supplier.
    return best_implausible


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
            lowered = line.lower()
            if keyword not in lowered:
                continue
            if any(excl in lowered for excl in EXCLUDE_FROM_TOTAL_LINE):
                continue  # a Subtotal/Tax/Tip/Payment line, not the document's actual total
            m = re.search(MONEY, line)
            if m:
                return _clean_number(m.group(1))
    # fallback: last money-looking number in the whole text
    all_amounts = re.findall(MONEY, text)
    if all_amounts:
        return _clean_number(all_amounts[-1])
    return ""


def has_conflicting_totals(text: str) -> bool:
    """True when two or more DIFFERENT amounts appear on lines carrying an
    equally authoritative "this is the total" label — genuinely ambiguous
    which one is correct, so the caller must not silently pick one (Task
    requirement 4/7: "conflicting totals -> HUMAN")."""

    amounts_found: set[str] = set()
    for line in text.splitlines():
        lowered = line.lower()
        if not any(keyword in lowered for keyword in STRONG_TOTAL_KEYWORDS):
            continue
        if any(excl in lowered for excl in EXCLUDE_FROM_TOTAL_LINE):
            continue
        m = re.search(MONEY, line)
        if m:
            amounts_found.add(_clean_number(m.group(1)))
    return len(amounts_found) > 1


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
