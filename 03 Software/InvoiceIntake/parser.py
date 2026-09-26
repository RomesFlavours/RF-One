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
    "total amount",
    "total",
]

# INVOICE_SCAN_ACQUISITION_001 — what is still to be paid is NOT the
# invoice total: "Balance due $1,394.39" under "Total $1,452.00" (BBC Wine
# Imports, invoice 6855) was read as the total. These labels now feed the
# separate `balance_due` amount and are never used as the total.
BALANCE_KEYWORDS = ("balance due", "amount due", "total due", "balance")
PAID_KEYWORDS = ("amount paid", "payments/credits", "payment received", "payments", "paid", "credits applied")
SUBTOTAL_KEYWORDS = ("subtotal", "sub-total", "sub total")
TAX_RE = re.compile(r"tax(?!\s*(?:id|#|no|number|exempt))", re.IGNORECASE)
SHIPPING_KEYWORDS = ("shipping", "freight", "delivery charge", "delivery fee")

# The same subset used by has_conflicting_totals() below — the only labels
# treated as equally authoritative "this line states the document's total"
# claims. The bare "total" is deliberately excluded here: it matches
# Subtotal too (see EXCLUDE_FROM_TOTAL_LINE), so two different "total"-ish
# lines are expected and not itself a conflict signal.
STRONG_TOTAL_KEYWORDS = ("grand total", "invoice total", "receipt total", "total amount")

# A line containing one of these must never be read as "the total" even
# though it may contain the substring "total" (Subtotal) or look like a
# total-shaped line otherwise (Task requirement 4: "Evita di confondere:
# subtotal, tax, balance forward, tip, payment amount"). "total weight" and
# "sub total for" (a per-section subtotal, e.g. "SUB TOTAL FOR COOLER") were
# added by "Purchased Supplier+Format Training — Phase 1" after a real
# distributor invoice (Ben E. Keith Foods) showed a per-line freight
# weight/subtotal ("TOTAL WEIGHT 19.10# 15.85 302.74") being misread as the
# document's own total — purely additive, so this only ever makes total
# recognition more conservative, never introduces a new false match.
EXCLUDE_FROM_TOTAL_LINE = (
    "subtotal",
    "sub-total",
    "sub total",
    "total weight",
    "tax",
    "balance forward",
    "tip",
    "gratuity",
    "amount paid",
    "amount tendered",
    "payment amount",
    "change due",
    # INVOICE_SCAN_ACQUISITION_001: balance/payment lines are never the total.
    "balance",
    "amount due",
    "total due",
    "paid",
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
    """The invoice TOTAL, only from a line labelled as a total (never a
    balance/amount-due/payment line). INVOICE_SCAN_ACQUISITION_001 removed
    the old fallback "last amount in the text": an unlabelled number is not
    evidence of the total, so an unrecognized total stays empty."""
    lines = text.splitlines()
    for keyword in TOTAL_KEYWORDS:
        for line in lines:
            lowered = line.lower()
            if keyword not in lowered:
                continue
            if any(excl in lowered for excl in EXCLUDE_FROM_TOTAL_LINE):
                continue  # a Subtotal/Tax/Tip/Payment/Balance line, not the document's actual total
            m = re.search(MONEY, line)
            if m:
                return _clean_number(m.group(1))
    return ""


def _labelled_amounts(text: str, keywords, exclude=()) -> list[str]:
    found = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(k in lowered for k in keywords) and not any(e in lowered for e in exclude):
            m = re.search(MONEY, line[max(lowered.find(k) for k in keywords if k in lowered):])
            if m:
                found.append(_clean_number(m.group(1)))
    return found


def extract_terms_and_due_date(text: str) -> dict:
    """Payment terms and due date, only from explicitly labelled text."""
    out = {}
    m = re.search(r"\bterms\s*[:\-]\s*([^\n]{1,40}?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        out["payment_terms"] = m.group(1).strip()
    m = re.search(r"\bdue\s*date\s*[:\-]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", text, re.IGNORECASE)
    if m:
        out["due_date"] = m.group(1)
    return out


def extract_amounts(text: str) -> dict:
    """Every document-level amount the text states with an explicit label,
    kept distinct (INVOICE_SCAN_ACQUISITION_001): total, subtotal, tax,
    shipping, amount paid, balance due. A label read with two different
    amounts is reported in `conflicts`, never resolved by choosing one."""
    amounts: dict = {}
    conflicts: list[str] = []

    def put(key, values):
        distinct = sorted(set(values))
        if len(distinct) == 1:
            amounts[key] = distinct[0]
        elif len(distinct) > 1:
            conflicts.append(f"{key}: different values read {', '.join(distinct)}")

    total = guess_total(text)
    if total:
        amounts["total"] = total
    put("balance_due", _labelled_amounts(text, BALANCE_KEYWORDS, exclude=("balance forward",)))
    put("amount_paid", _labelled_amounts(text, PAID_KEYWORDS, exclude=("will be", "made with")))
    put("subtotal", _labelled_amounts(text, SUBTOTAL_KEYWORDS, exclude=("sub total for",)))
    put("shipping", _labelled_amounts(text, SHIPPING_KEYWORDS, exclude=("ship to", "shipping info", "ship via")))
    tax_values = []
    for line in text.splitlines():
        match = TAX_RE.search(line)
        if match:
            m = re.search(MONEY, line[match.end():])
            if m:
                tax_values.append(_clean_number(m.group(1)))
    put("tax", tax_values)
    return {"amounts": amounts, "conflicts": conflicts}


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
