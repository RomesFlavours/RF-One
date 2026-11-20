"""RF-One Web — Upload and Reconcile, the daily Bank path (BANK_UPLOAD_AND_RECONCILE_001, 2026-11-02).

    UPLOAD FILES -> CHECK COMPLETENESS -> RECONCILE AUTOMATICALLY -> COMPLETE BY HAND -> EXPORT QBO

One page, `/bank/work`, and no month, period or session to choose:

* UPLOAD — any number of bank, card and Amazon files, in any order, at any time. Each file is recognised
  from its content (`import_session.identify_file`), given the one Source its name identifies
  (`import_session.matching_sources`), and integrated at once without duplicating movements
  (`intake.integrate_bank_file`); an Amazon orders report is saved as purchase evidence (`bank_amazon.ingest`).
  A file Bank cannot settle alone (no or several Sources, an incomplete Source, unreadable rows, rows already
  stored on another Source, an unknown layout) waits on the page with one concrete question. Every file
  received is recorded as an INTAKE_FILE artifact, so the list survives and the person can come back later.
* CHECK — after every upload or answer the completeness is recomputed (`intake.completeness`). Blocking
  items: files waiting for an answer and coverage gaps. Uncertainties are shown and never block.
* RECONCILE — "Start automatic reconciliation" is enabled only when nothing blocks; it is never started by an
  upload. RFBank (2026-11-17): it reads saved data and rules only — the Amazon WHY proposals are made at
  acquisition, right after an upload (`bank_amazon.start_acquisition_analysis`, kept answers reused, only new or
  changed products sent, with the recorded consent), never by the run. It runs the single engine (`bank_guided_reconciliation`: matching,
  WHO rules, text recognition, WHY by WHO UNIQUE/MULTIPLE and Source, Amazon links and splits, WHAT from WHY).
  The engine writes its results and matches, never a classification. A failed run can simply be started again:
  nothing it did is applied twice.
* COMPLETE — the latest engine run is read back as: reconciled automatically, to confirm, still to reconcile,
  already confirmed by a person. A person makes the automatic results effective with ONE confirmation, after
  seeing what it will write; the other cases are worked in Guided Reconciliation / Split, linked per group.
* EXPORT — the QuickBooks Online preview (`qbo_export.preview`) of the confirmed movements of the work period:
  ready, blocked and why. Nothing is sent to QuickBooks: no QBO connection exists.

Registered from `bank_routes.register_bank_routes`.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import import_session, intake, parsers, qbo_books, qbo_export, recognition
from rfone_data_store.bank_reconciliation.rule_application_safety import lock_writes

from rfone_data_store.bank_reconciliation import adp_reports, paypal_reports

import bank_amazon
import bank_zelle
import bank_zelle_links
import bank_guided_reconciliation
import bank_work_research

INTAKE, WORK_RUN = "INTAKE_FILE", "WORK_RUN"
# File states. Blocking: the person must answer before the automatic reconciliation.
INTEGRATED, ALREADY_LOADED, AMAZON_LOADED, KEPT_ASIDE, REMOVED = (
    "INTEGRATED", "ALREADY_LOADED", "AMAZON_LOADED", "KEPT_ASIDE", "REMOVED")
NEEDS_SOURCE, SOURCE_INCOMPLETE, UNREADABLE_ROWS, CHECK_SOURCE, NOT_RECOGNIZED, FAILED = (
    "NEEDS_SOURCE", "SOURCE_INCOMPLETE", "UNREADABLE_ROWS", "CHECK_SOURCE", "NOT_RECOGNIZED", "FAILED")
BLOCKING = intake.BLOCKING_FILE_STATES   # the gate reads the same states
# Zelle documents are support data: they never block the reconciliation (Product Owner, 2026-11-17).
ZELLE, NEEDS_KIND = "ZELLE", "NEEDS_KIND"
STATE_LABELS = {
    NEEDS_KIND: 'Che documento è?', ZELLE: 'Documento Zelle',
    'PAYPAL_LOADED': 'Report PayPal salvato',
    'ADP_LOADED': 'Report ADP salvato', 'REPORT_INVALID': 'Report da ricaricare',
    INTEGRATED: 'Integrato', ALREADY_LOADED: 'Già caricato', AMAZON_LOADED: 'Report Amazon salvato',
    KEPT_ASIDE: 'Conservato, non utilizzato', NEEDS_SOURCE: 'Quale conto o carta?', SOURCE_INCOMPLETE: 'Dati del conto o carta incompleti',
    UNREADABLE_ROWS: 'Righe non leggibili', CHECK_SOURCE: 'Verifica il conto o carta', NOT_RECOGNIZED: 'Non riconosciuto',
    FAILED: 'Importazione non riuscita',
}
MAX_FILE_BYTES = 25 * 1024 * 1024

# Engine exception codes in plain words (the engine's own message is shown as the detail).
CASE_LABELS = {
    "WHO_SOURCE_CLASSIFICATION_MISSING": 'WHO riconosciuto, WHY non impostato per questo conto o carta',
    "WHY_RULE_MISSING": 'WHO multiplo: nessuna regola WHY risolve questo movimento',
    "WHY_DOCUMENT_MISSING": 'Manca il documento necessario per determinare il WHY',
    "WHY_RULES_CONFLICT": 'Regole WHY in conflitto',
    "WHY_SPLIT_INCOMPLETE": 'Ripartizione incompleta',
    "WHO_UNKNOWN": 'WHO non riconosciuto',
    "WHO_AMBIGUOUS": 'Più WHO possibili',
    "PERSONAL_SOURCE_BUSINESS_WHAT": 'Conto o carta personale con WHAT aziendale',
    "RELATIONSHIP_TO_DECIDE": 'Rapporto economico tra titolari da definire',
    "CARD_PAYMENT_UNMATCHED": 'Pagamento carta senza il corrispondente accredito sulla carta',
    "CARD_PAYMENT_AMBIGUOUS": 'Pagamento carta con più contropartite possibili',
    "PROVISIONAL_WHY": 'WHY provvisorio: natura da determinare',
    "CATEGORY_MISSING": 'WHY senza categoria contabile',
    "INCOMPLETE": 'Classificazione incompleta',
}

_runs_alive: dict[int, threading.Thread] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# The files received
# ---------------------------------------------------------------------------

def _files(db) -> list:
    return list(db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == INTAKE)
                           .order_by(m.BankFlowArtifact.id.desc())))


def _save(rec, data) -> None:
    rec.payload = json.dumps(data, ensure_ascii=False, default=str)


def _content(data) -> bytes:
    return base64.b64decode(data["content_b64"]) if data.get("content_b64") else b""


def _process_bank(db, data: dict, content: bytes, account_id: int, *, leave_out_unreadable=False,
                  source_confirmed=False) -> None:
    """Integrate a bank file whose Source is known, or set the question that stops it. Never commits."""
    source = db.get(m.PaymentInstrument, data["source_id"])
    if source is None or not source.is_payment_source:
        data.update(state=NEEDS_SOURCE, question="Choose the bank account or card this file belongs to.")
        return
    missing = import_session.source_missing_fields(db, source)
    if missing:
        data.update(state=SOURCE_INCOMPLETE, question=f"Complete the Source “{source.display_name}”: "
                    + ", ".join(missing) + ". Then check the file again.")
        return
    plan = intake.plan_bank_file(db, file_name=data["file_name"], content=content, source_id=source.id)
    data.update(source=source.display_name, rows=plan.rows, period_start=plan.period_start,
                period_end=plan.period_end, plan=plan.as_dict())
    if plan.already_imported_batch is not None:
        data.update(state=ALREADY_LOADED, batch_id=plan.already_imported_batch, new_rows=0,
                    already_stored=plan.rows, question=None, content_b64=None)
        return
    if plan.unreadable and not leave_out_unreadable:
        data.update(state=UNREADABLE_ROWS, question=f"{len(plan.unreadable)} row(s) cannot be read. Upload a "
                    "corrected file, or confirm that these rows stay out.")
        return
    if plan.suspected_source and not source_confirmed:
        data.update(state=CHECK_SOURCE, question=(
            f"{plan.other_source[plan.suspected_source]} of its {plan.rows} rows are already stored on "
            f"{plan.suspected_source}: is this really the file of {source.display_name}?"))
        return
    with db.begin_nested():
        result = intake.integrate_bank_file(db, file_name=data["file_name"], content=content, source_id=source.id,
                                            account_id=account_id, plan=plan,
                                            leave_out_unreadable=leave_out_unreadable)
    data.update(state=INTEGRATED, batch_id=result.batch.id, new_rows=plan.new_rows,
                already_stored=plan.already_stored, left_out_unreadable=len(plan.unreadable),
                question=None, content_b64=None)


def receive(db, file_name: str, content: bytes, account_id: int, *, upload_id: str | None = None) -> dict:
    """Record one uploaded file and settle it as far as Bank can alone. Never commits."""
    data = dict(file_name=file_name, received_at=_now(), account_id=account_id, size=len(content),
                content_b64=base64.b64encode(content).decode("ascii"), state=None, question=None,
                upload_id=upload_id or _upload_token())
    rec = m.BankFlowArtifact(kind=INTAKE, account_id=account_id, payload="{}")
    db.add(rec)
    db.flush()
    try:
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("The file is larger than 25 MB.")
        if content.startswith(b'%PDF-'):
            kind = bank_zelle.identify_pdf(file_name, content)
            if kind == "ZELLE":
                _receive_zelle(db, data, content, account_id)
                _save(rec, data)
                return data
            if kind is None:
                data.update(kind="PDF", kind_label="PDF da identificare", state=NEEDS_KIND,
                            question="Bank non riconosce con certezza questo PDF: indica se è un documento Zelle o uno statement PayPal.")
                _save(rec, data)
                return data
            saved, created = paypal_reports.ingest(db, file_name, content, account_id)
            data.update(kind=paypal_reports.KIND, kind_label='Statement PayPal (PDF)',
                state='PAYPAL_LOADED' if created else ALREADY_LOADED, rows=len(saved['events']),
                new_rows=saved['new_transactions'], already_stored=saved['already_stored'],
                period_start=saved['days'][0], period_end=saved['days'][-1], content_b64=None)
            _save(rec, data)
            return data
        if file_name.casefold().endswith(".xlsx") or content.startswith(b"PK\x03\x04"):
            data.update(kind=adp_reports.KIND, kind_label="Report Excel", content_b64=None)
            try:
                saved, created = adp_reports.ingest(db, file_name, content, account_id)
                data.update(kind_label="ADP Payroll Summary", state="ADP_LOADED" if created else ALREADY_LOADED,
                            rows=len(saved["payments"]), period_start=saved["days"][0], period_end=saved["days"][-1])
            except ValueError as exc:
                data.update(state="REPORT_INVALID", question=str(exc))
            _save(rec, data)
            return data
        identity = import_session.identify_file(file_name, content)
        data.update(kind=identity.kind, kind_label=import_session.KIND_LABELS.get(identity.kind),
                    format=identity.detected_format, note=identity.note)
        if identity.kind == import_session.KIND_AMAZON:
            with db.begin_nested():
                saved = bank_amazon.ingest(db, [dict(file_name=file_name, content=content)], account_id)[0]
            days = [d for r in saved["rows"] for d in (intake._day(r["fields"].get("Order Date")),) if d]
            data.update(state=AMAZON_LOADED if saved["created"] else ALREADY_LOADED, report_id=saved["id"],
                        rows=len(saved["rows"]), period_start=min(days) if days else None,
                        period_end=max(days) if days else None, content_b64=None)
        elif identity.kind == import_session.KIND_PAYPAL:
            saved, created = paypal_reports.ingest(db, file_name, content, account_id)
            data.update(state='PAYPAL_LOADED' if created else ALREADY_LOADED,
                rows=len(saved['events']), new_rows=saved['new_transactions'],
                already_stored=saved['already_stored'], period_start=saved['days'][0],
                period_end=saved['days'][-1], question=None, content_b64=None)
        elif identity.kind == import_session.KIND_UNRECOGNIZED:
            data.update(state=NOT_RECOGNIZED, question="Bank does not know this layout. Remove the file, or "
                        "upload the CSV exported by the bank or card issuer.")
        else:
            found = import_session.matching_sources(db, identity)
            data.update(digits=identity.account_digits, candidates=[s.id for s in found])
            if len(found) == 1:
                data["source_id"] = found[0].id
                _process_bank(db, data, content, account_id)
            else:
                data.update(state=NEEDS_SOURCE, question=(
                    'Il nome del file corrisponde a più conti o carte: scegli quello corretto.' if found else
                    "The file name does not identify its account: choose the bank account or card it belongs to."))
    except (ValueError, parsers.UnrecognizedFormatError) as exc:
        data.update(state="REPORT_INVALID" if data.get("kind") == import_session.KIND_AMAZON else FAILED,
                    question=str(exc))
    _save(rec, data)
    return data


def _receive_zelle(db, data: dict, content: bytes, account_id: int) -> None:
    """Store a Zelle document once; only a new file is read by the AI (started after the commit). Never commits."""
    saved, created = bank_zelle.register(db, data["file_name"], content, account_id)
    data.update(kind=bank_zelle.KIND, kind_label="Pagamenti Zelle (PDF)", zelle_file_id=saved["id"],
                state=ZELLE if created else ALREADY_LOADED, question=None, content_b64=None,
                note=None if created else "File già presente: nessuna nuova lettura AI.")


def _start_new_zelle(SessionFactory, outcome: list[dict]) -> None:
    for data in outcome:
        if data.get("kind") == bank_zelle.KIND and data.get("state") == ZELLE:
            bank_zelle.start_reading(SessionFactory, data["zelle_file_id"])


def _link_zelle(SessionFactory) -> None:
    """After new bank movements: link the confirmed Zelle payments that were still waiting for their movement
    (Product Owner, 2026-11-20). Evidence only, never a classification."""
    with SessionFactory() as db:
        if not bank_zelle.exists(db):
            return
        lock_writes(db)
        bank_zelle_links.match(db)
        db.commit()


def _support_acquisition(app, SessionFactory, account_id: int) -> None:
    """After an upload: Amazon WHY proposals only for products without a kept answer (new movements can link
    saved orders), with the recorded consent. Acquisition, not reconciliation."""
    with SessionFactory() as db:
        if not intake.amazon_reports(db):
            return
        lock_writes(db)
        bank_amazon.queue(db, account_id)
        db.commit()
    bank_amazon.start_acquisition_analysis(app, SessionFactory)


def sync_support_tables(SessionFactory) -> None:
    """Rule-readable tables rebuilt from the support data already saved (no upload, no AI)."""
    with SessionFactory() as db:
        if intake.amazon_reports(db):
            bank_amazon.sync_items(db)
        if paypal_reports.reports(db):
            paypal_reports.sync(db)
        if bank_zelle.exists(db):
            bank_zelle.ensure(db)
            bank_zelle_links.match(db)
        db.commit()


def _upload_token() -> str:
    """BANK_WHO_WHY_UPLOAD_CHECK_001: one token per upload (or per answer that integrates a waiting file); the
    newest token is the upload whose new movements the WHO -> WHY check looks at."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def upload_scope(db) -> dict:
    """The latest upload: its files and the ids of the NEW movements it integrated (a file already loaded, or rows
    already stored, add none — a reload never asks the same question twice)."""
    files = [json.loads(rec.payload) for rec in _files(db)]
    tokens = [f["upload_id"] for f in files if f.get("upload_id")]
    if not tokens:
        return dict(token=None, files=[], movement_ids=[])
    token = max(tokens)
    mine = [f for f in files if f.get("upload_id") == token]
    batches = [f["batch_id"] for f in mine if f.get("state") == INTEGRATED and f.get("batch_id") and f.get("new_rows")]
    ids = list(db.scalars(select(m.FinancialTransaction.id).where(m.FinancialTransaction.import_batch_id.in_(batches)))) \
        if batches else []
    return dict(token=token, files=[f["file_name"] for f in mine], movement_ids=ids)


def file_view(db, rec) -> dict:
    data = json.loads(rec.payload)
    data.pop("content_b64", None)
    data["id"] = rec.id
    data["state_label"] = STATE_LABELS.get(data.get("state"), data.get("state") or "—")
    data["blocking"] = data.get("state") in BLOCKING
    if data.get("kind") == bank_zelle.KIND and data.get("state") == ZELLE:
        live = bank_zelle.get(db, data["zelle_file_id"])
        if live:
            data["state_label"] = bank_zelle.view(db, live)["status_label"]
            data["zelle_status"] = live["status"]
            data["rows"] = len(live["extracted"]) if live.get("extracted") is not None else None
    return data


# ---------------------------------------------------------------------------
# The automatic run
# ---------------------------------------------------------------------------

def _latest_run_record(db):
    return db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == WORK_RUN)
                      .order_by(m.BankFlowArtifact.id.desc())).first()


def run_view(db) -> dict | None:
    rec = _latest_run_record(db)
    if rec is None:
        return None
    data = dict(json.loads(rec.payload), id=rec.id)
    if data.get("finished_at"):
        data["finished_dt"] = datetime.fromisoformat(data["finished_at"])
    if data.get("status") in ("QUEUED", "RUNNING") and rec.id not in _runs_alive:
        # Its thread lives in this process only: without it the server was restarted during the run.
        data.update(status="INTERRUPTED", error="The run was interrupted (the server stopped). Start it again: "
                    "nothing it did is applied twice, and the internet answers already received are reused.")
    return data


def _engine_tables(db) -> bool:
    from sqlalchemy import inspect
    return inspect(db.connection()).has_table("bank_engine_runs")


def latest_engine_run(db) -> dict | None:
    if not _engine_tables(db):
        return None
    row = db.execute(text("select id, created_at, label, summary_json from bank_engine_runs order by id desc limit 1")).first()
    if row is None:
        return None
    return dict(id=row[0], created_at=row[1], label=row[2], summary=json.loads(row[3] or "{}"))


def engine_results(db, run_id: int) -> list[dict]:
    return [json.loads(p) for (p,) in db.execute(text(
        "select payload_json from bank_engine_results where run_id = :r"), dict(r=run_id))]


def report_pending(db):
    """Only document-dependent movements still open in the latest reconciliation."""
    pending = {"ADP": [], "Amazon": []}
    latest = latest_engine_run(db)
    if latest:
        decided = _decided_ids(db)
        for row in engine_results(db, latest["id"]):
            if row.get("protected") or row["txn_id"] in decided:
                continue
            for exc in row.get("exceptions", []):
                if exc.get("code") != "WHY_DOCUMENT_MISSING":
                    continue
                reason = json.dumps(exc).lower()
                for key, tokens in (("ADP", ("adp", "payroll")), ("Amazon", ("amazon",))):
                    if any(t in reason for t in tokens) and row["date"] not in pending[key]:
                        pending[key].append(row["date"])
    return pending


def _run_worker(app, SessionFactory, rec_id: int, account_id: int) -> None:
    def update(**fields):
        # A page read while the run writes can hold SQLite for a moment: retry, each time in a new session.
        for attempt in range(10):
            try:
                with SessionFactory() as db:
                    rec = db.get(m.BankFlowArtifact, rec_id)
                    data = json.loads(rec.payload)
                    data.update(fields)
                    _save(rec, data)
                    db.commit()
                return
            except OperationalError:
                if attempt == 9:
                    raise
                time.sleep(1 + attempt)

    try:
        # RFBank (2026-11-17): no AI here. The Amazon WHY proposals already obtained at acquisition are read by the
        # engine (split_allocation.item_whys_from_runs); products without one stay to be clarified.
        update(status="RUNNING", started_at=_now(), step="Engine")
        warnings = []
        update(step="Engine: transfers and card payments, WHO rules, WHO names and aliases, WHY, Amazon links and "
                    "splits, WHAT")
        run_id, summary = bank_guided_reconciliation.recalculate_classification()
        update(engine_run_id=run_id, step='Ricerca internet')
        with SessionFactory() as db:
            check = intake.completeness(db)
        research = bank_work_research.run_stage(
            app, SessionFactory, engine_run_id=run_id,
            window=(check.window_start.isoformat(), check.window_end.isoformat()), progress=update)
        if not research["authorized"]:
            warnings.append("Internet research did not run: it waits for your authorization (see below).")
        elif research["counts"].get(bank_work_research.PROVIDER_ERROR):
            warnings.append(f"Internet research: {research['counts'][bank_work_research.PROVIDER_ERROR]} movement(s) "
                            f"not researched because ChatGPT did not answer ({research.get('error') or 'error'}). "
                            "Start again to retry them; the answers already received are reused.")
        update(status="DONE", finished_at=_now(), step=None, warnings=warnings, research=dict(
            requests=research["requests"], distinct=research["distinct"], reused=research["reused"],
            counts=research["counts"]))
    except Exception as exc:  # noqa: BLE001 — reported on the page; a new run can be started
        update(status="ERROR", finished_at=_now(), error=str(exc)[:1000])
    finally:
        _runs_alive.pop(rec_id, None)


# ---------------------------------------------------------------------------
# Results: one state per movement, two quadratures
# ---------------------------------------------------------------------------

# Final state of a movement of the work period. Exactly one each; the five add up to the total.
DECIDED, MATCHED, PROPOSAL, TO_CONFIRM, MANUAL = "decided", "matched", "proposal", "to_confirm", "manual"
STATE_TITLES = {
    DECIDED: 'Deciso — registrato da una persona o confermato da te',
    MATCHED: 'Applicato automaticamente',
    PROPOSAL: 'Risolto automaticamente — proposta completa, registrata alla conferma',
    TO_CONFIRM: 'Da confermare — proposta della ricerca internet',
    MANUAL: 'Da riconciliare a mano',
}
# Where the WHO comes from. Exactly one each; they add up to the total.
WHO_ORIGINS = (("person", 'Persona (decisione registrata in Bank)'), ("rule", 'Regola WHO'),
               ("text", 'Nome o alias WHO nella descrizione'),
               ("context", 'WHO non previsto (giroconto / pagamento carta)'),
               ("internet", 'Ricerca internet — WHO identificato'), ("generic", 'Ricerca internet — WHO generico'),
               ("none", 'WHO non identificato'))
CASE_LABELS.update({
    "PROVIDER_ERROR": 'Ricerca internet non riuscita (ChatGPT non ha risposto): riavvia per riprovare',
    "NOT_AUTHORIZED": 'Ricerca internet non autorizzata',
    "WHO_UNRESOLVED": 'Ricerca internet: WHO e natura del movimento non determinati',
    "WHY_NOT_SUPPORTED": 'WHO identificato, WHY non supportato dalle evidenze',
    "NO_CATALOG_WHO": 'Classificato senza WHO a catalogo: scegli il WHO',
})


def _in_window(r: dict, start: date | None, end: date | None) -> bool:
    if start is None:
        return False
    day = (r.get("date") or "")[:10]
    return bool(day) and start.isoformat() <= day <= end.isoformat()


def _decided_ids(db) -> set[int]:
    return {t for (t,) in db.execute(select(m.FinancialTransaction.id).join(
        m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id).where(
        m.BankTransactionExplanation.decision_source == "HUMAN",
        m.BankTransactionExplanation.transaction_reason_id.is_not(None)))}


def classify(r: dict, research: dict | None, decided: bool) -> tuple[str, str, str, dict | None]:
    """(final state, open reason code, WHO origin, proposal) of one movement of the work period."""
    split_ok = bool((r.get("split") or {}).get("complete") and (r.get("split") or {}).get("origin") != "BANK")
    if decided or r.get("protected"):
        return DECIDED, "", "person", None
    method = r.get("who_method")
    origin = {"RULE": "rule", "NAME/ALIAS": "text", "CONTEXT": "context"}.get(method, "none")
    if r.get("why_method") == "Causale bancaria":
        if r["status"] == "RECONCILED" and not r.get("anomalies"):
            return MATCHED, "", "context", None
        return MANUAL, (r["exceptions"] or [{"code":"BANK_NARRATIVE"}])[0]["code"], "context", None
    if r["status"] == "RECONCILED":
        if r.get("why_method") in ("Toast restaurant", "Web restaurant") and not r.get("anomalies"):
            return MATCHED, "", "internet", None
        if (r.get("match") or {}).get("state") == "MATCHED" and not r.get("who_id"):
            return MATCHED, "", "context", None
        if r.get("who_id") and (r.get("why_id") or split_ok):
            return PROPOSAL, "", origin, dict(source="ENGINE", who_id=r["who_id"], who=r.get("who_name"),
                                              why_id=r.get("why_id"), why=r.get("why"), split=r.get("split") if split_ok else None)
        return MANUAL, "NO_CATALOG_WHO", origin, None
    code = r["exceptions"][0]["code"] if r.get("exceptions") else "INCOMPLETE"
    if r.get("method_conflicts"):
        return MANUAL, code, origin, None
    if any(e.get("code") == "WHY_DOCUMENT_MISSING" for e in r.get("exceptions", [])):
        return MANUAL, "WHY_DOCUMENT_MISSING", origin, None
    if research:
        outcome = research.get("outcome")
        if research.get("toast_applied"):
            return MATCHED, "", "internet", None
        if outcome == "WHO_IDENTIFIED":
            if origin == "none":
                origin = "internet"
            if research.get("why_id"):
                return TO_CONFIRM, "RESEARCH_WHO" if origin == "internet" else "RESEARCH_WHY", origin, dict(
                    source="RESEARCH", who_id=research.get("who_id"), who=research.get("who"),
                    why_id=research["why_id"], why=research.get("why"), basis=research.get("why_basis"),
                    sources=research.get("sources") or [], reasoning=research.get("reasoning"))
            return MANUAL, research.get("why_open_reason") or "WHY_NOT_SUPPORTED", origin, None
        if outcome == "GENERIC_WHO":
            return TO_CONFIRM, "RESEARCH_GENERIC", "generic", dict(
                source="RESEARCH", who_id=None, who=research.get("who"), why_id=research.get("why_id"),
                why=research.get("why"), basis=research.get("why_basis"), sources=research.get("sources") or [],
                reasoning=research.get("reasoning"), generic=True)
        if outcome == "UNRESOLVED":
            return MANUAL, "WHO_UNRESOLVED", origin, None
        if outcome in ("PROVIDER_ERROR", "NOT_AUTHORIZED"):
            return MANUAL, outcome, origin, None
    return MANUAL, code, origin, None


RESEARCH_TITLES = {"RESEARCH_WHO": "WHO identified on the internet, WHY from the evidence",
                   "RESEARCH_WHY": "WHO already known, WHY from the internet evidence",
                   "RESEARCH_GENERIC": "Generic WHO (nature established, merchant not verified) — choose the WHO"}


def results_view(db, completeness) -> dict | None:
    engine_run = latest_engine_run(db)
    if engine_run is None:
        return None
    research = bank_work_research.latest_results(db, engine_run["id"])
    by_txn = (research or {}).get("results", {})
    decided = _decided_ids(db)
    rows = []
    earlier_open = 0
    for r in engine_results(db, engine_run["id"]):
        if not _in_window(r, completeness.window_start, completeness.window_end):
            day = (r.get("date") or "")[:10]
            if completeness.window_start and day and day < completeness.window_start.isoformat() \
                    and r["status"] != "RECONCILED" and not r.get("protected") and r["txn_id"] not in decided:
                earlier_open += 1
            continue
        state, reason, origin, proposal = classify(r, by_txn.get(str(r["txn_id"])), r["txn_id"] in decided)
        rows.append(dict(r=r, state=state, reason=reason, origin=origin, proposal=proposal))
    total = len(rows)
    states = Counter(x["state"] for x in rows)
    origins = Counter(x["origin"] for x in rows)
    groups = defaultdict(list)
    for x in rows:
        if x["state"] in (TO_CONFIRM, MANUAL):
            who = (x["proposal"] or {}).get("who") or x["r"].get("group_key") or x["r"].get("who_name") or "—"
            groups[(x["state"], x["reason"], who)].append(x)
    case_groups = []
    for (state, reason, who), members in groups.items():
        first = members[0]["r"]
        confirmable = [x for x in members if x["proposal"] and x["proposal"].get("why_id")
                       and not x["proposal"].get("generic")]
        case_groups.append(dict(
            key=f"{state}|{reason}|{who}", state=state, reason=reason, who=who, count=len(members),
            label=RESEARCH_TITLES.get(reason) or CASE_LABELS.get(reason, reason.replace("_", " ").capitalize()),
            detail=(first["exceptions"][0].get("message") if first.get("exceptions") else ""),
            amazon=any(re.search(r"AMAZON|AMZN", x["r"].get("description") or "", re.I) for x in members),
            confirmable=len(confirmable), proposal=members[0]["proposal"],
            cases=sorted(members, key=lambda x: x["r"].get("date") or "", reverse=True)[:5]))
    case_groups.sort(key=lambda g: (g["state"] != TO_CONFIRM, -g["count"]))
    proposals = [x for x in rows if x["state"] == PROPOSAL]
    return dict(run=engine_run, research=research, total=total, states=states, origins=origins,
                quadrature_final=sum(states.values()) == total, quadrature_who=sum(origins.values()) == total,
                earlier_open=earlier_open, groups=case_groups, confirmable=len(proposals),
                confirm_preview=Counter((x["proposal"].get("why") or "Split") for x in proposals).most_common(12))


def _proposals(db, completeness, engine_run_id: int, *, state: str, group_key: str | None = None) -> list[dict]:
    """The proposals the person confirms, recomputed on the server (the page never sends them)."""
    research = bank_work_research.latest_results(db, engine_run_id)
    by_txn = (research or {}).get("results", {})
    decided = _decided_ids(db)
    out = []
    for r in engine_results(db, engine_run_id):
        if not _in_window(r, completeness.window_start, completeness.window_end):
            continue
        st, reason, _origin, proposal = classify(r, by_txn.get(str(r["txn_id"])), r["txn_id"] in decided)
        if st != state or not proposal or proposal.get("generic") or not (proposal.get("why_id") or proposal.get("split")):
            continue
        if group_key is not None:
            who = proposal.get("who") or r.get("group_key") or r.get("who_name") or "—"
            if f"{st}|{reason}|{who}" != group_key:
                continue
        out.append(dict(proposal, txn_id=r["txn_id"]))
    return out


def confirm_proposals(db, proposals: list[dict], *, account_id: int, note: str) -> dict:
    """The person's confirmation: each proposal becomes a HUMAN decision through Bank's own services (WHO + WHY
    with WHAT derived, one complete allocation to the existing WHOM; or a complete Amazon split). A WHO the
    research identified that is not yet in the catalog is created, as Review's "+ New WHO" does. A movement a
    person decided in the meantime is skipped, never overwritten. The WHO -> WHY association is not recorded:
    confirming decides this movement only. The caller commits."""
    from rfone_data_store.bank_reconciliation import economic_allocation, manual_reconciliation, split_allocation
    written, skipped = 0, []
    for p in proposals:
        txn = db.get(m.FinancialTransaction, p["txn_id"])
        current = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn and txn.explanation_id else None
        if txn is None or (current is not None and current.decision_source == "HUMAN" and current.transaction_reason_id):
            skipped.append(dict(id=p["txn_id"], reason="decided by a person in the meantime"))
            continue
        try:
            with db.begin_nested():
                if p.get("split"):
                    lines = [dict(amount_minor=ln["amount_minor"], why_id=ln["why_id"],
                                  description=ln.get("description") or "", items=ln.get("items") or [])
                             for ln in p["split"]["lines"]]
                    split_allocation.confirm_split(db, txn.id, lines, account_id=account_id,
                                                   evidence_kind=split_allocation.EVIDENCE_AMAZON,
                                                   evidence_reference=", ".join((p["split"].get("link") or {}).get("codes") or []) or None)
                else:
                    who_id = p.get("who_id")
                    if not who_id:
                        who_id = manual_reconciliation.create_who(db, name=p["who"]).occurrence.id
                    whom = split_allocation.whom_for(db, txn)
                    if whom is None:
                        raise ValueError("WHOM unknown: configure the owner of the Source at the movement date.")
                    if len(db.scalars(select(m.BankTransactionAllocation).where(
                            m.BankTransactionAllocation.financial_transaction_id == txn.id)).all()) > 1:
                        raise ValueError("the movement is split: confirm it on Split")
                    explanation = recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                        transaction_id=txn.id, occurrence_id=who_id, confirmed_by_account_id=account_id,
                        transaction_reason_id=p["why_id"], notes=note, record_association=False))
                    economic_allocation.set_allocations(db, financial_transaction_id=txn.id, specs=[
                        economic_allocation.AllocationSpec(
                            amount_minor=txn.amount_minor, reporting_entity_id=whom,
                            transaction_reason_id=explanation.transaction_reason_id,
                            accounting_classification_id=explanation.accounting_classification_id,
                            status=economic_allocation.COMPLETE, decision_source="HUMAN",
                            decided_by_account_id=account_id, notes=note)])
                    txn.review_status = "REVIEWED"
            written += 1
        except ValueError as exc:
            skipped.append(dict(id=p["txn_id"], reason=str(exc)[:300]))
    return dict(written=written, skipped=skipped)


# ---------------------------------------------------------------------------
# QuickBooks Online scope
# ---------------------------------------------------------------------------

def qbo_scope(db, check) -> list[int]:
    """The movements of the work period that QBO may receive: canonical, not a confirmed duplicate."""
    if check.window_start is None:
        return []
    return [t for (t,) in db.execute(select(m.FinancialTransaction.id).where(
        m.FinancialTransaction.posting_date >= check.window_start, m.FinancialTransaction.posting_date <= check.window_end,
        m.FinancialTransaction.accounting_status == "CANONICAL",
        m.FinancialTransaction.duplicate_status.is_distinct_from("CONFIRMED_DUPLICATE")))]


def qbo_view(db, check) -> dict:
    plan = qbo_books.plan(db, qbo_scope(db, check))
    reasons = Counter(b["label"] for i in plan["items"] if not i["exported"] for b in i["blockers"])
    companies = defaultdict(lambda: dict(ready=0, blocked=0, exported=0))
    for i in plan["items"]:
        c = companies[(i["owner_id"], i["owner"] or "Owner not configured")]
        c["exported" if i["exported"] else "ready" if i["ready"] else "blocked"] += 1
    return dict(plan=plan, reasons=reasons.most_common(),
                companies=[dict(owner_id=k[0], owner=k[1], **v) for k, v in sorted(companies.items(), key=lambda kv: kv[0][1])])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register(app, *, gate, SessionFactory, current_account, require_csrf, instruments):
    from bank_ui_it import bank_ui_it
    app.jinja_env.filters["bank_ui_it"] = bank_ui_it

    def zelle_memo(transaction_id):
        """The memo of the Zelle payment linked to a movement (one read per page, shared by every row)."""
        from flask import g
        if "zelle_memos" not in g:
            try:
                with SessionFactory() as db:
                    g.zelle_memos = bank_zelle_links.memos(db)
            except OperationalError:
                g.zelle_memos = {}
        return g.zelle_memos.get(transaction_id)
    app.jinja_env.globals["zelle_memo"] = zelle_memo

    try:
        sync_support_tables(SessionFactory)
    except Exception as exc:  # noqa: BLE001 — the pages work; the tables are rebuilt at the next upload
        print(f"Support tables not rebuilt at start: {exc}", flush=True)

    def back(anchor=None, endpoint="bank_work"):
        return redirect(url_for(endpoint, _anchor=anchor))

    def page_state(db) -> dict:
        r = intake.readiness(db)
        files = [file_view(db, x) for x in _files(db)]
        files = [f for f in files if f.get("state") != REMOVED]
        run = run_view(db)
        running = bool(run and run.get("status") in ("QUEUED", "RUNNING"))
        return dict(check=r.check, files=files, waiting=[f for f in files if f["blocking"]], ready=r.ready, run=run,
                    running=running)

    def busy_page():
        # The engine is writing its results and the local SQLite file is busy for a moment: say so and retry,
        # rather than failing (the run itself is not affected).
        return app.response_class(
            '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="5">'
            '<title>Upload and Reconcile</title><p style="font-family:sans-serif;margin:2rem">'
            'The automatic reconciliation is writing its results. This page reloads in a few seconds.</p>',
            status=503, headers={"Retry-After": "5"})

    # BANK_LAYOUT_NAVIGATION_001 (Product Owner, 2026-11-05): Pannello is the new first tab and the Bank Home
    # (/bank). It only reads: the state of data and reconciliation, what is pending (each with its action, on the
    # page that already performs it), the P/L area (not implemented: no figure is shown) and, at the bottom, the
    # existing monthly export, whose check and download stay on its own route (bank_export). The period chosen
    # here is for consulting and exporting only; uploading files never asks for a month.
    @app.route("/bank")
    @app.route("/bank/panel")
    @gate
    def bank_panel():
        from sqlalchemy import func
        from rfone_data_store.bank_reconciliation import export as export_service
        today = date.today()
        year = request.args.get("year", type=int) or today.year
        month = request.args.get("month", type=int) or today.month
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            year, month = today.year, today.month
        try:
            with SessionFactory() as db:
                state = page_state(db)
                results = results_view(db, state["check"]) if not state["running"] else None
                movements = db.scalar(select(func.count()).select_from(m.FinancialTransaction)) or 0
                return render_template(
                    "bank_panel.html", **state, results=results, movements=movements,
                    sources=[i for i in instruments(db) if i.is_payment_source],
                    research_consent=bank_work_research.consent(app),
                    guided=bank_guided_reconciliation.available(), state_titles=STATE_TITLES,
                    year=year, month=month, owners=export_service.owner_choices(db))
        except OperationalError:
            return busy_page()

    # BANK-2026-11-04 (Product Owner, 2026-11-04): Upload and Reconcile was the Bank Home. Since
    # BANK_LAYOUT_NAVIGATION_001 (2026-11-05) it is the second tab, at /bank/work; /bank opens Pannello.
    @app.route("/bank/work")
    @gate
    def bank_work():
        try:
            with SessionFactory() as db:
                state = page_state(db)
                sources = [i for i in instruments(db) if i.is_payment_source]
                results = results_view(db, state["check"]) if not state["running"] else None
                qbo = qbo_view(db, state["check"]) if results else None
                scope = upload_scope(db)
                return render_template(
                    "bank_work.html", **state, sources=sources, results=results, qbo=qbo, upload_scope=scope,
                    adp_reports=adp_reports.reports(db), amazon_reports=intake.amazon_reports(db),
                      paypal_reports=paypal_reports.reports(db),
                    report_pending=report_pending(db),
                    periods={fp.batch_id: fp for sc in state["check"].sources for fp in sc.files},
                    guided=bank_guided_reconciliation.available(), answer_labels=intake.ANSWER_LABELS,
                    state_titles=STATE_TITLES, who_origins=WHO_ORIGINS,
                    research_consent=bank_work_research.consent(app), research_sent=bank_work_research.SENT,
                    research_not_sent=bank_work_research.NOT_SENT, zelle_files=bank_zelle.files(db),
                    zelle_links=bank_zelle_links.overview(db))
        except OperationalError:
            return busy_page()

    @app.route("/bank/work/who-why-check")
    @gate
    def bank_work_who_why_check():
        """BANK_WHO_WHY_UPLOAD_CHECK_001: the WHO -> WHY questions of the latest upload, read-only (no WHY, WHOM,
        rule or decision is written). `refresh=1` after a save re-evaluates them."""
        import bank_why_signals
        with SessionFactory() as db:
            scope = upload_scope(db)
        if not scope["movement_ids"]:
            return jsonify(ok=True, token=scope["token"], files=scope["files"], issues=[], scope=0, affected=0,
                           applicable=0, scope_recognised=0)
        try:
            data = bank_why_signals.upload_check(scope["movement_ids"], force=request.args.get("refresh") == "1")
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 503
        return jsonify(ok=True, token=scope["token"], files=scope["files"], **data)

    @app.route("/bank/how-it-works")
    @gate
    def bank_how_it_works():
        """The Bank guide (How Works standard): one section per page, opened by the page's How Works link."""
        return render_template("bank_how_it_works.html")

    @app.route("/bank/work/status")
    @gate
    def bank_work_status():
        with SessionFactory() as db:
            run = run_view(db)
            return jsonify(ok=True, run={k: v for k, v in (run or {}).items() if k != "finished_dt"} or None)

    @app.route("/bank/work/upload", methods=["POST"])
    @gate
    def bank_work_upload():
        require_csrf()
        uploaded = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploaded:
            flash('Scegli almeno un file.', "error")
            return back("upload")
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            outcome = []
            token = _upload_token()
            for f in uploaded:
                data = receive(db, f.filename, f.read(), account_id, upload_id=token)
                outcome.append(data)
            db.commit()
        _start_new_zelle(SessionFactory, outcome)
        _link_zelle(SessionFactory)
        _support_acquisition(app, SessionFactory, account_id)
        for data in outcome:
            label = STATE_LABELS.get(data["state"], data["state"])
            extra = (f": {data.get('new_rows', 0)} new movement(s), {data.get('already_stored', 0)} already present"
                     if data["state"] in (INTEGRATED, ALREADY_LOADED) and data.get("kind") == import_session.KIND_BANK else "")
            flash(f"{data['file_name']} — {label}{extra}.", "error" if data["state"] in BLOCKING else "info")
        return back("files")

    def _intake(db, file_id):
        rec = db.get(m.BankFlowArtifact, file_id)
        if rec is None or rec.kind != INTAKE:
            abort(404)
        return rec, json.loads(rec.payload)

    @app.route("/bank/work/files/<int:file_id>/<action>", methods=["POST"])
    @gate
    def bank_work_file_action(file_id: int, action: str):
        """The person's answer for one waiting file: its Source, leave out its unreadable rows, confirm its
        Source, check it again (after completing the Source), or remove it."""
        require_csrf()
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            rec, data = _intake(db, file_id)
            if data.get("state") not in BLOCKING:
                flash(f"{data['file_name']} needs nothing more.", "info")
                return back(f"file-{file_id}")
            content = _content(data)
            try:
                if action == "remove":
                    data.update(state=REMOVED, question=None, content_b64=None, removed_at=_now())
                elif not content:
                    raise ValueError("The file content is no longer available: upload it again.")
                elif action == "source":
                    source = db.get(m.PaymentInstrument, request.form.get("source_id", type=int) or 0)
                    if source is None or not source.is_payment_source:
                        raise ValueError("Choose a bank account or card.")
                    data["source_id"] = source.id
                    _process_bank(db, data, content, account_id)
                elif action == "leave-out":
                    _process_bank(db, data, content, account_id, leave_out_unreadable=True,
                                  source_confirmed=data.get("source_confirmed", False))
                elif action == "confirm-source":
                    data["source_confirmed"] = True
                    _process_bank(db, data, content, account_id, source_confirmed=True)
                elif action == "retry":
                    if data.get("kind") == import_session.KIND_BANK and data.get("source_id"):
                        _process_bank(db, data, content, account_id, source_confirmed=data.get("source_confirmed", False))
                    else:
                        raise ValueError("Upload the file again.")
                else:
                    abort(404)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return back(f"file-{file_id}")
            if data.get("state") == INTEGRATED:
                # the answer integrates the file into the latest upload, whose new movements are checked together
                data["upload_id"] = upload_scope(db)["token"] or _upload_token()
            rec = db.get(m.BankFlowArtifact, file_id)
            _save(rec, data)
            db.commit()
        if data.get("state") == INTEGRATED:
            _link_zelle(SessionFactory)
            _support_acquisition(app, SessionFactory, account_id)
        flash(f"{data['file_name']} — {STATE_LABELS.get(data['state'], data['state'])}.",
              "error" if data["state"] in BLOCKING else "info")
        return back(f"file-{file_id}")


    # Zelle documents (Product Owner, 2026-11-17): identify an uncertain PDF, follow the one AI reading, confirm
    # the acquisition of its rows into bank_zelle_payments, or repeat only a reading that failed.
    @app.route("/bank/work/files/<int:file_id>/identify", methods=["POST"])
    @gate
    def bank_work_file_identify(file_id: int):
        require_csrf()
        choice = request.form.get("kind")
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            rec, data = _intake(db, file_id)
            content = _content(data)
            if data.get("state") != NEEDS_KIND or not content or choice not in ("ZELLE", "PAYPAL"):
                flash("Il file non è in attesa di identificazione: caricalo di nuovo.", "error")
                return back(f"file-{file_id}")
            try:
                with db.begin_nested():
                    if choice == "ZELLE":
                        _receive_zelle(db, data, content, account_id)
                    else:
                        saved, created = paypal_reports.ingest(db, data["file_name"], content, account_id)
                        data.update(kind=paypal_reports.KIND, kind_label="Statement PayPal (PDF)",
                                    state="PAYPAL_LOADED" if created else ALREADY_LOADED, rows=len(saved["events"]),
                                    new_rows=saved["new_transactions"], already_stored=saved["already_stored"],
                                    period_start=saved["days"][0], period_end=saved["days"][-1], question=None,
                                    content_b64=None)
            except ValueError as exc:
                data.update(question=str(exc))
            _save(rec, data)
            db.commit()
        _start_new_zelle(SessionFactory, [data])
        flash(f"{data['file_name']} — {STATE_LABELS.get(data['state'], data['state'])}.",
              "error" if data["state"] == NEEDS_KIND else "info")
        return back("zelle" if data.get("kind") == bank_zelle.KIND else f"file-{file_id}")

    @app.route("/bank/work/zelle/status")
    @gate
    def bank_work_zelle_status():
        with SessionFactory() as db:
            return jsonify(ok=True, files=[dict(id=f["id"], status=f["status"]) for f in bank_zelle.files(db)])

    @app.route("/bank/work/zelle/<int:zelle_id>/confirm", methods=["POST"])
    @gate
    def bank_work_zelle_confirm(zelle_id: int):
        require_csrf()
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            try:
                done = bank_zelle.confirm(db, zelle_id, account_id)
                links = bank_zelle_links.match(db)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return back(f"zelle-{zelle_id}")
            db.commit()
        flash(f"Dati Zelle acquisiti: {done['acquired']} nuovi pagamenti, {done['duplicates']} già presenti non duplicati, "
              f"{done['updates']} aggiornamenti di stato, {done['ambiguous']} ambigui da chiarire, {done['invalid']} non "
              "acquisibili. Nessun movimento bancario è stato creato.", "info")
        flash(f"Abbinamento ai movimenti bancari: {links['linked']} pagamenti collegati, {links['proposed']} abbinamenti "
              f"ambigui da scegliere, {links['no_movement']} pagamenti senza movimento corrispondente (per ora).", "info")
        return back("zelle-links")

    @app.route("/bank/work/zelle/links/<int:link_id>/<choice>", methods=["POST"])
    @gate
    def bank_work_zelle_link_decide(link_id: int, choice: str):
        """The person resolves an ambiguous Zelle pair (collega / scarta)."""
        require_csrf()
        decision = {"confirm": "CONFIRMED", "reject": "REJECTED"}.get(choice)
        if decision is None:
            abort(404)
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            try:
                bank_zelle_links.decide(db, link_id, decision, account_id)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return back("zelle-links")
            db.commit()
        flash("Abbinamento collegato." if decision == "CONFIRMED" else "Abbinamento scartato.", "info")
        return back(f"zl-{link_id}")

    @app.route("/bank/work/zelle/<int:zelle_id>/retry", methods=["POST"])
    @gate
    def bank_work_zelle_retry(zelle_id: int):
        require_csrf()
        with SessionFactory() as db:
            lock_writes(db)
            restarted = bank_zelle.retry(db, zelle_id)
            db.commit()
        if restarted:
            bank_zelle.start_reading(SessionFactory, zelle_id)
        else:
            flash("Solo una lettura non riuscita può essere ripetuta.", "error")
        return back(f"zelle-{zelle_id}")

    @app.route("/bank/work/facts", methods=["POST"])
    @gate
    def bank_work_fact():
        """The person's factual answer to one coverage question (or a file's statement period), traced."""
        require_csrf()
        form = request.form
        try:
            start = date.fromisoformat(form.get("start") or "")
            end = date.fromisoformat(form.get("end") or form.get("start") or "")
        except ValueError:
            flash("Give the dates of the answer.", "error")
            return back("check")
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            try:
                intake.record_fact(db, source_id=form.get("source_id", type=int) or 0, fact=form.get("fact"),
                                   start=start, end=end, account_id=account_id, note=form.get("note"),
                                   batch_id=form.get("batch_id", type=int))
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return back("check")
            db.commit()
        flash("Answer recorded. The check was repeated.", "info")
        return back("files" if form.get("fact") == intake.FACT_STATEMENT_PERIOD else "check")

    @app.route("/bank/work/research/authorize", methods=["POST"])
    @gate
    def bank_work_research_authorize():
        """The person's explicit authorization of the internet research, with the exact list shown on the page."""
        require_csrf()
        if request.form.get("authorize") != "yes":
            flash("Tick the authorization first.", "error")
            return back("reconcile")
        with SessionFactory() as db:
            account = current_account(db)
            try:
                bank_work_research.record_consent(app, account_id=account.id, account_name=account.display_name)
            except ValueError as exc:
                flash(str(exc), "error")
                return back("reconcile")
        flash("Internet research authorized. It runs at the next automatic reconciliation.", "info")
        return back("reconcile")

    @app.route("/bank/work/reconcile", methods=["POST"])
    @gate
    def bank_work_reconcile():
        """Start the automatic reconciliation — only when the check is complete (the one gate, server side)."""
        require_csrf()
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            run = run_view(db)
            if run and run.get("status") in ("QUEUED", "RUNNING"):
                flash("The automatic reconciliation is already running.", "info")
                return back("reconcile")
            try:
                readiness = intake.require_ready(db, what="The automatic reconciliation")
            except intake.NotReady as exc:
                flash(str(exc), "error")
                return back("check")
            if not bank_guided_reconciliation.available():
                flash("The reconciliation engine is not available in this environment (start Bank with "
                      "“Avvia Bank”). Nothing was started.", "error")
                return back("reconcile")
            rec = m.BankFlowArtifact(kind=WORK_RUN, account_id=account_id, payload=json.dumps(dict(
                status="QUEUED", queued_at=_now(), requested_by=account_id,
                window=[readiness.check.window_start.isoformat(), readiness.check.window_end.isoformat()])))
            db.add(rec)
            db.commit()
            rec_id = rec.id
        thread = threading.Thread(target=_run_worker, args=(app, SessionFactory, rec_id, account_id),
                                  daemon=True, name=f"bank-work-run-{rec_id}")
        _runs_alive[rec_id] = thread
        thread.start()
        flash('Riconciliazione automatica avviata.', "info")
        return back("reconcile")

    @app.route("/bank/work/confirm", methods=["POST"])
    @gate
    def bank_work_confirm():
        """Make proposals effective: every complete automatic proposal, or the confirmable proposals of one group.
        The proposals are recomputed here from the latest run; the page only names what it showed."""
        require_csrf()
        if request.form.get("confirm") != "yes":
            flash("Tick the confirmation first.", "error")
            return back("results")
        scope = request.form.get("scope")
        with SessionFactory() as db:
            account_id = current_account(db).id
            lock_writes(db)
            engine_run = latest_engine_run(db)
            if engine_run is None or engine_run["id"] != request.form.get("engine_run_id", type=int):
                flash("A newer reconciliation exists: review its results and confirm again. Nothing was written.",
                      "error")
                return back("results")
            check = intake.completeness(db)
            if scope == "automatic":
                items = _proposals(db, check, engine_run["id"], state=PROPOSAL)
                note = f"Confirmed from automatic reconciliation (engine run #{engine_run['id']}, Upload and Reconcile)."
            elif scope == "group":
                items = _proposals(db, check, engine_run["id"], state=TO_CONFIRM, group_key=request.form.get("group"))
                note = f"Confirmed from internet research (engine run #{engine_run['id']}, Upload and Reconcile)."
            else:
                abort(400)
            if not items:
                flash("Nothing to confirm here any more.", "info")
                return back("results")
            outcome = confirm_proposals(db, items, account_id=account_id, note=note)
            db.commit()
        flash(f"{outcome['written']} proposal(s) confirmed and now recorded in Bank"
              + (f"; {len(outcome['skipped'])} skipped" if outcome["skipped"] else "") + ".", "info")
        if outcome["skipped"]:
            flash("Skipped: " + "; ".join(f"#{s['id']} {s['reason']}" for s in outcome["skipped"][:8]), "error")
        return back("results")

    # ------------------------------------------------------------------ QuickBooks Online

    @app.route("/bank/work/qbo")
    @gate
    def bank_work_qbo():
        try:
            with SessionFactory() as db:
                check = intake.completeness(db)
                view = qbo_view(db, check)
                cos = qbo_books.companies(db)
                chosen = request.args.get("company", type=int)
                if chosen not in {c.id for c in cos}:
                    chosen = next((c["owner_id"] for c in view["companies"] if c["owner_id"] and c["ready"] + c["blocked"]),
                                  cos[0].id if cos else None)
                company = db.get(m.ReportingEntity, chosen) if chosen else None
                sources = {s.id: s for s in db.scalars(select(m.PaymentInstrument))}
                whats = {w.id: w for w in db.scalars(select(m.BankAccountingClassification))}

                def local(r):
                    if r.kind == qbo_export.PAYMENT_ACCOUNT:
                        return sources[r.local_id].display_name if r.local_id in sources else "—"
                    return f"{whats[r.local_id].code} {whats[r.local_id].name}" if r.local_id in whats else "—"

                rows = [dict(id=r.id, kind=r.kind, local_id=r.local_id, local=local(r), name=r.qbo_account_name,
                             type=r.qbo_account_type, status=r.status, proposed_from=r.proposed_from,
                             verified_by=r.verified_by, has_id=bool(r.qbo_account_id), entity_id=r.reporting_entity_id)
                        for r in qbo_books.maps(db).values()]
                mine = sorted([r for r in rows if company and r["entity_id"] == company.id],
                              key=lambda x: (x["status"] != qbo_books.PROPOSED, x["kind"], x["local"]))
                legacy = sorted([r for r in rows if r["status"] == qbo_books.GLOBAL_LEGACY], key=lambda x: (x["kind"], x["local"]))
                return render_template(
                    "bank_work_qbo.html", check=check, view=view, companies=cos, company=company,
                    chart=list(qbo_books.chart(db, company.id).values()) if company else [],
                    need=view["plan"]["need"].get(company.id, {}) if company else {},
                    mine=mine, legacy=legacy,
                    batches=[b for b in qbo_books.batch_list(db) if company and b["owner_id"] == company.id],
                    prerequisites=qbo_books.SEND_PREREQUISITES,
                    CATEGORY=qbo_export.CATEGORY, PAYMENT_ACCOUNT=qbo_export.PAYMENT_ACCOUNT, MAX_ROWS=qbo_books.MAX_ROWS)
        except OperationalError:
            return busy_page()

    def to_company(anchor):
        return redirect(url_for("bank_work_qbo", company=request.form.get("company_id", type=int), _anchor=anchor))

    def qbo_write(anchor, action, done):
        """One QBO configuration / export write: refused with its reason, or committed with `done`'s message."""
        require_csrf()
        with SessionFactory() as db:
            lock_writes(db)
            try:
                out = action(db, current_account(db).id)
                message = done(out)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return to_company(anchor)
            db.commit()
        flash(message, "info")
        return to_company(anchor)

    @app.route("/bank/work/qbo/accounts", methods=["POST"])
    @gate
    def bank_work_qbo_accounts():
        f = request.files.get("file")
        if not f or not f.filename:
            require_csrf()
            flash("Choose the Account List file exported from this company's QuickBooks Online.", "error")
            return to_company("chart")
        content = f.read()
        return qbo_write("chart", lambda db, acc: qbo_books.import_account_list(
            db, content, entity_id=request.form.get("company_id", type=int), account_id=acc),
            lambda r: f"{r['company']}'s QuickBooks chart imported: {r['added']} new, {r['updated']} updated, "
                      f"{r['deactivated']} no longer in the list." + (f" File title: “{r['title']}”." if r["title"] else ""))

    @app.route("/bank/work/qbo/map", methods=["POST"])
    @gate
    def bank_work_qbo_map():
        return qbo_write("mappings", lambda db, acc: qbo_books.set_map(
            db, request.form.get("company_id", type=int), request.form.get("kind"),
            request.form.get("local_id", type=int) or 0, request.form.get("name"), account_id=acc),
            lambda r: "Correspondence verified in this company's chart; it is reused by every movement of this company.")

    @app.route("/bank/work/qbo/map/<int:map_id>/verify", methods=["POST"])
    @gate
    def bank_work_qbo_verify(map_id: int):
        return qbo_write("mappings", lambda db, acc: qbo_books.verify_proposal(db, map_id, account_id=acc),
                         lambda r: f"Proposal verified: {r.qbo_account_name} is in this company's chart.")

    @app.route("/bank/work/qbo/copy", methods=["POST"])
    @gate
    def bank_work_qbo_copy():
        return qbo_write("mappings", lambda db, acc: qbo_books.copy_as_proposals(
            db, request.form.get("from_company_id", type=int), request.form.get("company_id", type=int), account_id=acc),
            lambda n: f"{n} correspondence(s) copied as proposals: each one is used only after you verify it below.")

    @app.route("/bank/work/qbo/export", methods=["POST"])
    @gate
    def bank_work_qbo_export():
        """Generates the journal-entry import file of ONE company's ready movements (a batch). Downloading it is a
        separate step; importing it in QBO is a third one, confirmed by a person."""
        def action(db, acc):
            return qbo_books.generate_batch(db, qbo_scope(db, intake.completeness(db)),
                                            owner_id=request.form.get("company_id", type=int) or 0, account_id=acc,
                                            feeds_excluded=request.form.get("feeds_excluded") == "1")
        return qbo_write("files", action, lambda b: f"File generated: {b.file_name} ({b.journal_count} entries, "
                         f"{b.line_count} lines). Download it, import it in QuickBooks, then confirm the import here.")

    @app.route("/bank/work/qbo/files/<int:batch_id>/confirm", methods=["POST"])
    @gate
    def bank_work_qbo_confirm(batch_id: int):
        return qbo_write("files", lambda db, acc: qbo_books.confirm_import(
            db, batch_id, account_id=acc, note=request.form.get("note", "")),
            lambda b: f"{b.file_name}: import in QuickBooks confirmed.")

    @app.route("/bank/work/qbo/files/<int:batch_id>/withdraw", methods=["POST"])
    @gate
    def bank_work_qbo_withdraw(batch_id: int):
        return qbo_write("files", lambda db, acc: qbo_books.withdraw(
            db, batch_id, account_id=acc, reason=request.form.get("reason", "")),
            lambda b: f"{b.file_name} withdrawn (not imported): its movements can go into a new file.")

    @app.route("/bank/work/qbo/files/<int:batch_id>")
    @gate
    def bank_work_qbo_file(batch_id: int):
        """The generated file, always the same content: a new download creates nothing and exports nothing again."""
        with SessionFactory() as db:
            lock_writes(db)
            try:
                b = qbo_books.download(db, batch_id)
            except ValueError:
                abort(404)
            content, name = b.content, b.file_name
            db.commit()
        return app.response_class(content, mimetype="text/csv", headers={
            "Content-Disposition": f'attachment; filename="{name}"'})

    @app.route("/bank/work/qbo-preview.json")
    @gate
    def bank_work_qbo_preview():
        """The QuickBooks Online preview of the work period, as a file to inspect. A preview, not an export."""
        with SessionFactory() as db:
            check = intake.completeness(db)
            plan = qbo_books.plan(db, qbo_scope(db, check))
        body = json.dumps(dict(kind="PREVIEW — nothing was exported or sent to QuickBooks Online", **plan),
                          indent=2, default=str)
        return app.response_class(body, mimetype="application/json", headers={
            "Content-Disposition": "attachment; filename=bank_qbo_preview.json"})
