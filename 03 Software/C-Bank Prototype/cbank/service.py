"""Runs: the same engine for the sample, a month or the whole history (decision 24)."""
from __future__ import annotations

import json
import threading
import time

from . import engine as engine_mod, legacy, sample, store


def new_engine(con):
    return engine_mod.Engine(legacy.session(), con)


def execute(con, kind: str, month: str | None = None) -> int:
    with _RUN_LOCK:
        return _execute(con, kind, month)


def _execute(con, kind: str, month: str | None = None) -> int:
    eng = new_engine(con)
    cases: dict[int, list[str]] = {}
    if kind == "sample":
        picked = sample.select(eng)
        cases = sample.case_index(picked)
        txns = [eng.by_id[i] for i in sorted(cases)]
        label, scope = "MVP sample", dict(kind="sample", cases=picked)
    elif kind == "month" and month:
        txns = [t for t in eng.txns if str(t.posting_date).startswith(month)]
        label, scope = f"Month {month}", dict(kind="month", month=month)
    elif kind == "all":
        # The whole history (Historical Cleanup and Daily Operations use this same run).
        txns = list(eng.txns)
        label, scope = "Whole history", dict(kind="all", bank_signature=bank_signature(eng))
    else:
        raise ValueError("Choose the sample, a month (YYYY-MM) or the whole history.")
    # Persist only unambiguous new catalog identities read by approved rules, never movement decisions.
    candidate_names = []
    for txn in txns:
        if txn.id in eng.matches or (eng.bank_decision(txn)["source"] == "HUMAN" and eng.bank_decision(txn)["who_id"]):
            continue
        if txn.id in eng.ambiguous or engine_mod.matching.is_card_payment_out(txn, eng.c.instruments, eng.card_payment_out):
            continue
        recognition = eng.recogniser.recognise(txn, row=eng.c.rule_row(txn))
        if recognition.outcome == "FOUND" and recognition.method == "RULE" and not recognition.known:
            candidate_names.append(recognition.who)
    registration = dict(created=[], reused=[], held={})
    if candidate_names:
        ids = [t.id for t in txns]
        eng.db.close()
        registration = legacy.register_rule_whos(candidate_names)
        eng = new_engine(con)
        txns = [eng.by_id[i] for i in ids]
    eng.who_registration_holds = registration["held"]
    if kind == "all":
        scope["bank_signature"] = bank_signature(eng)
    results = []
    for t in txns:
        r = eng.evaluate(t)
        r["cases"] = cases.get(t.id, [])
        results.append(r)
    pairs = [(r["who_id"], eng.by_id[r["txn_id"]].payment_instrument_id) for r in results if r.get("who_id")]
    eng.db.close()
    added_pairs = legacy.ensure_source_classification_pairs(pairs)
    if kind == "all":
        scope["bank_signature"] = current_bank_signature()
    summary = engine_mod.summarize(results)
    summary["new_who_source_pairs"] = added_pairs
    summary["new_catalog_whos"] = len(registration["created"])
    summary["held_new_who_names"] = len(registration["held"])
    previous = store.previous_full_run(con) if kind == "all" else None
    if previous:
        # Daily operations: what is new since the previous full run, and which card payments that
        # were waiting / ambiguous are matched now (they are retried on every run, no manual relaunch).
        before = {r["txn_id"]: r for r in store.results(con, previous["id"])}
        summary["new_movements"] = sum(1 for r in results if r["txn_id"] not in before)
        summary["resumed_matches"] = sum(
            1 for r in results if (r.get("match") or {}).get("state") == "MATCHED"
            and ((before.get(r["txn_id"]) or {}).get("match") or {}).get("state") in ("WAITING", "AMBIGUOUS", None)
            and r["txn_id"] in before)
    run_id = store.save_run(con, label, scope, results, summary)
    new_pairs = store.record_matches(con, run_id, results)
    summary["new_matched_pairs"] = new_pairs
    store.update_summary(con, run_id, summary)
    return run_id


def manual_signature(db):
    """Current manual decisions also wake the watcher after movement-level edits."""
    import hashlib
    from sqlalchemy import select
    m = legacy.m
    decisions = db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.explanation_id,
        m.BankTransactionExplanation.occurrence_id, m.BankTransactionExplanation.transaction_reason_id)
        .join(m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
        .where(m.BankTransactionExplanation.decision_source == "HUMAN").order_by(m.FinancialTransaction.id)).all()
    allocations = db.execute(select(m.BankTransactionAllocation.id, m.BankTransactionAllocation.financial_transaction_id,
        m.BankTransactionAllocation.reporting_entity_id, m.BankTransactionAllocation.amount_minor)
        .where(m.BankTransactionAllocation.decision_source == "HUMAN").order_by(m.BankTransactionAllocation.id)).all()
    return hashlib.sha256(repr((decisions, allocations)).encode()).hexdigest()[:16]


def bank_signature(eng) -> str:
    """What identifies the data a run saw: movement count, last id, total amount, approved WHY rules, and what
    recognises a WHO (WHO rules, aliases, WHO catalog)."""
    return (f"{len(eng.txns)}:{max((t.id for t in eng.txns), default=0)}:{sum(t.amount_minor or 0 for t in eng.txns)}"
            f":{RECONCILIATION_POLICY}:{manual_signature(eng.db)}:{legacy.why_patterns.knowledge_signature(eng.db)}:{legacy.who_search_text.knowledge_signature(eng.db)}"
            f":{legacy.who_why_rules.knowledge_signature(eng.db)}")


def current_bank_signature() -> str:
    """Same signature read straight from Bank (read-only), without building an engine — movements plus the
    approved WHY rules."""
    from sqlalchemy import func, select
    db = legacy.session()
    try:
        q = select(func.count(), func.max(legacy.m.FinancialTransaction.id), func.sum(legacy.m.FinancialTransaction.amount_minor)).where(
            legacy.m.FinancialTransaction.accounting_status == "CANONICAL",
            legacy.m.FinancialTransaction.duplicate_status.is_distinct_from("CONFIRMED_DUPLICATE"))
        n, last, total = db.execute(q).one()
        # An approved, revised or (de)activated WHY rule is new knowledge: it also starts a new run.
        # BANK_WHO_RULES_001: a WHO rule, alias or WHO changed is new knowledge too.
        return (f"{n}:{last or 0}:{total or 0}:{RECONCILIATION_POLICY}:{manual_signature(db)}:{legacy.why_patterns.knowledge_signature(db)}"
                f":{legacy.who_search_text.knowledge_signature(db)}:{legacy.who_why_rules.knowledge_signature(db)}")
    finally:
        db.close()


def run_if_bank_changed(con) -> int | None:
    """Automatic Daily Operations: a new full run whenever Bank has new/changed imported movements
    (read-only check). Nothing is written to Bank; the result goes to the C-Bank store."""
    with _RUN_LOCK:
        previous = store.previous_full_run(con)
        if previous and previous["scope"].get("bank_signature") == current_bank_signature():
            return None
        return execute(con, "all")


RECONCILIATION_POLICY = "who-why-mode-v5"   # BANK_WHO_WHY_MODE_001: UNIQUE pair / MULTIPLE rules

_RUN_LOCK = threading.RLock()


def start_auto_runs(con, interval_seconds: int = 60) -> threading.Thread:
    """The minimal hook after a Bank CSV import, with no change to Bank: C-Bank checks the imported
    movements (read-only) every minute and, when they changed, runs the engine on the whole history
    (new movements, retried card payments). Errors are logged and the next check simply tries again."""
    def loop():
        while True:
            try:
                run_id = run_if_bank_changed(con)
                if run_id:
                    print(f"C-Bank: Bank data changed — automatic run #{run_id} done.", flush=True)
            except Exception as exc:  # noqa: BLE001 — never stops the watcher
                print(f"C-Bank: automatic run skipped: {exc}", flush=True)
            time.sleep(interval_seconds)
    thread = threading.Thread(target=loop, daemon=True, name="cbank-auto-run")
    thread.start()
    return thread


def reevaluate(con, run_id: int, txn_ids: set[int] | None = None) -> int:
    """New knowledge re-processes ONLY unresolved movements of the run, plus the
    movement just decided (decision 46). Reconciled ones stay as they were."""
    eng = new_engine(con)
    current = store.results(con, run_id)
    updated = []
    changed = 0
    for r in current:
        if r["status"] == engine_mod.RECONCILED and not (txn_ids and r["txn_id"] in txn_ids):
            updated.append(r)
            continue
        txn = eng.by_id.get(r["txn_id"])
        if txn is None:
            updated.append(r)
            continue
        new = eng.evaluate(txn)
        new["cases"] = r.get("cases", [])
        changed += json.dumps(new, sort_keys=True, default=str) != json.dumps(r, sort_keys=True, default=str)
        updated.append(new)
    store.replace_results(con, run_id, updated, engine_mod.summarize(updated))
    return changed
