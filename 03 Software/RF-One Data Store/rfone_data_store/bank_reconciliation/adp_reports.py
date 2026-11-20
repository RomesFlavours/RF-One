"""Bank evidence from ADP Payroll Summary workbooks. No payroll ledger writes.

ADP is a documentary source kept separate from bank movements (same principle as Zelle and PayPal):

* The original workbook is stored once in `bank_flow_artifacts` (kind ADP_PAYROLL_SUMMARY), keyed by its SHA-256:
  importing the same file again never creates new rows.
* Every report row is kept as read, including void rows, payments made outside ADP and zero values, with the
  original cell values, the source file and the Excel row number. Projection tables (no business decisions):
  `bank_adp_reports` (one row per file) and `bank_adp_payroll_lines` (one row per report line).
* A file is accepted only when its payment count (see `payment_count`) and every economic total equal the report's own
  "Company Totals and Count" row; otherwise it is rejected atomically.
* Nothing here links ADP rows to bank movements, classifies them or creates rules or allocations.
"""
import base64
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select, text

from .. import models as m

KIND = "ADP_PAYROLL_SUMMARY"

# Report column -> line field. Amount columns are stored in minor units (cents).
COLUMNS = {
    "Pay Frequency": "pay_frequency", "Department": "department", "Check Date": "check_date_original",
    "Name": "name", "Hours": "hours", "Total Paid": "total_paid_minor", "Tax Withheld": "tax_withheld_minor",
    "Deductions": "deductions_minor", "Net Pay": "net_pay_minor",
    "Payment Details/Check No": "payment_details_original", "Employer Liability": "employer_liability_minor",
    "Total Expenses": "total_expenses_minor",
}
AMOUNTS = ("total_paid_minor", "tax_withheld_minor", "deductions_minor", "net_pay_minor",
           "employer_liability_minor", "total_expenses_minor")
REQUIRED = ("Name", "Check Date", "Net Pay")


def reports(db):
    return [json.loads(p) for p in db.scalars(select(m.BankFlowArtifact.payload)
            .where(m.BankFlowArtifact.kind == KIND).order_by(m.BankFlowArtifact.id))]


def name_key(name):
    return tuple(sorted(re.findall(r"[^\W_]+", name.casefold())))


def _json_cell(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _decimal(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return Decimal(0)
    d = Decimal(str(v).replace(",", "").strip())
    if not d.is_finite():
        raise InvalidOperation()
    return d


def _cents(v):
    d = _decimal(v) * 100
    if d != d.to_integral_value():
        raise InvalidOperation()
    return int(d)


def _check_date(v):
    """('2026-01-21', is_void) from '01/21/2026 ' or '01/21/2026  - Void' or a real date cell."""
    if isinstance(v, datetime):
        return v.date().isoformat(), False
    if isinstance(v, date):
        return v.isoformat(), False
    raw = str(v or "").strip()
    void = bool(re.search(r"-\s*Void$", raw, flags=re.I))
    day = re.sub(r"\s*-\s*Void$", "", raw, flags=re.I).strip()
    return datetime.strptime(day, "%m/%d/%Y").date().isoformat(), void


def _parse_sheet(sheet):
    rows = list(sheet.values)
    meta = {"company": "", "report_title": "", "period_from": "", "period_to": ""}
    header_index = None
    for i, row in enumerate(rows[:32]):
        cells = [str(v or "").strip() for v in (row or ())]
        for v in cells:
            if v.startswith("Company:"):
                meta["company"] = v.partition(":")[2].strip()
            elif v.startswith("Report:"):
                meta["report_title"] = v.partition(":")[2].strip()
            elif v.startswith("Check Dates From:"):
                meta["period_from"] = v.partition(":")[2].strip()
            elif v.startswith("To:"):
                meta["period_to"] = v.partition(":")[2].strip()
        if set(REQUIRED) <= set(cells):
            header_index = i
            break
    is_summary = (sheet.title.strip().casefold() == "payroll summary"
                  or meta["report_title"].casefold() == "payroll summary")
    if header_index is None or not is_summary:
        return None
    headers = [str(v or "").strip() for v in rows[header_index]]
    position = {h: i for i, h in enumerate(headers) if h}
    lines, declared, declared_count = [], None, None
    pending_totals = False
    for i in range(header_index + 1, len(rows)):
        row = list(rows[i] or ())
        cell = lambda h: row[position[h]] if h in position and position[h] < len(row) else None
        first = str(row[0] if row else "").strip()
        if first.startswith("Company Totals and Count"):
            declared_count = int(re.search(r"(\d+)\s*$", first).group(1))
            pending_totals = True
            continue
        if pending_totals:
            if any(v not in (None, "") for v in row):
                declared = row
                pending_totals = False
            continue
        if declared is not None:
            break          # "Pay Frequency Totals" and anything after the company totals
        if not str(cell("Name") or "").strip() and not str(cell("Check Date") or "").strip():
            continue       # blank spacer row
        try:
            check_date, void = _check_date(cell("Check Date"))
            line = {"source_row": i + 1, "check_date": check_date, "is_void": void,
                    "raw": [_json_cell(v) for v in row]}
            for header, field in COLUMNS.items():
                value = cell(header)
                if field in AMOUNTS:
                    line[field] = _cents(value)
                elif field == "hours":
                    line[field] = str(_decimal(value))
                else:
                    line[field] = "" if value is None else str(value)
            if not line["name"].strip():
                raise ValueError()
        except (ValueError, InvalidOperation, AttributeError):
            raise ValueError(f"Riga {i + 1} del report ADP illeggibile (data, nominativo o importo).") from None
        line["name"] = line["name"].strip()
        line["pay_frequency"] = line["pay_frequency"].strip()
        line["department"] = line["department"].strip()
        line["check_date_original"] = line["check_date_original"].strip()
        # Original cell kept in payment_details_original; the normalized value only drops whitespace/nbsp.
        line["payment_details"] = line["payment_details_original"].replace("\xa0", " ").strip()
        lines.append(line)
    if not lines:
        raise ValueError("Il report ADP non contiene righe leggibili.")
    if declared is None or declared_count is None:
        raise ValueError("Il report ADP non contiene la riga 'Company Totals and Count': impossibile verificarlo.")
    totals = {}
    try:
        for header, field in COLUMNS.items():
            if field in AMOUNTS:
                totals[field] = _cents(declared[position[header]])
            elif field == "hours":
                totals[field] = str(_decimal(declared[position[header]]))
    except (KeyError, IndexError, ValueError, InvalidOperation):
        raise ValueError("Totali del report ADP illeggibili.") from None
    verify(lines, declared_count, totals)
    return dict(meta, headers=headers, lines=lines, declared_count=declared_count, declared_totals=totals)


def line_totals(lines):
    totals = {f: sum(line[f] for line in lines) for f in AMOUNTS}
    totals["hours"] = str(sum((Decimal(line["hours"]) for line in lines), Decimal(0)))
    return totals


def payment_count(lines):
    """ADP's "Count" counts the payments issued: rows that are not voids and have a net pay other than zero.
    Void rows and zero-net rows (e.g. pay fully absorbed by withholding) are kept but not counted by ADP."""
    return sum(1 for line in lines if not line["is_void"] and line["net_pay_minor"] != 0)


def verify(lines, declared_count, declared_totals):
    """Payment count and every economic total must equal the report's own totals row, to the cent."""
    if payment_count(lines) != declared_count:
        raise ValueError(f"Il report ADP dichiara {declared_count} pagamenti ma ne contiene {payment_count(lines)}.")
    computed = line_totals(lines)
    for field, value in declared_totals.items():
        same = Decimal(computed[field]) == Decimal(value) if field == "hours" else computed[field] == value
        if not same:
            raise ValueError(f"Totale '{field}' del report ADP non coincide con la somma delle righe.")


def parse(content):
    import openpyxl
    # Read only workbook tables, never formulas, macros or links to other files.
    with ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError("Il report Excel supera la dimensione leggibile.")
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        for sheet in book:
            report = _parse_sheet(sheet)
            if report is not None:
                return report
    finally:
        book.close()
    raise ValueError("Formato Excel non riconosciuto. Per ADP scegli il report Payroll Summary.")


def ingest(db, filename, content, account_id):
    digest = hashlib.sha256(content).hexdigest()
    for saved in reports(db):
        if saved["digest"] == digest:
            ensure(db)
            return saved, False
    try:
        report = parse(content)
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("Report Excel illeggibile.") from exc
    lines = report["lines"]
    saved = dict(report, file_name=filename, digest=digest,
                 imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 content_b64=base64.b64encode(content).decode("ascii"),
                 # Compact view used by the Zelle payroll verification (name, net pay, check date).
                 payments=[[l["name"], l["net_pay_minor"], l["check_date"]] for l in lines],
                 days=sorted({l["check_date"] for l in lines}))
    db.add(m.BankFlowArtifact(kind=KIND, account_id=account_id, payload=json.dumps(saved, ensure_ascii=False)))
    db.flush()
    ensure(db)
    return saved, True


# ---------------------------------------------------------------------------
# Projection tables (documentary data only)
# ---------------------------------------------------------------------------

TABLES = (
    """CREATE TABLE IF NOT EXISTS bank_adp_reports (
        id INTEGER PRIMARY KEY REFERENCES bank_flow_artifacts(id),
        file_name TEXT NOT NULL, digest TEXT NOT NULL UNIQUE, company TEXT NOT NULL, report_title TEXT,
        period_from TEXT, period_to TEXT, first_check_date TEXT, last_check_date TEXT,
        line_count INTEGER NOT NULL, declared_count INTEGER NOT NULL, declared_totals TEXT NOT NULL,
        headers TEXT NOT NULL, account_id INTEGER, imported_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS bank_adp_payroll_lines (
        id INTEGER PRIMARY KEY,
        report_id INTEGER NOT NULL REFERENCES bank_adp_reports(id),
        company TEXT NOT NULL, source_row INTEGER NOT NULL,
        pay_frequency TEXT, department TEXT, check_date TEXT NOT NULL, check_date_original TEXT NOT NULL,
        is_void INTEGER NOT NULL, name TEXT NOT NULL, hours TEXT NOT NULL,
        total_paid_minor INTEGER NOT NULL, tax_withheld_minor INTEGER NOT NULL, deductions_minor INTEGER NOT NULL,
        net_pay_minor INTEGER NOT NULL, payment_details TEXT, payment_details_original TEXT,
        employer_liability_minor INTEGER NOT NULL, total_expenses_minor INTEGER NOT NULL,
        raw_cells TEXT NOT NULL,
        UNIQUE (report_id, source_row))""",
    "CREATE INDEX IF NOT EXISTS ix_bank_adp_lines_company_date ON bank_adp_payroll_lines (company, check_date)",
)

LINE_FIELDS = ("company", "source_row", "pay_frequency", "department", "check_date", "check_date_original",
               "is_void", "name", "hours", *AMOUNTS[:4], "payment_details", "payment_details_original",
               *AMOUNTS[4:], "raw_cells")


def ensure(db):
    """Create the tables and project every stored report not yet projected. Idempotent."""
    for statement in TABLES:
        db.execute(text(statement))
    done = set(db.execute(text("SELECT id FROM bank_adp_reports")).scalars())
    for artifact_id, account_id, payload in db.execute(
            select(m.BankFlowArtifact.id, m.BankFlowArtifact.account_id, m.BankFlowArtifact.payload)
            .where(m.BankFlowArtifact.kind == KIND).order_by(m.BankFlowArtifact.id)):
        if artifact_id in done:
            continue
        report = json.loads(payload)
        if "lines" not in report:
            continue       # first-version payload (name/net/date only): no full lines to project
        lines = report["lines"]
        db.execute(text("""INSERT INTO bank_adp_reports (id,file_name,digest,company,report_title,period_from,
            period_to,first_check_date,last_check_date,line_count,declared_count,declared_totals,headers,account_id,
            imported_at) VALUES (:id,:file_name,:digest,:company,:report_title,:period_from,:period_to,:first,:last,
            :line_count,:declared_count,:declared_totals,:headers,:account_id,:imported_at)"""),
            dict(id=artifact_id, file_name=report["file_name"], digest=report["digest"], company=report["company"],
                 report_title=report.get("report_title"), period_from=report.get("period_from"),
                 period_to=report.get("period_to"), first=min(report["days"]), last=max(report["days"]),
                 line_count=len(lines), declared_count=report["declared_count"],
                 declared_totals=json.dumps(report["declared_totals"]), headers=json.dumps(report["headers"]),
                 account_id=account_id, imported_at=report["imported_at"]))
        columns = ",".join(("report_id",) + LINE_FIELDS)
        values = ",".join(":" + f for f in ("report_id",) + LINE_FIELDS)
        db.execute(text(f"INSERT INTO bank_adp_payroll_lines ({columns}) VALUES ({values})"),
                   [dict({f: line.get(f) for f in LINE_FIELDS}, report_id=artifact_id, company=report["company"],
                         is_void=int(line["is_void"]), raw_cells=json.dumps(line["raw"], ensure_ascii=False))
                    for line in lines])


class Payments:
    def __init__(self, saved):
        # Preserve repeated lines in one file, without counting overlapping exports twice.
        facts = Counter()
        for report in saved:
            facts |= Counter((report["company"], name_key(n), amount, day) for n, amount, day in report["payments"])
        self.days = {date.fromisoformat(day) for report in saved for day in report["days"]}
        self.index = defaultdict(list)
        for (company, name, amount, day), count in facts.items():
            if amount <= 0:
                continue
            count -= facts[company, name, -amount, day]
            self.index[name, amount].extend([date.fromisoformat(day)] * count)

    def matches(self, name, amount_minor, day, tolerance):
        if amount_minor >= 0 or not day or not name:
            return []
        return [d for d in self.index.get((name_key(name), -amount_minor), ())
                if abs((d - day).days) <= tolerance]
