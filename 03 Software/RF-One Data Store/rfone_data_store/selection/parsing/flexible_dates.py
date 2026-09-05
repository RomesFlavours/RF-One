"""Shared flexible date-string parsing for résumé parsers (Task 2A) and,
since Task 2B, the precision/confidence-aware normalization layer built on
top of it.

`parse_flexible_date`/`is_current_marker` are the low-level, Task 2A
primitives — they turn one résumé-written date string into a `datetime`
(day fixed to 1) or a "this is a current-role marker" flag, and are kept
exactly as Task 2A left them (still used directly by `normalize_date_text`
below, so there is one parsing implementation, not two).

`normalize_date_text`/`normalize_date_pair` are Task 2B's addition: they
layer PRECISION (day/month/year/approximate/unknown) and CONFIDENCE
(high/medium/low) on top of the same parse, and combine a start+end pair
into `is_current`/normalized values — this is what turns a parsed date into
the machine-usable representation Task 2B's normalization layer persists,
while the original text a parser captured (`WorkHistoryRecord.start_date_text`
etc.) stays untouched as the authoritative evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime

CURRENT_WORDS = {"present", "current", "currently", "now", "ongoing", "today", "date"}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_YEAR_RE = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{4})$")
_NUMERIC_MY_RE = re.compile(r"^(\d{1,2})[/\-](\d{4})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


def is_current_marker(text: str | None) -> bool:
    if not text:
        return False
    return text.strip().lower().rstrip(".") in CURRENT_WORDS


def parse_flexible_date(text: str | None) -> datetime | None:
    """Best-effort, conservative parse of a résumé-written date into a
    `datetime` (day fixed to 1). Returns None for "Present"/"Current"/etc.
    and for any text not confidently recognized as one of: ISO "YYYY-MM-DD"
    / "YYYY-MM", "Month YYYY", "MM/YYYY", or a bare "YYYY"."""

    if not text:
        return None
    cleaned = text.strip()
    if is_current_marker(cleaned):
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass

    m = _MONTH_YEAR_RE.match(cleaned)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month:
            return datetime(int(m.group(2)), month, 1)

    m = _NUMERIC_MY_RE.match(cleaned)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12:
            return datetime(int(m.group(2)), month, 1)

    m = _YEAR_RE.match(cleaned)
    if m:
        return datetime(int(m.group(1)), 1, 1)

    return None


# ---------------------------------------------------------------------------
# Task 2B — precision/confidence-aware normalization
# ---------------------------------------------------------------------------

PRECISION_DAY = "DAY"
PRECISION_MONTH = "MONTH"
PRECISION_YEAR = "YEAR"
PRECISION_APPROXIMATE = "APPROXIMATE"  # e.g. "Spring 2021" — resolved to a month, but not one the résumé stated
PRECISION_UNKNOWN = "UNKNOWN"  # no value at all — never a claim about "no precision", just "no date"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
_CONFIDENCE_ORDER = {CONFIDENCE_HIGH: 3, CONFIDENCE_MEDIUM: 2, CONFIDENCE_LOW: 1}

_SINCE_RE = re.compile(r"^since\s+(.+)$", re.IGNORECASE)
_SEASON_RE = re.compile(r"^(spring|summer|fall|autumn|winter)\s+(\d{4})$", re.IGNORECASE)
# Conservative, documented convention (task's own "use a consistent documented
# rule" ask) — a season is mapped to a representative month only for ordering/
# duration purposes; PRECISION_APPROXIMATE tells every consumer this month was
# not actually stated on the résumé.
_SEASON_MONTH = {"spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12}
_ISO_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class NormalizedDate:
    value: datetime | None
    precision: str
    confidence: str
    is_current: bool = False


def _infer_precision(cleaned: str) -> str:
    if _YEAR_RE.match(cleaned):
        return PRECISION_YEAR
    if _ISO_DAY_RE.match(cleaned):
        return PRECISION_DAY
    return PRECISION_MONTH  # ISO "YYYY-MM", "Month YYYY", "MM/YYYY"


def normalize_date_text(text: str | None) -> NormalizedDate:
    """Turns one résumé-written date string into a `NormalizedDate` — never
    guesses: a value that cannot be confidently parsed comes back as
    `value=None, precision=UNKNOWN, confidence=LOW` rather than an invented
    date. "Present"/"Current"/"Ongoing"/"Now" come back as
    `is_current=True, value=None` (task's date-semantics rule); "Since X" is
    treated as "X" for the value itself."""

    if not text or not text.strip():
        return NormalizedDate(None, PRECISION_UNKNOWN, CONFIDENCE_LOW)
    cleaned = text.strip()

    if is_current_marker(cleaned):
        return NormalizedDate(None, PRECISION_UNKNOWN, CONFIDENCE_HIGH, is_current=True)

    since_match = _SINCE_RE.match(cleaned)
    if since_match:
        return normalize_date_text(since_match.group(1))

    season_match = _SEASON_RE.match(cleaned)
    if season_match:
        month = _SEASON_MONTH[season_match.group(1).lower()]
        return NormalizedDate(datetime(int(season_match.group(2)), month, 1), PRECISION_APPROXIMATE, CONFIDENCE_MEDIUM)

    value = parse_flexible_date(cleaned)
    if value is None:
        return NormalizedDate(None, PRECISION_UNKNOWN, CONFIDENCE_LOW)
    return NormalizedDate(value, _infer_precision(cleaned), CONFIDENCE_HIGH)


@dataclass
class DatePairResult:
    normalized_start: datetime | None
    normalized_end: datetime | None
    start_precision: str
    end_precision: str
    is_current: bool
    confidence: str | None


def _combine_confidence(*confidences: str | None) -> str | None:
    present = [c for c in confidences if c]
    if not present:
        return None
    return min(present, key=lambda c: _CONFIDENCE_ORDER[c])


def normalize_date_pair(start_text: str | None, end_text: str | None) -> DatePairResult:
    """Normalizes one employment/education record's start+end date text
    together — the record-level `is_current` is driven solely by the END
    text (a "Since 2022" START value never flips `is_current` on its own);
    an end that IS a current marker always yields `normalized_end=None`,
    never a fabricated end date."""

    start_result = normalize_date_text(start_text)
    end_result = normalize_date_text(end_text)
    is_current = end_result.is_current

    return DatePairResult(
        normalized_start=start_result.value,
        normalized_end=None if is_current else end_result.value,
        start_precision=start_result.precision,
        end_precision=PRECISION_UNKNOWN if is_current else end_result.precision,
        is_current=is_current,
        confidence=_combine_confidence(start_result.confidence, CONFIDENCE_HIGH if is_current else end_result.confidence),
    )
