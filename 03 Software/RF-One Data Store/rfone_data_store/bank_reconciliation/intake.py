"""Upload and Reconcile — files in, completeness out, no month chosen (BANK_UPLOAD_AND_RECONCILE_001).

The Product Owner's path (2026-11-02, completed 2026-11-03):

    UPLOAD FILES -> CHECK COMPLETENESS -> RECONCILE AUTOMATICALLY -> COMPLETE BY HAND -> EXPORT QBO

The person never selects a month, a period or a monthly session. Files are uploaded as they come; Bank reads
their dates from their content, integrates them, and derives what is missing. This module is the data side of
the first two steps and THE completeness gate every automatic processing goes through (`require_ready`); the
page is `bank_work_routes` in RF-One Web.

INTEGRATING A BANK FILE (`plan_bank_file`, `integrate_bank_file`)
-----------------------------------------------------------------
A file is read by the existing parsers and imported by the existing import (`import_session.import_confirmed`
-> `service.import_csv`). What is new is only which rows are left out, decided automatically:

* the same bytes already imported -> nothing new (the import is idempotent by content hash);
* otherwise rows are compared with the movements already stored ON THE SAME SOURCE with the duplicate key of
  the two-pass import (posting date + normalized description + signed amount), COUNTING occurrences: a file
  with three identical rows (three fans bought the same day) against one stored row adds two. So a file
  uploaded twice adds nothing, a more complete file adds only what was missing, and genuine repeated purchases
  are never merged. Left-out rows stay in the stored original file and in the batch's import log;
* nothing stored is ever changed or deleted: human decisions on existing movements stay as they are.

Rows that cannot be read, and a file whose rows are mostly already stored on ANOTHER Source (probably the wrong
Source), are not decided here: they are file problems the person settles before reconciliation.

COMPLETENESS (`completeness`) — from the files actually received
---------------------------------------------------------------
What a file proves:

* its PERIOD is DECLARED when the export states it — two dates in the file name (`…20260101_20260930…`,
  `orders_from_20260101_to_20261026…`) — or when a person CONFIRMED it (a fact, traced); otherwise the period is
  only INFERRED from its first and last movement, and is shown as such, never as the statement period;
* a movement in a month does not prove the month is covered: only the days of a file's period are covered.

What is required, Source by Source (payment Sources only):

* the WORK STARTS at the reconciliation control start when configured, else on the first day any bank file
  covers. Each Source is required from there (or from the date a person stated it came into use) TO THE LAST
  DAY ITS OWN FILES COVER: a Source whose data stop earlier than the others is reconciled up to its own data
  and listed, never asked for days beyond what was acquired;
* the first movement of a Source does not prove when it opened: when its files begin more than 31 days (or a
  whole calendar month) after the work start and no start date was stated, Bank asks (blocking) — upload the
  earlier file, or state "in use only since then", or "no movements in these dates"; 11–31 days are listed as an
  uncertainty, up to 10 days are normal (the first movement a few days into the work);
* a Source with nessun file at all is neither incomplete nor "not expected" by itself: Bank asks (blocking) —
  upload its file, or "not in use in these dates", "no movements in these dates", "closed";
* a hole between the periods of two files of the same Source is
    - a MISSING STATEMENT (blocking) when both periods are declared or confirmed: the statements prove the gap;
    - a QUESTION (blocking) when the periods are only inferred and the hole spans a whole calendar month or more
      than 31 days: "upload the file, or confirm there were no movements" — days without movements are never
      taken as proof of a missing file, so the person states the fact;
    - an UNCERTAINTY (not blocking) when it is shorter (over 10 days: listed; up to 10 days: normal between
      inferred periods);
* the answers are FACTS kept with who and when (`COVERAGE_FACT` artifacts): no movements in given dates, not
  in use from a date until further notice, in use since a date (also written as the Source's start date), a file's statement
  period. "Closed" uses the existing Source lifecycle. Earlier month resolutions (NO_ACTIVITY, NOT EXPECTED)
  keep counting for their months. There is no generic "ignore the missing files";
* Amazon: when Amazon order reports have been loaded and movements of a Source were already paid through them
  (their Charge Identifier is in a report), that Source's Amazon movements in the work need a report covering
  their date (blocking). Without any report there is no evidence of the dependency: only a note.

Completeness never looks at how single movements are classified: a movement needing a clarification is
manual-reconciliation work and never blocks the automatic run (no circular block). Files waiting for an answer
(`INTAKE_FILE` artifacts in a blocking state) block as well.

THE GATE (`readiness`, `require_ready`)
---------------------------------------
Every path that starts automatic processing (Upload and Reconcile, Configuration → recalculate, the Amazon page,
Guided Reconciliation's runs and AI investigations, the legacy runs) calls `require_ready` server side. Reading,
configuration, simulations that apply nothing and the manual completion of single movements are not gated.

Read-only except `integrate_bank_file` and `record_fact`, which are a person's actions (an upload, an answer).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import import_session, monthly_source, parsers
from . import service as bank_service

ISSUE_ALREADY_STORED = "ALREADY_STORED"     # automatic: the row is already a movement of this Source
WRONG_SOURCE_SHARE = 0.5                    # share of rows stored on another Source that questions the Source
WRONG_SOURCE_MIN_ROWS = 3
SHORT_HOLE_DAYS = 10                        # holes up to this length between inferred periods are normal
LONG_HOLE_DAYS = 31                         # a longer hole (or a whole calendar month) is asked about
TAIL_DAYS = 3                               # a Source ending this many days before the others is listed

GAP_MISSING_STATEMENT = "MISSING_STATEMENT"
GAP_POSSIBLE_MISSING = "POSSIBLE_MISSING"
GAP_START_UNKNOWN = "START_UNKNOWN"
GAP_NO_FILES = "NO_FILES"
GAP_AMAZON_REPORT = "AMAZON_REPORT"

FACT = "COVERAGE_FACT"
INTAKE = "INTAKE_FILE"
ANSWER_NO_MOVEMENTS = "NO_MOVEMENTS"
ANSWER_NOT_IN_USE = "NOT_IN_USE"
ANSWER_IN_USE_SINCE = "IN_USE_SINCE"
ANSWER_CLOSED = "CLOSED"
FACT_STATEMENT_PERIOD = "STATEMENT_PERIOD"
ANSWER_LABELS = {
    ANSWER_NO_MOVEMENTS: 'Non ci sono stati movimenti in queste date',
    ANSWER_NOT_IN_USE: 'Non in uso (da questa data, fino a nuovo avviso)',
    ANSWER_IN_USE_SINCE: 'In uso soltanto dal primo file',
    ANSWER_CLOSED: 'Chiuso / non più utilizzato',
}
# File states (`bank_work_routes`) that need the person before any automatic processing.
BLOCKING_FILE_STATES = ("NEEDS_SOURCE", "SOURCE_INCOMPLETE", "UNREADABLE_ROWS", "CHECK_SOURCE", "NOT_RECOGNIZED",
                        "FAILED")

_AMAZON_TEXT = re.compile(r"AMAZON|AMZN", re.I)
_TOKEN = re.compile(r"[A-Z0-9]+")
_DECLARED = re.compile(r"(?<!\d)(20\d{6})(?!\d)\D{0,4}?(?:to\D{0,3})?(?<!\d)(20\d{6})(?!\d)", re.I)


def _label(instrument) -> str:
    digits = instrument.last_four or (instrument.external_account_identifier or "")[-4:]
    name = instrument.display_name or f"Source #{instrument.id}"
    return name if not digits or digits in name else f"{name} ··{digits}"


def _fmt(day: date | None) -> str:
    return day.strftime("%d %b %Y") if day else "—"


def declared_period(file_name: str | None) -> tuple[date, date] | None:
    """The period an export states in its file name: the first two dates YYYYMMDD in order, at most 400 days
    apart (`Chase3144_Activity20260101_20260930_20261007.csv`, `orders_from_20260101_to_20261026_….csv`). One date
    alone is a download date and states no period."""
    match = _DECLARED.search(file_name or "")
    if not match:
        return None
    try:
        start, end = (datetime.strptime(g, "%Y%m%d").date() for g in match.groups())
    except ValueError:
        return None
    return (start, end) if start <= end and (end - start).days <= 400 else None

# ---------------------------------------------------------------------------
# Integrating a bank file
# ---------------------------------------------------------------------------

@dataclass
class FilePlan:
    """What integrating one bank file into one Source would do. Nothing is written to build it."""

    file_name: str
    source_id: int
    detected_format: str | None
    rows: int = 0
    new_rows: int = 0
    already_stored: int = 0
    unreadable: list[dict] = field(default_factory=list)
    other_source: dict = field(default_factory=dict)          # Source label -> rows stored there
    period_start: date | None = None
    period_end: date | None = None
    already_imported_batch: int | None = None
    excluded: list[dict] = field(default_factory=list)        # the rows left out, as import-log issues

    @property
    def suspected_source(self) -> str | None:
        """The other Source most of this file is already stored on, when that is most of the file."""
        readable = self.rows - len(self.unreadable)
        if not self.other_source or readable < WRONG_SOURCE_MIN_ROWS:
            return None
        label, count = max(self.other_source.items(), key=lambda kv: kv[1])
        return label if count >= WRONG_SOURCE_SHARE * readable else None

    def as_dict(self) -> dict:
        return dict(file_name=self.file_name, source_id=self.source_id, format=self.detected_format,
                    rows=self.rows, new_rows=self.new_rows, already_stored=self.already_stored,
                    unreadable=self.unreadable, other_source=self.other_source,
                    suspected_source=self.suspected_source,
                    period_start=self.period_start.isoformat() if self.period_start else None,
                    period_end=self.period_end.isoformat() if self.period_end else None,
                    already_imported_batch=self.already_imported_batch)


def plan_bank_file(session: Session, *, file_name: str, content: bytes, source_id: int) -> FilePlan:
    """Read a bank file and decide, row by row, what is new for its Source (see the module docstring)."""
    parsed = parsers.parse_csv_bytes(content)
    plan = FilePlan(file_name=file_name, source_id=source_id, detected_format=parsed.detected_format,
                    rows=len(parsed.rows))
    already = session.scalars(select(m.BankImportBatch).where(
        m.BankImportBatch.sha256 == parsers.sha256_bytes(content))).first()
    if already is not None:
        plan.already_imported_batch = already.id
    dates = [r.posting_date for r in parsed.rows if r.posting_date is not None]
    if dates:
        plan.period_start, plan.period_end = min(dates), max(dates)
    stored_same: Counter = Counter()
    stored_other: dict[tuple, Counter] = defaultdict(Counter)
    labels = {i.id: _label(i) for i in session.scalars(select(m.PaymentInstrument))}
    if dates:
        for t in session.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.posting_date >= min(dates),
                m.FinancialTransaction.posting_date <= max(dates))):
            key = (t.posting_date, bank_service.comparison_description(t), t.amount_minor)
            if t.payment_instrument_id == source_id:
                stored_same[key] += 1
            else:
                stored_other[key][labels.get(t.payment_instrument_id, "another Source")] += 1
    seen: Counter = Counter()
    for row in parsed.rows:
        if row.parse_status == "UNREADABLE":
            plan.unreadable.append(dict(row_number=row.row_number, description=row.description or "",
                                        reason="; ".join(row.anomalies) or "missing date or amount"))
            continue
        key = import_session.duplicate_key(row.posting_date, row.description, row.amount_minor)
        seen[key] += 1
        if seen[key] <= stored_same[key]:
            plan.already_stored += 1
            plan.excluded.append(dict(
                key=f"0:{row.row_number}", file_index=0, row_number=row.row_number, kind=ISSUE_ALREADY_STORED,
                date=row.posting_date.isoformat() if row.posting_date else "", description=row.description or "",
                amount=f"{(row.amount_minor or 0) / 100:,.2f}",
                reason="Already stored on this Source (same date, description and amount, counted occurrence "
                       "by occurrence): left out automatically.", match={}))
            continue
        plan.new_rows += 1
        for label in stored_other.get(key, {}):
            plan.other_source[label] = plan.other_source.get(label, 0) + 1
    return plan


def integrate_bank_file(session: Session, *, file_name: str, content: bytes, source_id: int,
                        account_id: int | None, plan: FilePlan | None = None,
                        leave_out_unreadable: bool = False) -> "bank_service.ImportResult":
    """Import the file's new rows into its Source with the existing import; the caller commits.

    Refuses unreadable rows the person has not agreed to leave out: an unreadable row is never imported
    and never dropped silently."""
    plan = plan or plan_bank_file(session, file_name=file_name, content=content, source_id=source_id)
    if plan.unreadable and not leave_out_unreadable:
        raise ValueError(f"{file_name}: {len(plan.unreadable)} row(s) cannot be read. Upload a corrected file, "
                         "or confirm that these rows stay out.")
    issues = list(plan.excluded) + [dict(
        key=f"0:{u['row_number']}", file_index=0, row_number=u["row_number"], kind=import_session.ISSUE_UNREADABLE,
        date="", description=u["description"], amount="", reason="Unreadable row, left out by the person: "
        + u["reason"], match={}, exclusion_only=True) for u in plan.unreadable]
    results = import_session.import_confirmed(
        session, files=[dict(index=0, file_name=file_name, content=content, source_id=source_id)],
        issues=issues, decisions={i["key"]: import_session.DECISION_EXCLUDE for i in issues},
        uploaded_by_account_id=account_id)
    result = results[0]
    if result.created and plan.period_start and plan.period_end:
        # The file covers the days of ALL its rows, also those left out because already stored: the import
        # records the range of the rows it wrote, which would shrink a fuller file to its new days.
        result.batch.date_range_start = min(plan.period_start, result.batch.date_range_start or plan.period_start)
        result.batch.date_range_end = max(plan.period_end, result.batch.date_range_end or plan.period_end)
        session.flush()
    return result



# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------

@dataclass
class Gap:
    """One blocking request: what to upload (or answer) and why."""

    kind: str
    source_id: int | None
    source: str
    start: date
    end: date
    reason: str
    answers: tuple = ()

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.source_id or 0}:{self.start.isoformat()}:{self.end.isoformat()}"

    @property
    def after(self) -> date:
        """The day after the gap: for a START_UNKNOWN gap, the first day of the Source's files."""
        return self.end + timedelta(days=1)

    @property
    def request(self) -> str:
        dates = f"{_fmt(self.start)} – {_fmt(self.end)}"
        if self.kind == GAP_AMAZON_REPORT:
            return f"Carica un report ordini Amazon Business che copra {dates}."
        if self.kind == GAP_MISSING_STATEMENT:
            return f"Carica l’estratto di {self.source} per {dates}."
        if self.kind == GAP_NO_FILES:
            return f"Carica il file di {self.source} per {dates}, oppure indica perché non è presente."
        if self.kind == GAP_START_UNKNOWN:
            return f"{self.source}: carica il file per {dates}, oppure indica da quando è in uso."
        return f"{self.source}: carica il file per {dates}, oppure conferma che non ci sono stati movimenti."


@dataclass
class FilePeriod:
    batch_id: int
    file_name: str
    first: date
    last: date
    start: date
    end: date
    basis: str            # DECLARED (file name) / CONFIRMED (a person) / MOVEMENTS (first and last movement)
    note: str = ""


@dataclass
class SourceCoverage:
    source_id: int
    source: str
    kind: str
    files: list = field(default_factory=list)
    intervals: list = field(default_factory=list)   # [start, end, proven]
    required_from: date | None = None
    required_to: date | None = None
    status: str = ""


@dataclass
class Completeness:
    window_start: date | None
    window_end: date | None
    sources: list
    gaps: list
    uncertainties: list
    notes: list

    @property
    def has_data(self) -> bool:
        return self.window_end is not None

    @property
    def ready(self) -> bool:
        return self.has_data and not self.gaps


def _merge(intervals) -> list[list]:
    """Merge [start, end, proven] intervals that touch; a merged interval is proven only where all parts are."""
    out: list[list] = []
    for start, end, proven in sorted(intervals, key=lambda x: (x[0], x[1])):
        if out and start <= out[-1][1] + timedelta(days=1):
            out[-1][1] = max(out[-1][1], end)
            out[-1][2] = out[-1][2] and proven
        else:
            out.append([start, end, proven])
    return out


def _subtract(span: tuple[date, date], covered: list) -> list[tuple[date, date]]:
    """The parts of `span` that no interval of `covered` (start, end, …) covers."""
    holes, cursor = [], span[0]
    for c in sorted(covered, key=lambda x: x[0]):
        if c[1] < cursor:
            continue
        if c[0] > span[1]:
            break
        if c[0] > cursor:
            holes.append((cursor, min(c[0] - timedelta(days=1), span[1])))
        if c[1] >= span[1]:
            return holes
        cursor = max(cursor, c[1] + timedelta(days=1))
    if cursor <= span[1]:
        holes.append((cursor, span[1]))
    return holes


def _whole_month_inside(start: date, end: date) -> bool:
    first = start if start.day == 1 else (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    last_of_month = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return last_of_month <= end


def facts(session: Session) -> list[dict]:
    """The coverage facts people stated, oldest first."""
    return [dict(json.loads(a.payload), id=a.id) for a in session.scalars(
        select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == FACT).order_by(m.BankFlowArtifact.id))]


def _fact_ranges(session: Session, all_facts: list[dict]) -> dict[int, list]:
    """Per Source, the dates people stated need nessun file: facts, and earlier month resolutions."""
    out: dict[int, list] = defaultdict(list)
    for f in all_facts:
        if f.get("fact") == ANSWER_NO_MOVEMENTS:
            out[f["source_id"]].append((date.fromisoformat(f["start"]), date.fromisoformat(f["end"]), True))
        elif f.get("fact") == ANSWER_NOT_IN_USE:
            # "Not in use" holds until further notice: later days are not asked again (a file of the Source
            # still counts for its own days).
            out[f["source_id"]].append((date.fromisoformat(f["start"]), date.max, True))
    for coverage, month in session.execute(select(m.BankMonthlyInstrumentCoverage, m.BankMonthlySourcePeriod.period_month)
                                           .join(m.BankMonthlySourcePeriod,
                                                 m.BankMonthlySourcePeriod.id == m.BankMonthlyInstrumentCoverage.period_id)):
        if coverage.resolution in (m.RESOLUTION_NO_ACTIVITY, m.RESOLUTION_NOT_EXPECTED):
            start, end = monthly_source.period_bounds(int(month[:4]), int(month[5:7]))
            out[coverage.payment_instrument_id].append((start, end, True))
    return out


def file_periods(session: Session, all_facts: list[dict] | None = None) -> dict[int | None, list[FilePeriod]]:
    """Every accepted bank file with the period it proves, per Source."""
    confirmed = {f["batch_id"]: f for f in (all_facts if all_facts is not None else facts(session))
                 if f.get("fact") == FACT_STATEMENT_PERIOD and f.get("batch_id")}
    out: dict[int | None, list[FilePeriod]] = defaultdict(list)
    for b in session.scalars(select(m.BankImportBatch).where(
            m.BankImportBatch.status != "REJECTED", m.BankImportBatch.date_range_start.is_not(None),
            m.BankImportBatch.date_range_end.is_not(None)).order_by(m.BankImportBatch.id)):
        first, last = b.date_range_start, b.date_range_end
        fp = FilePeriod(b.id, b.original_file_name, first, last, first, last, "MOVEMENTS")
        if b.id in confirmed:
            fp.start, fp.end = date.fromisoformat(confirmed[b.id]["start"]), date.fromisoformat(confirmed[b.id]["end"])
            fp.basis = "CONFIRMED"
        else:
            declared = declared_period(b.original_file_name)
            if declared and declared[0] <= first and last <= declared[1]:
                fp.start, fp.end, fp.basis = declared[0], declared[1], "DECLARED"
            elif declared:
                fp.note = "the dates in the file name do not contain its movements: not used as its period"
        out[b.payment_instrument_id].append(fp)
    return out


def window(session: Session, periods: dict | None = None) -> tuple[date | None, date | None]:
    """Work start (control start, or first day any bank file covers) and the last day any bank file covers."""
    periods = periods if periods is not None else file_periods(session)
    all_files = [fp for files in periods.values() for fp in files]
    if not all_files:
        return None, None
    control = monthly_source.get_control_start_month(session)
    start = monthly_source.period_bounds(int(control[:4]), int(control[5:7]))[0] if control else \
        min(fp.start for fp in all_files)
    end = max(fp.end for fp in all_files)
    return (start, end) if start <= end else (None, None)


def _stated_start(instrument, first_posting: date | None, all_facts: list[dict]) -> date | None:
    """When a person said the Source came into use: an IN_USE_SINCE fact, or a start date recorded earlier than
    its first movement (a derived "birth" equal to the first movement proves nothing)."""
    stated = [date.fromisoformat(f["start"]) for f in all_facts
              if f.get("fact") == ANSWER_IN_USE_SINCE and f.get("source_id") == instrument.id]
    if stated:
        return stated[-1]
    start = instrument.effective_start_date
    return start if start and (first_posting is None or start < first_posting) else None


def completeness(session: Session) -> Completeness:
    all_facts = facts(session)
    periods = file_periods(session, all_facts)
    start, end = window(session, periods)
    notes = []
    if start is None:
        return Completeness(None, None, [], [], [], notes)
    stated_no_file = _fact_ranges(session, all_facts)
    inferred = sum(1 for files in periods.values() for fp in files if fp.basis == "MOVEMENTS")
    if inferred:
        notes.append(f"{inferred} file(s) do not state their statement period: their period is read from their "
                     "first and last movement, and only those days count as covered.")
    sources, gaps, uncertainties = [], [], []
    for instrument in monthly_source.relevant_instruments(session):
        files = periods.get(instrument.id, [])
        cov = SourceCoverage(instrument.id, _label(instrument), instrument.instrument_type, files)
        cov.intervals = _merge((fp.start, fp.end, fp.basis != "MOVEMENTS") for fp in files)
        sources.append(cov)
        closed_end = instrument.effective_end_date if instrument.status == "INACTIVE" else None
        closed = instrument.status == "INACTIVE" and instrument.lifecycle_end_reason is not None
        first_posting = monthly_source.first_posting_date(session, instrument.id)
        stated = _stated_start(instrument, first_posting, all_facts)
        req_from = max(start, stated) if stated else start
        answered = stated_no_file.get(instrument.id, [])
        if closed and (closed_end is None or closed_end < req_from) and not files:
            cov.status = "closed"
            continue
        if not files:
            if stated and stated > end:
                cov.status = "non ancora in uso"
                continue
            holes = _subtract((req_from, end), answered)
            if not holes:
                cov.status = "nessun file necessario (risposta registrata)"
                continue
            cov.status = "nessun file"
            for h_start, h_end in holes:
                gaps.append(Gap(GAP_NO_FILES, instrument.id, cov.source, h_start, h_end,
                                f"Bank non ha file né movimenti di {cov.source}. L’assenza di movimenti "
                                "non dimostra che manchino dati o che il conto sia inutilizzato: indica la situazione corretta.",
                                answers=(ANSWER_NOT_IN_USE, ANSWER_NO_MOVEMENTS, ANSWER_CLOSED)))
            continue
        req_to = min(cov.intervals[-1][1], closed_end) if closed_end else cov.intervals[-1][1]
        cov.required_from, cov.required_to = req_from, req_to
        covered = cov.intervals + [(a, b, True) for a, b, _ in answered]
        first_file = cov.intervals[0][0]
        if not stated and req_from < first_file:
            # The first movement does not prove when the Source opened.
            opening = [h for h in _subtract((req_from, first_file - timedelta(days=1)), answered)]
            for h_start, h_end in opening:
                days = (h_end - h_start).days + 1
                if days <= SHORT_HOLE_DAYS:
                    continue   # the first movement a few days into the work: normal
                if days <= LONG_HOLE_DAYS and not _whole_month_inside(h_start, h_end):
                    uncertainties.append(dict(
                        source_id=instrument.id, start=h_start, end=h_end,
                        text=f"{cov.source}: i file iniziano il {_fmt(first_file)}, {days} giorni dopo l’inizio del controllo. "
                             f"Se hai un estratto per {_fmt(h_start)} – {_fmt(h_end)}, caricalo."))
                    continue
                gaps.append(Gap(GAP_START_UNKNOWN, instrument.id, cov.source, h_start, h_end,
                                f"I file di {cov.source} iniziano il {_fmt(first_file)}, mentre il controllo parte dal "
                                f"{_fmt(start)}. Non è stata dichiarata una data di inizio: il primo movimento non dimostra "
                                "quando il conto o la carta sono entrati in uso.",
                                answers=(ANSWER_IN_USE_SINCE, ANSWER_NO_MOVEMENTS)))
            covered.append((req_from, first_file - timedelta(days=1), True))   # asked above, not twice
        for h_start, h_end in _subtract((req_from, req_to), covered):
            days = (h_end - h_start).days + 1
            before = next((iv for iv in reversed(cov.intervals) if iv[1] < h_start), None)
            after = next((iv for iv in cov.intervals if iv[0] > h_end), None)
            proven = bool(before and after and before[2] and after[2])
            if proven:
                gaps.append(Gap(GAP_MISSING_STATEMENT, instrument.id, cov.source, h_start, h_end,
                                "Queste date sono comprese tra due estratti che dichiarano il proprio periodo: "
                                "manca un estratto.", answers=(ANSWER_NO_MOVEMENTS,)))
            elif days > LONG_HOLE_DAYS or _whole_month_inside(h_start, h_end):
                gaps.append(Gap(GAP_POSSIBLE_MISSING, instrument.id, cov.source, h_start, h_end,
                                f"Nessun file di {cov.source} copre questi {days} giorni e i file non dichiarano il proprio "
                                "periodo. I giorni senza movimenti non dimostrano l’assenza di un file: indica "
                                "la situazione corretta.", answers=(ANSWER_NO_MOVEMENTS,)))
            elif days > SHORT_HOLE_DAYS:
                uncertainties.append(dict(
                    source_id=instrument.id, start=h_start, end=h_end,
                    text=f"{cov.source}: nessun movimento dal {_fmt(h_start)} al {_fmt(h_end)} ({days} giorni). I file "
                         "non dichiarano il periodo: Bank non può sapere se manca un estratto. Se un estratto "
                         "copre questi giorni, caricalo."))
        cov.status = "controllato fino al " + _fmt(req_to)
        if (end - req_to).days > TAIL_DAYS:
            uncertainties.append(dict(
                source_id=instrument.id, start=req_to + timedelta(days=1), end=end, tail=True,
                text=f"{cov.source}: i dati terminano il {_fmt(req_to)} (gli altri file arrivano al {_fmt(end)}). Il controllo arriva "
                     f"fino al {_fmt(req_to)}; carica un file più recente quando disponibile."))
    amazon_gaps, amazon_notes = _amazon(session, start, end)
    return Completeness(start, end, sources, gaps + amazon_gaps, uncertainties, notes + amazon_notes)


# ---------------------------------------------------------------------------
# A person's statement about coverage
# ---------------------------------------------------------------------------

def record_fact(session: Session, *, source_id: int, fact: str, start: date, end: date | None,
                account_id: int | None, note: str | None = None, batch_id: int | None = None) -> dict:
    """Record a person's factual statement, traced (who, when, what). The caller commits.

    NO_MOVEMENTS covers [start, end]; NOT_IN_USE holds from `start` until further notice (`end` is kept as the
    date it was stated for); IN_USE_SINCE also writes the Source's start date (explicit
    configuration); CLOSED closes the Source through the existing lifecycle (`monthly_source.set_source_active`);
    STATEMENT_PERIOD states the period of one file of the Source and must contain its movements."""
    instrument = session.get(m.PaymentInstrument, source_id)
    if instrument is None or not instrument.is_payment_source:
        raise ValueError("Questa richiesta non è più attuale: ricarica la pagina.")
    if fact not in (ANSWER_NO_MOVEMENTS, ANSWER_NOT_IN_USE, ANSWER_IN_USE_SINCE, ANSWER_CLOSED, FACT_STATEMENT_PERIOD):
        raise ValueError("Scegli una delle risposte disponibili.")
    end = end or start
    if end < start:
        raise ValueError("La data finale precede quella iniziale.")
    if fact == FACT_STATEMENT_PERIOD:
        batch = session.get(m.BankImportBatch, batch_id or 0)
        if batch is None or batch.payment_instrument_id != source_id:
            raise ValueError("Il file non appartiene a questo conto o carta.")
        if not (start <= batch.date_range_start and batch.date_range_end <= end):
            raise ValueError(f"The period must contain the file's movements ({_fmt(batch.date_range_start)} – "
                             f"{_fmt(batch.date_range_end)}).")
    if fact == ANSWER_IN_USE_SINCE:
        instrument.effective_start_date = start
    if fact == ANSWER_CLOSED:
        monthly_source.set_source_active(session, instrument=instrument, active=False)
    data = dict(source_id=source_id, source=_label(instrument), fact=fact, start=start.isoformat(),
                end=end.isoformat(), batch_id=batch_id, note=(note or "").strip()[:500] or None,
                account_id=account_id, at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    session.add(m.BankFlowArtifact(kind=FACT, account_id=account_id, payload=json.dumps(data)))
    session.flush()
    return data


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class NotReady(ValueError):
    """Automatic processing refused: the data are not complete."""


@dataclass
class Readiness:
    check: Completeness
    waiting: list

    @property
    def ready(self) -> bool:
        return self.check.ready and not self.waiting

    @property
    def blocking(self) -> int:
        return len(self.waiting) + len(self.check.gaps)


def waiting_files(session: Session) -> list[dict]:
    out = []
    for a in session.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == INTAKE)):
        data = json.loads(a.payload)
        if data.get("state") in BLOCKING_FILE_STATES:
            out.append(dict(id=a.id, file_name=data.get("file_name"), state=data.get("state")))
    return out


def readiness(session: Session) -> Readiness:
    return Readiness(completeness(session), waiting_files(session))


def require_ready(session: Session, *, what: str) -> Readiness:
    """THE server-side gate of every automatic processing. Raises NotReady with what is missing."""
    r = readiness(session)
    if not r.ready:
        if not r.check.has_data:
            detail = "no bank or card file has been uploaded yet"
        else:
            detail = f"{r.blocking} thing(s) to settle (files waiting, missing files or questions)"
        raise NotReady(f"{what} is not available until the data are complete: {detail}. "
                       "Vai a Carica e riconcilia.")
    return r

# ---------------------------------------------------------------------------
# Amazon dependency
# ---------------------------------------------------------------------------

def _day(text: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime((text or "").strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def amazon_reports(session: Session) -> list[dict]:
    """Every Amazon order report loaded (all accounts) with its coverage: DECLARED when the export's file
    name states it (`orders_from_YYYYMMDD_to_YYYYMMDD`), else INFERRED from its first and last order."""
    out = []
    for a in session.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == "AMAZON_REPORT")
                             .order_by(m.BankFlowArtifact.id)):
        report = json.loads(a.payload)
        declared = declared_period(report.get("file_name"))
        days = [d for r in report.get("rows", []) for d in (_day(r["fields"].get("Order Date")),
                                                           _day(r["fields"].get("Payment Date", ""))) if d]
        if declared:
            start, end = declared
            basis = "DECLARED"
        elif days:
            start, end, basis = min(days), max(days), "INFERRED"
        else:
            continue
        out.append(dict(id=a.id, file_name=report.get("file_name"), start=start, end=end, basis=basis,
                        rows=len(report.get("rows", [])),
                        codes={r["charge"] for r in report.get("rows", []) if r.get("charge")}))
    return out


def _protected(session: Session, txn) -> bool:
    e = session.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
    return bool(e and e.decision_source == "HUMAN" and e.transaction_reason_id)


def _amazon(session: Session, start: date, end: date) -> tuple[list[Gap], list[str]]:
    reports = amazon_reports(session)
    movements = [t for t in session.scalars(select(m.FinancialTransaction).where(
        m.FinancialTransaction.accounting_status == "CANONICAL",
        m.FinancialTransaction.duplicate_status.is_distinct_from("CONFIRMED_DUPLICATE"),
        m.FinancialTransaction.posting_date >= start, m.FinancialTransaction.posting_date <= end))
        if _AMAZON_TEXT.search(t.description_original or "")]
    if not movements:
        return [], []
    if not reports:
        return [], [f"{len(movements)} Amazon movement(s) in the work period and no Amazon order report loaded. "
                    "If they were paid on an Amazon Business account, upload its orders report: Bank links each "
                    "charge to its products and splits it by classification."]
    codes = set().union(*(r["codes"] for r in reports))
    paying = {t.payment_instrument_id for t in session.scalars(select(m.FinancialTransaction))
              if _AMAZON_TEXT.search(t.description_original or "")
              and set(_TOKEN.findall((t.description_original or "").upper())) & codes}
    labels = {i.id: _label(i) for i in session.scalars(select(m.PaymentInstrument))}
    uncovered = [t for t in movements if t.payment_instrument_id in paying and not _protected(session, t)
                 and not any(r["start"] <= (t.transaction_date or t.posting_date) <= r["end"] for r in reports)]
    notes = [f"Amazon report {r['file_name']}: {_fmt(r['start'])} – {_fmt(r['end'])}"
             + (" (period stated by the export)" if r["basis"] == "DECLARED"
                else " (period read from its first and last order: the file does not state it)") for r in reports]
    if not uncovered:
        return [], notes
    days = sorted(t.transaction_date or t.posting_date for t in uncovered)
    paid_on = sorted({labels.get(t.payment_instrument_id, "—") for t in uncovered})
    gap = Gap(GAP_AMAZON_REPORT, None, "Amazon Business", days[0], days[-1],
              f"{len(uncovered)} Amazon movement(s) on {', '.join(paid_on)} — Sources already paid through Amazon "
              "Business orders — fall outside every loaded report: without it Bank cannot link them to their "
              "products.")
    return [gap], notes


