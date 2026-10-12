"""Two-pass Bank import (BANK_TWO_PASS_IMPORT_001).

PASS 1 — SOURCES. The account comes from the FILE NAME (a suffix such as
" (1)" is ignored), the layout from the CONTENT. A file whose name matches
exactly one Source gets it; every other file gets its Source from the person,
in the Source modal, prefilled with what the file states
(`source_prefill`) — a Source is created only when that modal is saved.
Nothing but Sources is written in this pass.

PASS 2 — READ AND CHECK. Every row is read and assigned to its file's Source;
the identifiers a Chase file carries inside (a `Card` column, linked cards)
never change that Source and never block — they stay in the raw row only.
A possible duplicate is found with ONE key, and only this key:

    posting date + normalized description + amount (signed, minor units)

never the Source, account, card or currency. Each row is compared with the
transactions already stored AND with the earlier rows of the same upload,
across files. Nothing is written: the result is a log the person resolves
(confirm the exclusion, or import as a distinct operation) before Confirm.

CONFIRM — `import_confirmed` imports each file with its Source, leaving out
the excluded rows, marking the authorized repeats CONFIRMED_DISTINCT, and
keeping the decisions in the batch's import log. The caller commits once.

Purchase files (PayPal activity, Amazon Business orders) are RECOGNISED and
shown, never read by a bank parser: their importers do not exist yet, so they
are kept for the next step — their Source can still be set now.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import card_configuration
from . import parsers
from . import service as bank_service

KIND_BANK = "BANK"
KIND_PAYPAL = "PAYPAL_ACTIVITY"
KIND_AMAZON = "AMAZON_BUSINESS_ORDERS"
KIND_UNRECOGNIZED = "UNRECOGNIZED"
DOCUMENT_KINDS = (KIND_PAYPAL, KIND_AMAZON)
KIND_LABELS = {
    KIND_BANK: "Bank / card statement",
    KIND_PAYPAL: "PayPal activity (CSV)",
    KIND_AMAZON: "Amazon Business orders report (CSV)",
    KIND_UNRECOGNIZED: "Not a known layout",
}
_PAYPAL_HEADERS = {"Date", "Time", "Name", "Type", "Status", "Currency", "Amount", "Transaction ID"}
_AMAZON_HEADERS = {"Order ID", "Order Date", "ASIN", "Item Subtotal", "Payment Amount"}

_FORMAT_TYPE = {
    parsers.CHASE_BANK_ACCOUNT: ("Chase", "BANK_ACCOUNT"),
    parsers.CHASE_CREDIT_CARD_WITH_CARD: ("Chase", "CREDIT_CARD"),
    parsers.CHASE_CREDIT_CARD_NO_CARD: ("Chase", "CREDIT_CARD"),
    parsers.FIRST_CITIZENS: ("First Citizens", "BANK_ACCOUNT"),
}
_TYPE_LABEL = {"BANK_ACCOUNT": "bank account", "CREDIT_CARD": "credit card"}
_COPY_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")
_DIGITS = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")

ISSUE_DUPLICATE_DB = "DUPLICATE_STORED"
ISSUE_DUPLICATE_UPLOAD = "DUPLICATE_IN_UPLOAD"
ISSUE_UNREADABLE = "UNREADABLE"
DECISION_EXCLUDE = "EXCLUDE"
DECISION_DISTINCT = "IMPORT_DISTINCT"


# ---------------------------------------------------------------------------
# Pass 1 — what a file is, and which Source it belongs to
# ---------------------------------------------------------------------------

@dataclass
class FileIdentity:
    file_name: str
    kind: str
    detected_format: str | None = None
    institution: str | None = None
    instrument_type: str | None = None
    account_digits: str | None = None   # from the FILE NAME only
    note: str = ""


def account_digits_from_name(file_name: str) -> str | None:
    """The account digits a file NAME carries ("Chase3144_Activity_…",
    "Firstcityzen7470"): the first run of 4–5 digits that is not part of a
    longer number (so a date such as 20261007 never counts). A copy suffix
    such as " (1)" is dropped first: it does not name another account."""
    stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    stem = _COPY_SUFFIX.sub("", stem)
    match = _DIGITS.search(stem)
    return match.group(1) if match else None


def _header(content: bytes) -> list[str]:
    text = content.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""
    import csv
    return [h.strip() for h in next(csv.reader(io.StringIO(first)), [])]


def identify_file(file_name: str, content: bytes) -> FileIdentity:
    """Layout from the content, account from the name. Purchase files are
    recognised by their own headers and never handed to a bank parser."""
    header = set(_header(content))
    if _AMAZON_HEADERS <= header:
        return FileIdentity(file_name, KIND_AMAZON, note=(
            "Amazon Business orders report: purchases and their item lines, to link to the card movement "
            "that paid them. Its importer is not available yet."))
    if _PAYPAL_HEADERS <= header:
        return FileIdentity(file_name, KIND_PAYPAL, note=(
            "PayPal activity export: PayPal movements (and item details when present). Its importer is "
            "not available yet."))
    try:
        detected = parsers.parse_csv_bytes(content).detected_format
    except parsers.UnrecognizedFormatError as exc:
        return FileIdentity(file_name, KIND_UNRECOGNIZED, note=str(exc))
    institution, instrument_type = _FORMAT_TYPE.get(detected, (None, None))
    return FileIdentity(file_name, KIND_BANK, detected_format=detected, institution=institution,
                        instrument_type=instrument_type, account_digits=account_digits_from_name(file_name))


def matching_sources(session: Session, identity: FileIdentity) -> list["m.PaymentInstrument"]:
    """Sources of the file's institution and type whose account digits are
    the ones the file name carries."""
    if identity.kind != KIND_BANK or not identity.account_digits:
        return []
    wanted = bank_service.normalize_institution(identity.institution)
    digits = identity.account_digits
    found = []
    for instrument in session.scalars(select(m.PaymentInstrument).where(
            m.PaymentInstrument.instrument_type == identity.instrument_type)):
        if bank_service.normalize_institution(instrument.institution) != wanted:
            continue
        identifier = instrument.external_account_identifier or ""
        if instrument.last_four == digits[-4:] and len(digits) == 4 or identifier == digits \
                or (identifier and identifier.endswith(digits)):
            found.append(instrument)
    return found


# BANK_COMPLETE_SOURCE_ALL_ROWS_001 — what a file states about its Source,
# offered in the Source modal of a row that has none yet. Nothing is written
# until the person saves the modal, so a cancelled modal leaves no Source.
_DOCUMENT_PREFILL = {
    KIND_PAYPAL: {"display_name": "PayPal", "instrument_type": "PAYPAL", "institution": "PayPal"},
    KIND_AMAZON: {"display_name": "Amazon Business", "instrument_type": "PURCHASE_PLATFORM",
                  "institution": "Amazon"},
}


def source_prefill(kind: str, institution: str | None, instrument_type: str | None,
                   digits: str | None) -> dict:
    """The Source fields a file states: institution, type and account digits
    for a bank file (from its layout and NAME), the provider for a PayPal /
    Amazon file, nothing for an unrecognised one."""
    if kind == KIND_BANK and instrument_type:
        label = _TYPE_LABEL.get(instrument_type, "account")
        return {"display_name": f"{institution} {label}" + (f" ··{digits}" if digits else ""),
                "instrument_type": instrument_type, "institution": institution or "",
                "last_four": digits if digits and len(digits) == 4 else "",
                "external_account_identifier": digits if digits and len(digits) != 4 else ""}
    return dict(_DOCUMENT_PREFILL.get(kind, {}))


def document_candidates(session: Session, kind: str) -> list["m.PaymentInstrument"]:
    """Existing Sources a PayPal / Amazon file may belong to: same type and
    provider. Offered first in the modal; never assigned automatically."""
    prefill = _DOCUMENT_PREFILL.get(kind)
    if not prefill:
        return []
    wanted = bank_service.normalize_institution(prefill["institution"])
    return [i for i in session.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.instrument_type == prefill["instrument_type"]))
            if bank_service.normalize_institution(i.institution) == wanted]


def duplicate_of(session: Session, instrument: "m.PaymentInstrument") -> "m.PaymentInstrument | None":
    """Another Source that is the same one: same type and provider and the
    same account digits — or, with no digits on either, the same name."""
    institution = bank_service.normalize_institution(instrument.institution)
    name = (instrument.display_name or "").strip().casefold()
    for other in session.scalars(select(m.PaymentInstrument).where(
            m.PaymentInstrument.instrument_type == instrument.instrument_type,
            m.PaymentInstrument.id != instrument.id)):
        if bank_service.normalize_institution(other.institution) != institution:
            continue
        if instrument.last_four and other.last_four == instrument.last_four:
            return other
        if instrument.external_account_identifier                 and other.external_account_identifier == instrument.external_account_identifier:
            return other
        if not (instrument.last_four or instrument.external_account_identifier
                or other.last_four or other.external_account_identifier)                 and (other.display_name or "").strip().casefold() == name:
            return other
    return None


def source_missing_fields(session: Session, instrument: "m.PaymentInstrument") -> list[str]:
    """The required data a Source still lacks before its files may be
    imported (BANK_COMPLETE_SOURCE_001), named as the Source modal's fields.
    Empty means complete. Required: a name and an institution; for a bank
    account or a card, the account digits that tie a file to it; an owner
    (Company or person) — for a card, through its settlement account, never
    chosen on the card itself; a purchase platform's owner is optional.
    Currency, cardholder and PayPal's funding account stay optional."""
    missing = []
    if not (instrument.display_name or "").strip():
        missing.append("Source name")
    if not (instrument.institution or "").strip():
        missing.append("Institution / Provider")
    if instrument.instrument_type in ("BANK_ACCOUNT", "CREDIT_CARD") \
            and not (instrument.last_four or instrument.external_account_identifier):
        missing.append("Last 4 digits or account identifier")
    if instrument.instrument_type == "CREDIT_CARD":
        if card_configuration.current_settlement_account(session, instrument.id) is None:
            missing.append("Settlement / Funding account")
    elif instrument.instrument_type != m.INSTRUMENT_TYPE_PURCHASE_PLATFORM             and instrument.legal_entity_id is None and instrument.owner_reporting_entity_id is None:
        # A purchase platform's owner / LLC is optional
        # (BANK_PURCHASE_PLATFORM_SOURCE_001).
        missing.append("Owning entity")
    return missing


# ---------------------------------------------------------------------------
# Pass 2 — read every row and find what needs a decision
# ---------------------------------------------------------------------------

def duplicate_key(posting_date, description: str | None, amount_minor: int | None) -> tuple:
    """THE duplicate key: date + normalized description + signed amount —
    nothing else (no Source, account, card or currency)."""
    return (posting_date, bank_service.normalize_description(description or ""), amount_minor)


@dataclass
class RowIssue:
    file_index: int
    file_name: str
    row_number: int
    kind: str
    date: str
    description: str
    amount: str
    reason: str
    match: dict = field(default_factory=dict)
    differences: list[str] = field(default_factory=list)
    exclusion_only: bool = False

    @property
    def key(self) -> str:
        return f"{self.file_index}:{self.row_number}"

    def as_dict(self) -> dict:
        return {"key": self.key, "file_index": self.file_index, "file_name": self.file_name,
                "row_number": self.row_number, "kind": self.kind, "date": self.date,
                "description": self.description, "amount": self.amount, "reason": self.reason,
                "match": self.match, "differences": self.differences,
                "exclusion_only": self.exclusion_only or self.kind == ISSUE_UNREADABLE}


def _money(minor: int | None) -> str:
    return "—" if minor is None else f"{minor / 100:,.2f}"


def _original(row: "parsers.ParsedBankRow", *names: str) -> str:
    for name in names:
        value = (row.raw_fields or {}).get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def check_rows(session: Session, files: list[dict]) -> dict:
    """Read every BANK file of the session (`files`: dicts with index,
    file_name, content, source_id) and return what Confirm would import and
    every row that needs a decision. Writes nothing."""
    instruments = {i.id: i for i in session.scalars(select(m.PaymentInstrument))}
    seen: dict[tuple, dict] = {}
    issues: list[RowIssue] = []
    per_file: list[dict] = []
    present_by_month: dict[tuple[int, int], set[int]] = {}
    sha_seen: dict[str, str] = {}
    for entry in files:
        parsed = parsers.parse_csv_bytes(entry["content"])
        source = instruments.get(entry["source_id"])
        sha = parsers.sha256_bytes(entry["content"])
        already = session.scalars(select(m.BankImportBatch).where(m.BankImportBatch.sha256 == sha)).first()
        hints = sorted({r.account_hint for r in parsed.rows if r.account_hint})
        # The stored transactions this file could repeat: one query per file.
        dates = [r.posting_date for r in parsed.rows if r.posting_date is not None]
        stored_by_key: dict[tuple, list] = {}
        if dates:
            for t in session.scalars(select(m.FinancialTransaction).where(
                    m.FinancialTransaction.posting_date >= min(dates),
                    m.FinancialTransaction.posting_date <= max(dates)).order_by(m.FinancialTransaction.id)):
                stored_by_key.setdefault((t.posting_date, bank_service.comparison_description(t),
                                          t.amount_minor), []).append(t)
        dated_rows = [r.posting_date for r in parsed.rows if r.posting_date is not None]
        same_content_as = sha_seen.get(sha)
        sha_seen.setdefault(sha, entry["file_name"])
        stats = {"index": entry["index"], "file_name": entry["file_name"], "rows": len(parsed.rows),
                 "format": parsed.detected_format, "source": source.display_name if source else None,
                 "in_file_identifiers": hints,
                 "period_start": min(dated_rows).isoformat() if dated_rows else None,
                 "period_end": max(dated_rows).isoformat() if dated_rows else None,
                 "same_content_as": same_content_as,
                 "already_imported_batch": already.id if already is not None else None}
        # A byte-identical file (already imported, or a copy of an earlier file
        # of this upload) can never add a distinct operation: the import keeps
        # one batch per content. Its flagged rows can only be excluded.
        exclusion_only_note = None
        if already is not None:
            exclusion_only_note = f"this exact file was already imported as batch #{already.id}: its rows can only be excluded"
        elif same_content_as:
            exclusion_only_note = f"this file has exactly the same content as {same_content_as}: its rows can only be excluded"
        first_issue = len(issues)
        per_file.append(stats)
        for row in parsed.rows:
            original_date = _original(row, "Posting Date", "Post Date", "Transaction Date", "Date")
            original_amount = _original(row, "Amount", "Debit", "Credit")
            if row.parse_status == "UNREADABLE":
                issues.append(RowIssue(
                    entry["index"], entry["file_name"], row.row_number, ISSUE_UNREADABLE,
                    original_date, row.description or _original(row, "Description"), original_amount,
                    "The row cannot be read: " + ("; ".join(row.anomalies) or "missing date or amount")
                    + ". It cannot be imported as it is."))
                continue
            if row.posting_date is not None and source is not None:
                present_by_month.setdefault((row.posting_date.year, row.posting_date.month), set()).add(source.id)
            key = duplicate_key(row.posting_date, row.description, row.amount_minor)
            here = {"file_index": entry["index"], "file_name": entry["file_name"], "row_number": row.row_number,
                    "source": source.display_name if source else "—", "format": parsed.detected_format,
                    "card": row.account_hint, "date": original_date, "description": row.description or "",
                    "amount": original_amount}
            stored = stored_by_key.get(key, [])
            if stored:
                t = stored[0]
                other = instruments.get(t.payment_instrument_id)
                batch = session.get(m.BankImportBatch, t.import_batch_id) if t.import_batch_id else None
                differences = []
                if other is not None and source is not None and other.id != source.id:
                    differences.append(f"different Source: stored on {other.display_name}, this file is {source.display_name}")
                differences.append("currency: USD on both (bank and card statements carry no other currency)")
                issues.append(RowIssue(
                    entry["index"], entry["file_name"], row.row_number, ISSUE_DUPLICATE_DB,
                    original_date, row.description or "", original_amount,
                    "Same date, description and amount as a transaction already stored.",
                    match={"origin": "database", "transaction_id": t.id,
                           "source": other.display_name if other else "—",
                           "date": t.posting_date.isoformat() if t.posting_date else "",
                           "description": t.description_original, "amount": _money(t.amount_minor),
                           "file": batch.original_file_name if batch else "—",
                           "row_number": t.source_row_number},
                    differences=differences))
            elif key in seen:
                first = seen[key]
                differences = []
                if first["file_index"] == entry["index"]:
                    differences.append("same file: may be two genuine purchases on the same day")
                else:
                    if first["format"] != parsed.detected_format:
                        differences.append(f"different layout: {first['format']} vs {parsed.detected_format}")
                    if first["source"] != here["source"]:
                        differences.append(f"different Source: {first['source']} vs {here['source']}")
                if first.get("card") != here.get("card") and (first.get("card") or here.get("card")):
                    differences.append(f"in-file card: {first.get('card') or '—'} vs {here.get('card') or '—'}")
                issues.append(RowIssue(
                    entry["index"], entry["file_name"], row.row_number, ISSUE_DUPLICATE_UPLOAD,
                    original_date, row.description or "", original_amount,
                    "Same date, description and amount as an earlier row of this upload.",
                    match={"origin": "upload", "file": first["file_name"], "row_number": first["row_number"],
                           "source": first["source"], "date": first["date"],
                           "description": first["description"], "amount": first["amount"]},
                    differences=differences))
            else:
                seen[key] = here
        if exclusion_only_note:
            for issue in issues[first_issue:]:
                issue.differences.insert(0, exclusion_only_note)
                issue.exclusion_only = True
    # A Source the month EXPECTS but this upload does not bring: a warning,
    # never a blocking issue — the same expectation rule as the Import Preview.
    from . import import_preview
    active = [i for i in instruments.values() if i.status == "ACTIVE" and i.is_payment_source]
    expected_missing = []
    for month in sorted(present_by_month):
        view = import_preview._period_view(session, month, active, instruments, present_by_month[month], set())
        if view["missing"]:
            expected_missing.append({"month": view["month"], "label": view["label"],
                                     "controlled": view["controlled"], "missing": view["missing"]})
    return {"files": per_file, "issues": [i.as_dict() for i in issues], "expected_missing": expected_missing}


# ---------------------------------------------------------------------------
# Confirm — import with the person's decisions
# ---------------------------------------------------------------------------

def import_confirmed(
    session: Session, *, files: list[dict], issues: list[dict], decisions: dict[str, str],
    uploaded_by_account_id: int | None,
) -> list["bank_service.ImportResult"]:
    """Import every BANK file with its Source, honouring every decision:
    EXCLUDE leaves the row out (kept in the import log and in the stored
    original file), IMPORT_DISTINCT saves it as a distinct operation. Refuses
    if any issue is undecided. Nothing is committed here."""
    undecided = [i for i in issues if decisions.get(i["key"]) not in (DECISION_EXCLUDE, DECISION_DISTINCT)]
    invalid = [i for i in issues if i.get("exclusion_only") and decisions.get(i["key"]) != DECISION_EXCLUDE]
    if undecided or invalid:
        raise ValueError(f"{len(undecided) + len(invalid)} row(s) still need a decision before Confirm Import.")
    by_file: dict[int, list[dict]] = {}
    for issue in issues:
        by_file.setdefault(issue["file_index"], []).append(issue)
    results = []
    for entry in files:
        file_issues = by_file.get(entry["index"], [])
        excluded = {i["row_number"] for i in file_issues if decisions[i["key"]] == DECISION_EXCLUDE}
        distinct = {i["row_number"] for i in file_issues if decisions[i["key"]] == DECISION_DISTINCT}
        log = {"source_id": entry["source_id"], "decisions": [
            {**{k: i[k] for k in ("row_number", "kind", "date", "description", "amount", "reason", "match")},
             "decision": decisions[i["key"]]} for i in file_issues]}
        results.append(bank_service.import_csv(
            session, file_bytes=entry["content"], original_file_name=entry["file_name"],
            uploaded_by_account_id=uploaded_by_account_id, payment_instrument_id=entry["source_id"],
            excluded_row_numbers=excluded, distinct_row_numbers=distinct,
            import_log=json.dumps(log, default=str),
        ))
    return results
