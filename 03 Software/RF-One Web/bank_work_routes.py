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
  upload. It runs, in the background, the existing Amazon WHY proposals (`bank_amazon.process_pending`, only
  with the recorded ChatGPT consent) and then the single engine (`bank_guided_reconciliation`: matching,
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

import bank_amazon
import bank_guided_reconciliation
import bank_work_research

INTAKE, WORK_RUN = "INTAKE_FILE", "WORK_RUN"
# File states. Blocking: the person must answer before the automatic reconciliation.
INTEGRATED, ALREADY_LOADED, AMAZON_LOADED, KEPT_ASIDE, REMOVED = (
    "INTEGRATED", "ALREADY_LOADED", "AMAZON_LOADED", "KEPT_ASIDE", "REMOVED")
NEEDS_SOURCE, SOURCE_INCOMPLETE, UNREADABLE_ROWS, CHECK_SOURCE, NOT_RECOGNIZED, FAILED = (
    "NEEDS_SOURCE", "SOURCE_INCOMPLETE", "UNREADABLE_ROWS", "CHECK_SOURCE", "NOT_RECOGNIZED", "FAILED")
BLOCKING = intake.BLOCKING_FILE_STATES   # the gate reads the same states
STATE_LABELS = {
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


def receive(db, file_name: str, content: bytes, account_id: int) -> dict:
    """Record one uploaded file and settle it as far as Bank can alone. Never commits."""
    data = dict(file_name=file_name, received_at=_now(), account_id=account_id, size=len(content),
                content_b64=base64.b64encode(content).decode("ascii"), state=None, question=None)
    rec = m.BankFlowArtifact(kind=INTAKE, account_id=account_id, payload="{}")
    db.add(rec)
    db.flush()
    try:
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("The file is larger than 25 MB.")
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
            data.update(state=KEPT_ASIDE, question=None, note="Bank cannot read PayPal activity files yet: the file "
                        "is kept here and not used. It does not block the reconciliation.")
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
        data.update(state=FAILED, question=f"{exc} Nothing of this file was imported.")
    _save(rec, data)
    return data


def file_view(db, rec) -> dict:
    data = json.loads(rec.payload)
    data.pop("content_b64", None)
    data["id"] = rec.id
    data["state_label"] = STATE_LABELS.get(data.get("state"), data.get("state") or "—")
    data["blocking"] = data.get("state") in BLOCKING
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
    return inspect(db.get_bind()).has_table("bank_engine_runs")


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
        update(status="RUNNING", started_at=_now(), step="Amazon: product WHY proposals")
        warnings = []
        try:   # advisory: the engine runs whatever happens here
            with SessionFactory() as db:
                has_reports = bool(intake.amazon_reports(db))
                if has_reports:
                    bank_amazon.ingest(db, [], account_id)   # queues one Amazon analysis of every saved report
                    db.commit()
            if has_reports:
                bank_amazon.after_import(app, SessionFactory)()
                with SessionFactory() as db:
                    last = bank_amazon.artifacts(db, bank_amazon.RUN, account_id)
                    state = json.loads(last[0].payload) if last else {}
                    if state.get("status") == "ERROR":
                        error = state.get("error") or ""
                        if "SQL" in error or "locked" in error:
                            error = "the database was busy; they are retried at the next run"
                        warnings.append("Amazon product proposals not made: " + error)
        except OperationalError:
            warnings.append("Amazon product proposals not made: the database was busy; they are retried at the next run.")
        except Exception as exc:  # noqa: BLE001 — reported with the run, never stops it
            warnings.append(f"Amazon product proposals not made: {exc}"[:500])
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
    MATCHED: 'Applicato automaticamente — giroconti e pagamenti carta abbinati',
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
    if r["status"] == "RECONCILED":
        if (r.get("match") or {}).get("state") == "MATCHED" and not r.get("who_id"):
            return MATCHED, "", "context", None
        if r.get("who_id") and (r.get("why_id") or split_ok):
            return PROPOSAL, "", origin, dict(source="ENGINE", who_id=r["who_id"], who=r.get("who_name"),
                                              why_id=r.get("why_id"), why=r.get("why"), split=r.get("split") if split_ok else None)
        return MANUAL, "NO_CATALOG_WHO", origin, None
    code = r["exceptions"][0]["code"] if r.get("exceptions") else "INCOMPLETE"
    if research:
        outcome = research.get("outcome")
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

    @app.route("/bank/work")
    @gate
    def bank_work():
        try:
            with SessionFactory() as db:
                state = page_state(db)
                sources = [i for i in instruments(db) if i.is_payment_source]
                results = results_view(db, state["check"]) if not state["running"] else None
                qbo = qbo_view(db, state["check"]) if results else None
                return render_template(
                    "bank_work.html", **state, sources=sources, results=results, qbo=qbo,
                    periods={fp.batch_id: fp for sc in state["check"].sources for fp in sc.files},
                    guided=bank_guided_reconciliation.available(), answer_labels=intake.ANSWER_LABELS,
                    state_titles=STATE_TITLES, who_origins=WHO_ORIGINS,
                    research_consent=bank_work_research.consent(app), research_sent=bank_work_research.SENT,
                    research_not_sent=bank_work_research.NOT_SENT)
        except OperationalError:
            return busy_page()

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
            for f in uploaded:
                data = receive(db, f.filename, f.read(), account_id)
                outcome.append(data)
            db.commit()
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
            rec = db.get(m.BankFlowArtifact, file_id)
            _save(rec, data)
            db.commit()
        flash(f"{data['file_name']} — {STATE_LABELS.get(data['state'], data['state'])}.",
              "error" if data["state"] in BLOCKING else "info")
        return back(f"file-{file_id}")


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
