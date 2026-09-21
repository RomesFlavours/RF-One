"""Import a fixed chart of accounts as the What catalog
(BANK_CLASSIFICATION_BOOTSTRAP_001).

What a What is has not changed: one line of a Profit & Loss statement or
of a Balance Sheet (`BankAccountingClassification`, §12/§13). This module
only adds a way to LOAD such a plan from the accountant's own file
instead of typing it in one row at a time.

Three rules shape everything here:

* **Structure only.** A chart of accounts is names, codes and hierarchy.
  Amounts, balances and periods are figures ABOUT accounts, never part of
  an account, and are refused rather than silently ignored — a file whose
  "code" column holds a balance is a file that was misread.
* **Preview before write, always.** `parse` returns rows and anomalies
  and touches nothing. `apply_import` is a separate call that takes the
  parsed result back. There is no path from an upload straight to the
  database.
* **Nothing is invented.** A missing statement type is an anomaly, not a
  default. A missing code produces a DETERMINISTIC technical code derived
  from the statement type and the hierarchical path, clearly marked as
  generated — so re-importing the same catalog produces the same codes
  and therefore no duplicates, and nobody mistakes a generated code for
  the accountant's own.

Re-importing an identical catalog is idempotent. A code that already
exists with a DIFFERENT meaning is a conflict reported for a human, never
an overwrite: a What already used by a decision must never change meaning
under the historical snapshots that reference it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import classification as classification_service

PROFIT_LOSS = classification_service.PROFIT_LOSS
BALANCE_SHEET = classification_service.BALANCE_SHEET

GENERATED_CODE_PREFIX = "GEN"
GENERATED_CODE_MARKER = "[generated technical code]"

# Column names accepted for each field, matched case- and separator-
# insensitively. Deliberately a fixed vocabulary rather than a guess at
# what an arbitrary header might mean: an unrecognized header is reported,
# never assumed.
_HEADER_ALIASES = {
    "statement_type": (
        "statement type", "statement", "statementtype", "report", "prospetto",
        "tipo prospetto", "pl bs", "p&l bs",
    ),
    "code": ("code", "account code", "account", "codice", "conto", "account number", "acct"),
    "name": ("name", "account name", "description", "denominazione", "nome", "voce", "label"),
    "parent": ("parent", "parent code", "parent account", "padre", "parent name", "group"),
    "level": ("level", "livello", "depth", "indent"),
    "row_type": ("type", "row type", "kind", "tipo riga", "category type"),
}

_PROFIT_LOSS_HINTS = (
    "p&l", "pl", "profit", "profit and loss", "profit & loss", "income",
    "income statement", "conto economico", "ce",
)
_BALANCE_SHEET_HINTS = (
    "bs", "balance", "balance sheet", "stato patrimoniale", "sp", "patrimoniale",
)

# A row whose name reads as a subtotal is NOT an account. It is reported as
# such and excluded from the import rather than becoming a phantom account
# that would then be selectable as a What.
_TOTAL_PATTERNS = (
    re.compile(r"^\s*total\b", re.I),
    re.compile(r"\btotal\s*$", re.I),
    re.compile(r"^\s*totale\b", re.I),
    re.compile(r"^\s*sub\s*total\b", re.I),
    re.compile(r"^\s*subtotal\b", re.I),
    re.compile(r"^\s*grand\s+total\b", re.I),
    re.compile(r"^\s*net\s+(income|profit|loss)\b", re.I),
)

_AMOUNT_LIKE = re.compile(r"^[\s(]*[-+$€£]?\s*[\d.,]+\s*\)?$")


def _normalize_header(value: str | None) -> str:
    return re.sub(r"[^a-z0-9&]+", " ", (value or "").strip().lower()).strip()


def _looks_like_total(name: str) -> bool:
    return any(pattern.search(name) for pattern in _TOTAL_PATTERNS)


def _normalize_statement_type(raw: str | None) -> str | None:
    text = _normalize_header(raw)
    if not text:
        return None
    if text in {PROFIT_LOSS.lower().replace("_", " "), "profit loss"}:
        return PROFIT_LOSS
    if text in {BALANCE_SHEET.lower().replace("_", " ")}:
        return BALANCE_SHEET
    for hint in _BALANCE_SHEET_HINTS:
        if text == hint or text.startswith(hint + " "):
            return BALANCE_SHEET
    for hint in _PROFIT_LOSS_HINTS:
        if text == hint or text.startswith(hint + " "):
            return PROFIT_LOSS
    return None


def generated_code(statement_type: str, path: list[str]) -> str:
    """A stable technical code for a plan that carries none of its own.

    Derived from the statement type and the full hierarchical path, so the
    SAME catalog always yields the SAME codes — which is what makes a
    re-import idempotent instead of duplicating every account. The `GEN-`
    prefix and the digest make it obvious this is RF-One's own technical
    identifier, never the accountant's."""
    canonical = statement_type + "\x1f" + "\x1f".join(
        re.sub(r"\s+", " ", part).strip().upper() for part in path if part
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12].upper()
    return f"{GENERATED_CODE_PREFIX}-{digest}"


@dataclass
class ParsedWhatRow:
    """One row of the uploaded plan, as understood. `anomalies` being
    non-empty means the row is NOT importable and says exactly why."""

    source_row_number: int
    statement_type: str | None
    code: str | None
    code_is_generated: bool
    name: str
    parent_code: str | None
    level: int
    row_type: str          # ACCOUNT | HEADING | TOTAL
    source_label: str
    anomalies: list[str] = field(default_factory=list)

    @property
    def importable(self) -> bool:
        return self.row_type == "ACCOUNT" and not self.anomalies


@dataclass
class ParsedWhatCatalog:
    rows: list[ParsedWhatRow] = field(default_factory=list)
    file_anomalies: list[str] = field(default_factory=list)
    detected_headers: dict[str, str] = field(default_factory=dict)
    sheet_name: str | None = None

    @property
    def importable_rows(self) -> list[ParsedWhatRow]:
        return [row for row in self.rows if row.importable]

    @property
    def total_rows(self) -> list[ParsedWhatRow]:
        return [row for row in self.rows if row.row_type == "TOTAL"]

    @property
    def heading_rows(self) -> list[ParsedWhatRow]:
        return [row for row in self.rows if row.row_type == "HEADING"]

    @property
    def rejected_rows(self) -> list[ParsedWhatRow]:
        return [row for row in self.rows if row.anomalies]

    @property
    def is_importable(self) -> bool:
        return not self.file_anomalies and bool(self.importable_rows)


# ---------------------------------------------------------------------------
# Reading the file
# ---------------------------------------------------------------------------


def _read_csv(payload: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("The file could not be decoded as text.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx(payload: bytes, sheet_name: str | None) -> tuple[list[list[str]], str]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    try:
        name = sheet_name or workbook.sheetnames[0]
        if name not in workbook.sheetnames:
            raise ValueError(
                f"Sheet {name!r} is not in this workbook. Available: "
                f"{', '.join(workbook.sheetnames)}."
            )
        worksheet = workbook[name]
        rows = [
            ["" if value is None else str(value) for value in row]
            for row in worksheet.iter_rows(values_only=True)
        ]
        return rows, name
    finally:
        workbook.close()


def sheet_names(payload: bytes, file_name: str) -> list[str]:
    """The sheets a workbook offers, so the operator picks one instead of
    RF-One guessing which sheet holds the plan."""
    if not file_name.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return []
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse(
    payload: bytes, *, file_name: str, sheet_name: str | None = None,
    default_statement_type: str | None = None,
) -> ParsedWhatCatalog:
    """Read the plan and report what it contains. Writes nothing.

    `default_statement_type` is used ONLY when the file has no statement
    column at all — a single-statement export, which is how most P&L and
    Balance Sheet files arrive. It is an explicit operator statement about
    the whole file, never a guess about an individual row."""
    result = ParsedWhatCatalog(sheet_name=sheet_name)

    lower = file_name.lower()
    try:
        if lower.endswith((".xlsx", ".xlsm")):
            raw_rows, used_sheet = _read_xlsx(payload, sheet_name)
            result.sheet_name = used_sheet
        elif lower.endswith(".xls"):
            # Legacy .xls needs a separate engine that this repository does
            # not depend on. Saying so is better than a partial read of a
            # binary format the accountant will then trust.
            result.file_anomalies.append(
                "Legacy .xls is not supported — no reader for it is installed. Re-save the plan "
                "as .xlsx or .csv and upload that."
            )
            return result
        elif lower.endswith((".csv", ".txt")):
            raw_rows = _read_csv(payload)
        else:
            result.file_anomalies.append(
                f"Unsupported file type {file_name!r}. Upload a .csv or .xlsx chart of accounts."
            )
            return result
    except ValueError as exc:
        result.file_anomalies.append(str(exc))
        return result
    except Exception as exc:  # noqa: BLE001 — surfaced verbatim, never swallowed
        result.file_anomalies.append(f"The file could not be read: {exc}")
        return result

    raw_rows = [row for row in raw_rows if any((cell or "").strip() for cell in row)]
    if not raw_rows:
        result.file_anomalies.append("The file contains no rows.")
        return result

    # --- header ------------------------------------------------------------
    header_index = None
    columns: dict[str, int] = {}
    for index, row in enumerate(raw_rows[:10]):
        normalized = [_normalize_header(cell) for cell in row]
        found = {
            field_name: position
            for field_name, aliases in _HEADER_ALIASES.items()
            for position, cell in enumerate(normalized)
            if cell in aliases
        }
        if "name" in found:
            header_index = index
            columns = found
            break

    if header_index is None:
        result.file_anomalies.append(
            "No header row was recognized. The plan needs at least a column named "
            "'Name' (or 'Account Name'); 'Code', 'Parent', 'Level' and 'Statement Type' are "
            "used when present."
        )
        return result

    result.detected_headers = {
        field_name: (raw_rows[header_index][position] or "").strip()
        for field_name, position in columns.items()
    }

    if "statement_type" not in columns and default_statement_type is None:
        result.file_anomalies.append(
            "This file has no Statement Type column, and no statement type was stated for the "
            "upload. A What must be a Profit & Loss line or a Balance Sheet line — RF-One will "
            "not guess which."
        )
        return result

    if default_statement_type is not None and default_statement_type not in (
        PROFIT_LOSS, BALANCE_SHEET
    ):
        result.file_anomalies.append(
            f"Statement type must be {PROFIT_LOSS} or {BALANCE_SHEET}."
        )
        return result

    # --- rows ---------------------------------------------------------------
    path_by_level: dict[int, str] = {}
    code_by_level: dict[int, str] = {}

    for offset, row in enumerate(raw_rows[header_index + 1:], start=header_index + 2):
        def cell(field_name: str) -> str:
            position = columns.get(field_name)
            if position is None or position >= len(row):
                return ""
            return (row[position] or "").strip()

        name = cell("name")
        if not name:
            continue

        anomalies: list[str] = []
        statement_type = (
            _normalize_statement_type(cell("statement_type"))
            if "statement_type" in columns else default_statement_type
        )
        if statement_type is None:
            anomalies.append(
                f"Statement type {cell('statement_type')!r} is not recognizable as "
                "Profit & Loss or Balance Sheet."
            )

        raw_level = cell("level")
        try:
            level = int(float(raw_level)) if raw_level else 0
        except ValueError:
            level = 0
            anomalies.append(f"Level {raw_level!r} is not a number; treated as top level.")
        level = max(level, 0)

        code = cell("code") or None
        if code and _AMOUNT_LIKE.match(code) and len(code) > 8:
            # A code column holding what looks like a balance means the file
            # was read against the wrong columns. Refusing beats importing a
            # figure as an account identifier.
            anomalies.append(
                f"The code column holds {code!r}, which looks like an amount rather than an "
                "account code. Amounts, balances and periods are never part of a What."
            )

        explicit_row_type = _normalize_header(cell("row_type"))
        if _looks_like_total(name) or explicit_row_type in ("total", "subtotal", "totale"):
            row_type = "TOTAL"
        elif explicit_row_type in ("heading", "header", "group", "section", "intestazione"):
            row_type = "HEADING"
        elif not code and not cell("parent") and level == 0 and "code" in columns:
            # A row with no code at all in a file that HAS a code column is a
            # heading in every plan seen so far — reported as such rather than
            # imported as an account.
            row_type = "HEADING"
        else:
            row_type = "ACCOUNT"

        path_by_level[level] = name
        for deeper in [key for key in path_by_level if key > level]:
            path_by_level.pop(deeper, None)
            code_by_level.pop(deeper, None)
        path = [path_by_level[key] for key in sorted(path_by_level) if key <= level]

        parent_code = cell("parent") or None
        if parent_code is None and level > 0:
            parent_code = code_by_level.get(level - 1)

        code_is_generated = False
        if not code:
            code = generated_code(statement_type or "UNKNOWN", path)
            code_is_generated = True
        code_by_level[level] = code

        result.rows.append(ParsedWhatRow(
            source_row_number=offset,
            statement_type=statement_type,
            code=code,
            code_is_generated=code_is_generated,
            name=name,
            parent_code=parent_code,
            level=level,
            row_type=row_type,
            source_label=(
                f"{file_name}"
                + (f" · sheet {result.sheet_name}" if result.sheet_name else "")
                + f" · row {offset}"
            ),
            anomalies=anomalies,
        ))

    # --- cross-row validation ----------------------------------------------
    by_code: dict[str, ParsedWhatRow] = {}
    for parsed in result.rows:
        if parsed.row_type != "ACCOUNT" or not parsed.code:
            continue
        clash = by_code.get(parsed.code)
        if clash is not None and clash.name.strip().casefold() != parsed.name.strip().casefold():
            parsed.anomalies.append(
                f"Code {parsed.code} is already used in this file by {clash.name!r} "
                f"(row {clash.source_row_number}). One code cannot mean two accounts."
            )
        else:
            by_code[parsed.code] = parsed

    for parsed in result.rows:
        if parsed.row_type != "ACCOUNT" or not parsed.parent_code:
            continue
        parent = by_code.get(parsed.parent_code)
        if parent is None:
            parsed.anomalies.append(
                f"Parent {parsed.parent_code!r} is not an account in this file."
            )
        elif parent.statement_type != parsed.statement_type:
            # A P&L line under a Balance Sheet parent is a misread file, not
            # a legitimate hierarchy.
            parsed.anomalies.append(
                f"Parent {parsed.parent_code} is a {parent.statement_type} account while this "
                f"row is {parsed.statement_type}. A parent and a child must belong to the same "
                "statement."
            )

    if not result.importable_rows and not result.file_anomalies:
        result.file_anomalies.append(
            "No importable account row was found — every row was a heading, a total, or carried "
            "an anomaly."
        )
    return result


# ---------------------------------------------------------------------------
# Importing
# ---------------------------------------------------------------------------


@dataclass
class ImportOutcome:
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    skipped_totals: int = 0
    skipped_headings: int = 0
    rejected: int = 0

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def apply_import(
    session: Session, parsed: ParsedWhatCatalog, *, source_note: str | None = None,
) -> ImportOutcome:
    """Write the importable rows, after a human has seen the preview.

    Idempotent: a code that already exists with the SAME name is left
    untouched and counted as unchanged, so re-importing an identical
    catalog changes nothing. A code that exists with a DIFFERENT name is a
    CONFLICT — reported, never overwritten, because a What already
    referenced by a decision must not change meaning under the historical
    snapshots that point at it. Nothing is ever deleted.

    Raises `ValueError` before writing anything if the parse produced
    file-level anomalies: there is no partial import."""
    if parsed.file_anomalies:
        raise ValueError(
            "This file cannot be imported: " + "; ".join(parsed.file_anomalies)
        )

    outcome = ImportOutcome(
        skipped_totals=len(parsed.total_rows),
        skipped_headings=len(parsed.heading_rows),
        rejected=len(parsed.rejected_rows),
    )

    existing = {
        row.code: row for row in session.scalars(select(m.BankAccountingClassification)).all()
    }

    # Two passes: every account is created before any parent is linked, so
    # a child listed above its parent still resolves.
    created_by_code: dict[str, m.BankAccountingClassification] = {}
    for parsed_row in parsed.importable_rows:
        current = existing.get(parsed_row.code)
        if current is not None:
            if current.name.strip().casefold() == parsed_row.name.strip().casefold():
                outcome.unchanged.append(parsed_row.code)
            else:
                outcome.conflicts.append(
                    f"{parsed_row.code}: already exists as {current.name!r}, the file says "
                    f"{parsed_row.name!r}. Not overwritten."
                )
            continue

        description_parts = [f"Imported from {parsed_row.source_label}."]
        if parsed_row.code_is_generated:
            description_parts.append(
                f"{GENERATED_CODE_MARKER} — the source plan carried no account code, so this "
                "code was derived deterministically from the statement type and the account's "
                "position in the hierarchy."
            )
        if source_note:
            description_parts.append(source_note)

        classification = m.BankAccountingClassification(
            code=parsed_row.code,
            name=parsed_row.name,
            statement_type=parsed_row.statement_type,
            description=" ".join(description_parts),
            active=True,
        )
        session.add(classification)
        created_by_code[parsed_row.code] = classification
        outcome.created.append(parsed_row.code)

    session.flush()

    for parsed_row in parsed.importable_rows:
        if not parsed_row.parent_code or parsed_row.code not in created_by_code:
            continue
        parent = created_by_code.get(parsed_row.parent_code) or existing.get(parsed_row.parent_code)
        if parent is None:
            continue
        try:
            classification_service.update_accounting_classification(
                session,
                classification_id=created_by_code[parsed_row.code].id,
                name=parsed_row.name,
                statement_type=parsed_row.statement_type,
                parent_id=parent.id,
                description=created_by_code[parsed_row.code].description,
            )
        except ValueError as exc:
            # A cycle or a cross-statement parent is reported; the account
            # itself stays, unparented, rather than the whole import failing.
            outcome.conflicts.append(f"{parsed_row.code}: parent not linked — {exc}")

    session.flush()
    return outcome
