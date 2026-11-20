"""Supplier + Source Format specializations (Phase 1 of real supplier
training — "Purchased Supplier+Format Training — Phase 1").

`parser.py` stays entirely generic and untouched by this module (Task
requirement 6: "NON rompere il parser generico"). This module is the
*second* stage of the pipeline described there:

    generic parser -> supplier-format specialization -> validation -> NORMALIZED/HUMAN

Each specialization here exists only because a real, recurring, stable
pattern was observed and verified against real acquired documents (see
`07 Tasks/` phase-1 training report) — never introduced speculatively for a
Supplier we have not actually seen real documents for (Task requirement 6,
8: "NON inventare"). Like `parser.py`, a specialization never invents a
value: when its own targeted pattern does not find a clean value, it leaves
the field exactly as the generic parser left it (or empty), it never falls
back to guessing — a missing field is safer than a wrong one ("Meglio HUMAN
corretto che NORMALIZED sbagliato").

Currently covers, both validated against real Rome's Flavours documents:

- **Prime Line Distributors** (priority 1): a recurring letterhead brand
  string, a bare "Number:"/"Date:" label pair the generic parser's own
  invoice-number/date patterns do not recognize (they require an
  "Invoice"/"Order" prefix Prime Line's own label never uses, and can
  otherwise latch onto the blank "INVOICE #" remittance-stub field or a
  "Payment Due by" date instead of the real one), and a "TOTAL" line the
  generic parser can also mis-red when a Subtotal line's OCR-garbled digits
  happen to be picked up first.
- **Costco Wholesale** (priority 4, direct/in-store channel only — see
  `detect_channel()` below for the Instacart distinction): the printed
  "TOTAL" line sits inside a reverse-video/highlighted box that Tesseract
  reads very unreliably on a photographed receipt; the payment-confirmation
  block below it ("Tran ID#", "EFT/Debit <amount>") is consistently clean
  in every real sample seen so far and is used instead, both as this
  format's document-identity number and as its total.
- **Ben E. Keith Foods** (priority 2) — supplier name and document_number
  recognition (the "Invoice No. | Page | Rep" row — added in Phase 2 for
  multi-invoice splitting); Date/Total stay the generic parser's problem for
  now (see that section below for why).

Samuel & Son, Sam's Club (direct or via Instacart) have no real acquired
documents yet (see the phase-1 report, section D/G) — no specialization is
added for them; adding one now would be exactly the "inventare" this module
must not do.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Prime Line Distributors
# ---------------------------------------------------------------------------

# pdfplumber renders an unmapped glyph (an untagged tab cell in these forms'
# own table layout) as a literal "(cid:9)" token instead of whitespace — a
# real, recurring artifact confirmed on page 4 of the real 4-invoice batch
# `PL20200609171959_001.pdf` ("Number.(cid:9) 1103053"), where a plain
# `\s*` between the label and its value missed the number entirely (added
# for "Purchased Supplier Training Phase 2", multi-invoice splitting).
_LABEL_SEP = r"(?:\(cid:\d+\)|\s)*"

_PRIME_LINE_BRAND = re.compile(r"prime\s+line\s+distributors", re.IGNORECASE)
_PRIME_LINE_NUMBER = re.compile(r"\bnumber\s*[.:]" + _LABEL_SEP + r"([A-Za-z0-9]+)", re.IGNORECASE)
_PRIME_LINE_DATE = re.compile(r"\bdate\s*[.:]?" + _LABEL_SEP + r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.IGNORECASE)
_MONEY_TAIL = re.compile(r"(\d+\.\d{2})")

CANONICAL_PRIME_LINE_NAME = "Prime Line Distributors"


def _is_prime_line(raw_text: str) -> bool:
    return bool(_PRIME_LINE_BRAND.search(raw_text))


def _prime_line_total(raw_text: str) -> str | None:
    """The bare "TOTAL" line, same-line value only — deliberately never the
    generic parser's whole-document fallback ("last money-looking number in
    the text"), which real Prime Line scans have shown to latch onto an
    unrelated per-lb unit price when the real total's value is missing or
    displaced by noisy OCR column reordering."""

    for line in raw_text.splitlines():
        lowered = line.lower()
        if "total" not in lowered:
            continue
        if "subtotal" in lowered or "sub total" in lowered or "sub-total" in lowered:
            continue  # a Subtotal line also contains the substring "total"
        m = _MONEY_TAIL.search(line)
        if m:
            return m.group(1)
    return None


def _apply_prime_line(raw_text: str, header: dict) -> dict:
    """Once a document is confidently identified as Prime Line, its own
    bare "Number:"/"Date:"/"TOTAL" labels are the only trustworthy source
    for these three fields — real samples have shown the GENERIC parser's
    document-number/date/total guesses are consistently WRONG for this
    Supplier's own layout (see module docstring), not just occasionally
    missing. So when this specialization's own targeted pattern does not
    find a clean value either, the field is blanked out rather than left at
    the generic parser's guess: a confident wrong value is worse than an
    empty one that correctly routes to HUMAN ("Meglio HUMAN corretto che
    NORMALIZED sbagliato")."""

    header = dict(header)
    header["supplier_name"] = CANONICAL_PRIME_LINE_NAME

    number_match = _PRIME_LINE_NUMBER.search(raw_text)
    header["document_number"] = number_match.group(1) if number_match else ""

    date_match = _PRIME_LINE_DATE.search(raw_text)
    header["issue_date"] = date_match.group(1) if date_match else ""

    header["total_amount"] = _prime_line_total(raw_text) or ""

    return header


# ---------------------------------------------------------------------------
# Costco Wholesale (direct/in-store channel)
# ---------------------------------------------------------------------------

_COSTCO_WORDMARK = re.compile(r"\bcostco\b", re.IGNORECASE)
# The one real warehouse account observed so far (Task requirement 3:
# "NON assumere Supplier = one format" applies just as much to "one
# recognizable evidence signal" — this is deliberately narrow, not a
# general Costco-detection rule, until a second warehouse/account is
# actually seen).
_COSTCO_MERCHANT_ID = re.compile(r"merchant\s*id\s*:?\s*990183", re.IGNORECASE)
_COSTCO_TRAN_ID = re.compile(r"tran\s*id\s*#?\s*:?\s*([0-9]+)", re.IGNORECASE)
_COSTCO_EFT_DEBIT_AMOUNT = re.compile(r"eft\s*/\s*debit\s+(\d+\.\d{2})", re.IGNORECASE)

CANONICAL_COSTCO_NAME = "Costco Wholesale"


def _is_costco(raw_text: str) -> bool:
    return bool(_COSTCO_WORDMARK.search(raw_text) or _COSTCO_MERCHANT_ID.search(raw_text))


def _apply_costco(raw_text: str, header: dict) -> dict:
    header = dict(header)
    header["supplier_name"] = CANONICAL_COSTCO_NAME

    tran_match = _COSTCO_TRAN_ID.search(raw_text)
    if tran_match:
        header["document_number"] = tran_match.group(1)

    amount_match = _COSTCO_EFT_DEBIT_AMOUNT.search(raw_text)
    if amount_match:
        header["total_amount"] = amount_match.group(1)

    return header


# ---------------------------------------------------------------------------
# Ben E. Keith Foods — SUPPLIER NAME ONLY.
#
# Real samples (see report, section D) show this Supplier's own PDF text
# layer has its table columns badly reordered by whatever scan/OCR process
# produced it upstream (before it ever reaches this pipeline) — Number,
# Date and Total end up scattered across unrelated lines, sometimes
# overlapping other fields' values, in a way no single targeted regex can
# safely recover without a real risk of confidently returning the WRONG
# value (unlike Prime Line above, where the failure mode is "value simply
# absent", here it is "several plausible-looking values, wrong one just as
# likely as the right one" — not something a "blank when not found" policy
# alone protects against). Only the brand string itself is stable and
# unambiguous across both real invoices seen (it never competes with other
# similar-looking text), so only supplier_name is specialized for now;
# document_number/issue_date/total_amount are deliberately left to the
# generic parser (i.e. usually empty/HUMAN) until either a cleaner
# acquisition channel or more real samples justify a targeted rule.
# ---------------------------------------------------------------------------

_KEITH_BRAND = re.compile(r"ben\s*e\.?\s*keith", re.IGNORECASE)

# Added for "Purchased Supplier Training Phase 2" (multi-invoice splitting,
# §5B/§16): the table header on every real Keith page prints
# "Invoice No. | Page | Rep" and the row right under it as three adjacent
# numbers -- e.g. "90080721 1 OT", "90080721 2 OT". This one is used as a
# split-boundary + document-identity signal because it survived the exact
# real page (page 2 of `24 Keith_20241010_0002-1-3.pdf`) where the brand
# text itself came back so character-scrambled by pdfplumber that
# `_KEITH_BRAND` above does NOT match it -- so this pattern is also treated
# as its own, independent Keith-recognition signal (`_is_keith()` below),
# not only a refinement applied after the brand is already found. Digits
# can still be individually OCR-misread (same residual risk already
# documented for Costco's Tran ID# in Phase 1) -- this is a real, stable,
# *recurring* pattern, not a guess.
_KEITH_INVOICE_NUMBER = re.compile(r"\b(\d{6,9})\s+\d{1,2}\s+(?:OT|\d{2,3})\b")

CANONICAL_KEITH_NAME = "Ben E. Keith Foods"


def _is_keith(raw_text: str) -> bool:
    return bool(_KEITH_BRAND.search(raw_text)) or bool(_KEITH_INVOICE_NUMBER.search(raw_text))


def _apply_keith(raw_text: str, header: dict) -> dict:
    header = dict(header)
    header["supplier_name"] = CANONICAL_KEITH_NAME
    number_match = _KEITH_INVOICE_NUMBER.search(raw_text)
    if number_match:
        header["document_number"] = number_match.group(1)
    return header


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def apply_supplier_specializations(raw_text: str, header: dict) -> dict:
    """Applies the one matching specialization (if any) for this document's
    raw text, on top of whatever the generic parser already produced.
    Returns `header` unchanged when no known Supplier+Format signature is
    recognized (Task requirement 6: the generic parser's own result is
    always the fallback, never replaced by a guess)."""

    if not raw_text:
        return header
    if _is_prime_line(raw_text):
        return _apply_prime_line(raw_text, header)
    if _is_costco(raw_text):
        return _apply_costco(raw_text, header)
    if _is_keith(raw_text):
        return _apply_keith(raw_text, header)
    return header


# ---------------------------------------------------------------------------
# Acquisition channel (Task requirement 9: "Costco direct != Costco via
# Instacart" as a distinct Supplier+Format training unit) — supplier-
# agnostic on purpose: the same distinction applies to any supplier that
# might arrive either directly or through a marketplace/delivery channel.
# ---------------------------------------------------------------------------

CHANNEL_DIRECT = "Direct"
CHANNEL_INSTACART = "Instacart"


def detect_channel(raw_text: str, source_file: str | None = None) -> str:
    """Best-effort acquisition CHANNEL, independent of `document_number`/
    `total_amount` etc. — combined with the OCR/PDF-Text acquisition
    *method* to form the `source_format` unit `supplier_format_training.py`
    tracks (Task requirement 9). Never assumes Direct vs Instacart from the
    Supplier name alone: only the document's own text or its source
    filename (e.g. an Instacart receipt email attachment) count as
    evidence. No real Instacart document has been acquired yet for Costco
    or Sam's Club (see phase-1 report, section F/G) — this function is
    still added now, ahead of that data, purely so the training unit is
    structurally ready to keep them separate the moment one arrives,
    consistent with not merging them "solo per Supplier identity"."""

    haystack = f"{raw_text or ''}\n{source_file or ''}".lower()
    if "instacart" in haystack:
        return CHANNEL_INSTACART
    return CHANNEL_DIRECT
