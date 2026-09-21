"""Pure CSV parsing for Bank Reconciliation manual import (spec §3).

No database access here — every function in this module reads bytes/text
and returns dataclasses. `service.py` is responsible for persistence and
duplicate detection.

Four source layouts are recognized (spec §3):

- CHASE_BANK_ACCOUNT
- CHASE_CREDIT_CARD_WITH_CARD   (Variant A — explicit `Card` column)
- CHASE_CREDIT_CARD_NO_CARD     (Variant B — no `Card` column)
- FIRST_CITIZENS

Format detection is by exact header-set matching (never by file name —
spec §3.2: a file name is only ever a hint, never authoritative)."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CHASE_BANK_ACCOUNT = "CHASE_BANK_ACCOUNT"
CHASE_CREDIT_CARD_WITH_CARD = "CHASE_CREDIT_CARD_WITH_CARD"
CHASE_CREDIT_CARD_NO_CARD = "CHASE_CREDIT_CARD_NO_CARD"
FIRST_CITIZENS = "FIRST_CITIZENS"

_CHASE_BANK_HEADERS = {"Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"}
_CHASE_CARD_WITH_CARD_HEADERS = {
    "Card", "Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo",
}
_CHASE_CARD_NO_CARD_HEADERS = {
    "Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo",
}
_FIRST_CITIZENS_HEADERS = {
    "Account Number", "Post Date", "Check", "Description", "Debit", "Credit", "Status", "Balance",
}


class UnrecognizedFormatError(ValueError):
    """Raised when a CSV header does not match any of the four known
    layouts (spec §3) — never guessed, never silently forced into one."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> str:
    """Bank exports are not reliably UTF-8 (accented merchant names have
    been observed as Windows-1252). Try UTF-8 first (stripping a BOM, which
    Chase/First Citizens exports commonly carry), fall back to cp1252 with
    replacement rather than raising — a decoding wrinkle must never block
    preservation of the row (spec §4.1)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def detect_format(header: list[str]) -> str:
    header_set = {h.strip() for h in header if h.strip()}
    if header_set == _CHASE_BANK_HEADERS:
        return CHASE_BANK_ACCOUNT
    if header_set == _CHASE_CARD_WITH_CARD_HEADERS:
        return CHASE_CREDIT_CARD_WITH_CARD
    if header_set == _CHASE_CARD_NO_CARD_HEADERS:
        return CHASE_CREDIT_CARD_NO_CARD
    if header_set == _FIRST_CITIZENS_HEADERS:
        return FIRST_CITIZENS
    raise UnrecognizedFormatError(
        f"Header {sorted(header_set)!r} does not match any known Bank Reconciliation source "
        "layout (Chase bank account, Chase credit card with/without Card, First Citizens)."
    )


def to_minor_units(value: str | None) -> tuple[int | None, str | None]:
    """Parse a source dollar-amount string into signed integer cents.
    Returns (amount_minor, error) — error is None on success. Accepts an
    optional leading '$', thousands separators, and parentheses for
    negative amounts (e.g. "(24.05)") since real exports have used both
    conventions; never uses floating point on the stored value."""
    if value is None:
        return None, "missing amount"
    text = value.strip()
    if not text:
        return None, "missing amount"
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    if text.startswith("-"):
        negative = True
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, f"unparseable amount: {value!r}"
    minor = int((amount * 100).to_integral_value())
    return (-minor if negative else minor), None


def _parse_date(value: str | None) -> tuple[date | None, str | None]:
    if value is None or not value.strip():
        return None, "missing date"
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"unparseable date: {value!r}"


@dataclass
class ParsedBankRow:
    row_number: int  # 1-based line number within the file, header = line 1
    raw_fields: dict[str, str]
    parse_status: str  # PARSED, ANOMALOUS, UNREADABLE
    anomalies: list[str] = field(default_factory=list)

    posting_date: date | None = None
    transaction_date: date | None = None
    description: str | None = None
    amount_minor: int | None = None
    bank_transaction_type: str | None = None
    reference: str | None = None
    balance_minor: int | None = None
    pending_status: str | None = None
    # Account identifier as it literally appears in the file, when the
    # layout carries one (First Citizens' Account Number; Chase credit card
    # Variant A's Card). None for layouts with no in-file identifier.
    account_hint: str | None = None
    # BANK_MEMO_PURPOSE_CLASSIFICATION_001 — PURPOSE text the source
    # supplies, kept apart from `description` (which is what the BANK
    # wrote). Chase's two card layouts have a `Memo` column; the Chase bank
    # account and First Citizens layouts have none, so both stay None
    # rather than being filled from something that means something else.
    # `source_memo_field` names the column, so Description / Memo / Note
    # remain distinguishable downstream.
    #
    # A column that EXISTS but is blank leaves both None: "the bank offered
    # a memo box and nobody filled it" is not purpose evidence.
    source_memo: str | None = None
    source_memo_field: str | None = None


@dataclass
class ParsedFile:
    detected_format: str
    header: list[str]
    rows: list[ParsedBankRow]
    extra_trailing_column_seen: bool = False


def _get(fields: dict[str, str], key: str) -> str | None:
    value = fields.get(key)
    return value.strip() if value is not None else None


def _purpose_field(fields: dict[str, str], key: str) -> tuple[str | None, str | None]:
    """The layout's purpose column and its name, or (None, None).

    Only a NON-EMPTY value counts. Chase writes a `Memo` header on every
    card export and leaves it blank unless the cardholder typed something,
    so an empty cell is the absence of purpose evidence, not evidence of
    an absent purpose."""
    value = _get(fields, key)
    return (value, key) if value else (None, None)


def _parse_chase_bank_row(row_number: int, fields: dict[str, str], extra_value: str | None) -> ParsedBankRow:
    anomalies: list[str] = []
    if extra_value is not None and extra_value.strip():
        anomalies.append(
            f"undeclared trailing column is not empty: {extra_value!r} — spec §3.1 permits ignoring it "
            "only when genuinely empty."
        )

    posting_date, date_err = _parse_date(_get(fields, "Posting Date"))
    amount_minor, amount_err = to_minor_units(_get(fields, "Amount"))
    description = _get(fields, "Description")
    if date_err:
        anomalies.append(date_err)
    if amount_err:
        anomalies.append(amount_err)
    if not description:
        anomalies.append("missing description")

    balance_minor, balance_err = to_minor_units(_get(fields, "Balance"))
    if balance_err and _get(fields, "Balance"):
        anomalies.append(balance_err)

    status = "PARSED" if not anomalies else ("UNREADABLE" if date_err or amount_err or not description else "ANOMALOUS")
    return ParsedBankRow(
        row_number=row_number, raw_fields=fields, parse_status=status, anomalies=anomalies,
        posting_date=posting_date, transaction_date=None, description=description,
        amount_minor=amount_minor, bank_transaction_type=_get(fields, "Type"),
        reference=_get(fields, "Check or Slip #"), balance_minor=balance_minor, pending_status=None,
        account_hint=None,
    )


def _parse_chase_card_row(row_number: int, fields: dict[str, str], has_card: bool) -> ParsedBankRow:
    anomalies: list[str] = []
    posting_date, date_err = _parse_date(_get(fields, "Post Date"))
    source_memo, source_memo_field = _purpose_field(fields, "Memo")
    transaction_date, txn_date_err = _parse_date(_get(fields, "Transaction Date"))
    amount_minor, amount_err = to_minor_units(_get(fields, "Amount"))
    description = _get(fields, "Description")
    if date_err:
        anomalies.append(date_err)
    if txn_date_err:
        anomalies.append(f"transaction date: {txn_date_err}")
    if amount_err:
        anomalies.append(amount_err)
    if not description:
        anomalies.append("missing description")

    status = "PARSED" if not (date_err or amount_err or not description) else "UNREADABLE"
    if status == "PARSED" and txn_date_err:
        status = "ANOMALOUS"

    return ParsedBankRow(
        row_number=row_number, raw_fields=fields, parse_status=status, anomalies=anomalies,
        posting_date=posting_date, transaction_date=transaction_date, description=description,
        source_memo=source_memo, source_memo_field=source_memo_field,
        amount_minor=amount_minor, bank_transaction_type=_get(fields, "Type"),
        reference=_get(fields, "Memo"), balance_minor=None, pending_status=None,
        account_hint=_get(fields, "Card") if has_card else None,
    )


def _parse_first_citizens_row(row_number: int, fields: dict[str, str]) -> ParsedBankRow:
    anomalies: list[str] = []
    posting_date, date_err = _parse_date(_get(fields, "Post Date"))
    description = _get(fields, "Description")
    debit_minor, debit_err = to_minor_units(_get(fields, "Debit")) if _get(fields, "Debit") else (0, None)
    credit_minor, credit_err = to_minor_units(_get(fields, "Credit")) if _get(fields, "Credit") else (0, None)
    if date_err:
        anomalies.append(date_err)
    if debit_err:
        anomalies.append(f"debit: {debit_err}")
    if credit_err:
        anomalies.append(f"credit: {credit_err}")
    if not description:
        anomalies.append("missing description")

    amount_minor = None
    if debit_err is None and credit_err is None:
        amount_minor = (credit_minor or 0) - (debit_minor or 0)
    else:
        anomalies.append("amount could not be computed as Credit - Debit")

    balance_minor, balance_err = to_minor_units(_get(fields, "Balance"))
    if balance_err and _get(fields, "Balance"):
        anomalies.append(balance_err)

    status = "PARSED" if not (date_err or not description or amount_minor is None) else "UNREADABLE"

    return ParsedBankRow(
        row_number=row_number, raw_fields=fields, parse_status=status, anomalies=anomalies,
        posting_date=posting_date, transaction_date=None, description=description,
        amount_minor=amount_minor, bank_transaction_type=None,
        reference=_get(fields, "Check"), balance_minor=balance_minor, pending_status=_get(fields, "Status"),
        account_hint=_get(fields, "Account Number"),
    )


def parse_row_fields(detected_format: str, row_number: int, fields: dict[str, str]) -> ParsedBankRow:
    """Re-parse a single row's already-preserved `raw_fields` (spec §4.1)
    into a `ParsedBankRow`, without needing the original CSV bytes again —
    used by `service.py` when normalization happens later than upload
    (e.g. once a human resolves a batch's account). Structurally identical
    to the per-row logic `parse_csv_bytes` applies inline; the only thing
    it cannot reconstruct is the original file's undeclared-trailing-column
    anomaly (already recorded on the row at upload time, never needed
    twice)."""
    if detected_format == CHASE_BANK_ACCOUNT:
        return _parse_chase_bank_row(row_number, fields, extra_value=None)
    if detected_format in (CHASE_CREDIT_CARD_WITH_CARD, CHASE_CREDIT_CARD_NO_CARD):
        return _parse_chase_card_row(row_number, fields, has_card=detected_format == CHASE_CREDIT_CARD_WITH_CARD)
    if detected_format == FIRST_CITIZENS:
        return _parse_first_citizens_row(row_number, fields)
    raise UnrecognizedFormatError(f"Unknown detected_format {detected_format!r}")


def parse_csv_bytes(data: bytes) -> ParsedFile:
    """Parse a full CSV file. Format is detected once from the header
    (spec §3); every data row is then parsed according to that same
    format. A row that fails to parse is returned with `parse_status`
    `UNREADABLE`/`ANOMALOUS` rather than raising — it is never dropped
    (spec §4.1: the outcome of reading the row must itself be preserved)."""
    text = _decode(data)
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise UnrecognizedFormatError("File is empty — no header row found.")

    # A known trailing, undeclared empty column (spec §3.1) shows up as one
    # extra, unnamed field per data row beyond the declared header. Detect
    # it structurally (not by name) by checking the first data row's width.
    declared_width = len(header)
    detected_format = detect_format(header)
    has_card = detected_format == CHASE_CREDIT_CARD_WITH_CARD

    rows: list[ParsedBankRow] = []
    extra_trailing_column_seen = False
    for line_number, raw_row in enumerate(reader, start=2):
        if not raw_row or all(not cell.strip() for cell in raw_row):
            continue  # a genuinely blank line is not a transaction row
        extra_value = None
        if len(raw_row) > declared_width:
            extra_value = raw_row[declared_width]
            if extra_value.strip():
                extra_trailing_column_seen = True
        fields = {header[i]: raw_row[i] for i in range(min(declared_width, len(raw_row)))}

        if detected_format == CHASE_BANK_ACCOUNT:
            parsed = _parse_chase_bank_row(line_number, fields, extra_value)
        elif detected_format in (CHASE_CREDIT_CARD_WITH_CARD, CHASE_CREDIT_CARD_NO_CARD):
            parsed = _parse_chase_card_row(line_number, fields, has_card)
        else:
            parsed = _parse_first_citizens_row(line_number, fields)
        rows.append(parsed)

    return ParsedFile(
        detected_format=detected_format, header=header, rows=rows,
        extra_trailing_column_seen=extra_trailing_column_seen,
    )
