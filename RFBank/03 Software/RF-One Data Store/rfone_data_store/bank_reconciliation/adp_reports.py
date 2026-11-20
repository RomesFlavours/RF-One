"""Bank evidence from ADP Payroll Summary workbooks. No payroll ledger writes."""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select

from .. import models as m

KIND = "ADP_PAYROLL_SUMMARY"


def reports(db):
    return [json.loads(p) for p in db.scalars(select(m.BankFlowArtifact.payload)
            .where(m.BankFlowArtifact.kind == KIND).order_by(m.BankFlowArtifact.id))]


def name_key(name):
    return tuple(sorted(re.findall(r"[^\W_]+", name.casefold())))


def parse(content):
    import openpyxl
    # Read only workbook tables, never formulas, macros or links to other files.
    with ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError("Il report Excel supera la dimensione leggibile.")
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        for sheet in book:
            rows = iter(sheet.values)
            company = ""
            summary = sheet.title.strip().casefold() == "payroll summary"
            for _ in range(32):
                cells = [str(v or "").strip() for v in next(rows, ())]
                for v in cells:
                    if v.startswith("Company:"):
                        company = v.partition(":")[2].strip()
                    if v.casefold() == "report: payroll summary":
                        summary = True
                if summary and {"Name", "Net Pay", "Check Date"} <= set(cells):
                    break
            else:
                continue
            cols = [cells.index(k) for k in ("Name", "Net Pay", "Check Date")]
            payments = []
            for row in rows:
                name, amount, day = [row[i] if i < len(row) else None for i in cols]
                if not day and not name:
                    continue
                if not day and "total" in str(name).casefold():
                    continue
                try:
                    if isinstance(day, datetime):
                        day = day.date()
                    elif not isinstance(day, date):
                        day = datetime.strptime(re.sub(r"\s*-\s*Void$", "", str(day).strip(), flags=re.I).strip(), "%m/%d/%Y").date()
                    cents = Decimal(str(amount).replace(",", "").strip()) * 100
                    if not name or not cents.is_finite() or cents != cents.to_integral_value():
                        raise ValueError()
                except (ValueError, InvalidOperation):
                    raise ValueError("Data, nominativo o netto illeggibile nel report ADP.") from None
                payments.append([str(name).strip(), int(cents), day.isoformat()])
            if not payments:
                raise ValueError("Il report ADP non contiene pagamenti leggibili.")
            return company, payments
    finally:
        book.close()
    raise ValueError("Formato Excel non riconosciuto. Per ADP scegli il report Payroll Summary.")


def ingest(db, filename, content, account_id):
    digest = hashlib.sha256(content).hexdigest()
    for saved in reports(db):
        if saved["digest"] == digest:
            return saved, False
    try:
        company, payments = parse(content)
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("Report Excel illeggibile.") from exc
    saved = dict(file_name=filename, digest=digest, company=company, payments=payments,
                 days=sorted({p[2] for p in payments}))
    db.add(m.BankFlowArtifact(kind=KIND, account_id=account_id, payload=json.dumps(saved)))
    db.flush()
    return saved, True


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
