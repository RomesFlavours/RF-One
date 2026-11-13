"""AI rules check (BANK_AI_RULE_CHECK_001): every operative rule executed on every movement, READ-ONLY.

The rules saved on the AI Rules page (and the WHO extraction rules and Recognition Profiles of the same
catalogue) are run with Bank's own executor — the code the reconciliation engine uses — on every movement
of the database. The page shows, for each rule, the movements it intercepts and the WHO / WHY it gives,
next to the human decision and the engine's last result, plus the movements where rules disagree and those
no rule reads. Nothing is written: no WHO, WHY, WHAT or classification changes here.
"""
import threading
from collections import defaultdict

from flask import jsonify, render_template
from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules, flow

_CACHE = {}
_LOCK = threading.Lock()


def _signature(db, entries):
    return (tuple((r.id, v.id) for r, v, _s in entries), db.scalar(select(func.count(m.FinancialTransaction.id))),
            db.scalar(select(func.max(m.FinancialTransaction.id))), db.scalar(select(func.max(m.BankTransactionExplanation.id))))


def compute(db):
    """Execute every operative rule on every movement (cached until rules or movements change)."""
    entries = flow.entries(db)
    key = _signature(db, entries)
    with _LOCK:
        if _CACHE.get("key") == key:
            return _CACHE["value"]
    whys = {r.id: r.name for r in db.scalars(select(m.BankTransactionReason))}
    whats = {c.id: c.name for c in db.scalars(select(m.BankAccountingClassification))}
    whos = {o.id: o.canonical_name for o in db.scalars(select(m.BankOccurrence))}
    sources = {i.id: i.display_name for i in db.scalars(select(m.PaymentInstrument))}
    engine = {}
    run = db.scalars(select(m.BankEngineRun).order_by(m.BankEngineRun.id.desc()).limit(1)).first()
    if run is not None:
        import json
        for res in db.scalars(select(m.BankEngineResult).where(m.BankEngineResult.run_id == run.id)):
            p = json.loads(res.payload_json)
            engine[res.financial_transaction_id] = dict(who=p.get("who_name"), why=p.get("why"), status=p.get("status"))
    builder = ai_rules.RowBuilder(db)
    extractors = [e for e in entries if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "EXTRACTOR"]
    photos = [e for e in entries if e[2].get("engine") == flow.ENGINE and e[2].get("kind") == "PHOTO"]
    structured = [e for e in entries if e[2].get("engine") != flow.ENGINE]
    movements, hits = {}, defaultdict(list)
    for txn in db.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id)):
        ex = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
        human = ex is not None and ex.decision_source == "HUMAN"
        movements[txn.id] = dict(
            id=txn.id, source=sources.get(txn.payment_instrument_id) or "—", date=str(txn.posting_date or txn.transaction_date or ""),
            description=txn.description_original or "", amount=f"{(txn.amount_minor or 0) / 100:,.2f}",
            human_who=whos.get(ex.occurrence_id) if human and ex.occurrence_id else None,
            human_why=whys.get(ex.transaction_reason_id) if human and ex.transaction_reason_id else None,
            human_what=whats.get(ex.accounting_classification_id) if human and ex.accounting_classification_id else None,
            engine=engine.get(txn.id))
        results = []
        for rule, _v, spec in extractors:
            who = flow.extract(spec, txn.description_original)
            if who:
                results.append(dict(rule=rule.id, who=who, why=None))
        row = builder.row(txn, None)
        for rule, _v, spec in structured:
            try:
                done = ai_rules.execute(spec, row)
            except Exception:  # noqa: BLE001 — a malformed rule never stops the check; it simply reads nothing
                continue
            if done.outcome == "MATCH":
                results.append(dict(rule=rule.id, who=done.who, why=done.why or done.why_verify))
        named = {flow.clean(r["who"]) for r in results if r["who"]}
        who_now = next((r["who"] for r in results if r["who"]), None) if len(named) == 1 else None
        for entry in photos:
            if who_now:
                choice = flow.choose(db, txn, entry, who_now, allow_missing_whom=True)
                if choice:
                    results.append(dict(rule=entry[0].id, who=choice["who"], why=whys.get(choice["why_id"])))
        for r in results:
            hits[r["rule"]].append((txn.id, r["who"], r["why"]))
        movements[txn.id]["rules"] = results
    rules = []
    for rule, version, spec in entries:
        rows = hits.get(rule.id, [])
        agree = disagree = 0
        for tid, who, why in rows:
            mv = movements[tid]
            for mine, theirs in ((who, mv["human_who"]), (why, mv["human_why"])):
                if mine and theirs:
                    if flow.clean(mine) == flow.clean(theirs):
                        agree += 1
                    else:
                        disagree += 1
        rules.append(dict(id=rule.id, title=rule.user_title or rule.title, text=version.rule_text, version=version.version_no,
                          kind="WHO extraction" if spec.get("engine") == flow.ENGINE and spec.get("kind") == "EXTRACTOR"
                          else "Recognition profile" if spec.get("engine") == flow.ENGINE else "AI rule",
                          movements=len(rows), gives_who=sum(1 for _t, w, _y in rows if w), gives_why=sum(1 for _t, _w, y in rows if y),
                          human_agree=agree, human_disagree=disagree))
    rules.sort(key=lambda r: (-r["movements"], (r["title"] or "").casefold()))
    conflicts = [tid for tid, mv in movements.items()
                 if len({flow.clean(r["who"]) for r in mv["rules"] if r["who"]}) > 1
                 or len({flow.clean(r["why"]) for r in mv["rules"] if r["why"]}) > 1]
    with_who = {tid for tid, mv in movements.items() if any(r["who"] for r in mv["rules"])}
    with_why = {tid for tid, mv in movements.items() if any(r["why"] for r in mv["rules"])}
    read = {tid for tid, mv in movements.items() if mv["rules"]}
    value = dict(movements=movements, rules=rules, hits=hits, conflicts=conflicts,
                 summary=dict(movements=len(movements), rules=len(entries), rules_matching=sum(1 for r in rules if r["movements"]),
                              read=len(read), with_who=len(with_who), with_why=len(with_why), conflicts=len(conflicts),
                              unread=len(movements) - len(read), engine_run=run.id if run else None))
    with _LOCK:
        _CACHE.update(key=key, value=value)
    return value


def _row(mv, rule_id=None, names=None):
    out = {k: mv[k] for k in ("id", "source", "date", "description", "amount", "human_who", "human_why", "human_what", "engine")}
    mine = [r for r in mv["rules"] if rule_id is None or r["rule"] == rule_id]
    out["who"] = mine[0]["who"] if mine else None
    out["why"] = mine[0]["why"] if mine else None
    out["others"] = [dict(rule=r["rule"], title=(names or {}).get(r["rule"]), who=r["who"], why=r["why"])
                     for r in mv["rules"] if rule_id is None or r["rule"] != rule_id]
    return out


def register(app, *, gate, SessionFactory, endpoint):
    @app.route("/bank/ai-rules/check")
    @gate
    def bank_ai_rules_check_page():
        return render_template("bank_ai_rule_check.html")

    @app.route("/bank/ai-rules/check/data")
    @gate
    @endpoint
    def bank_ai_rules_check_data():
        with SessionFactory() as db:
            v = compute(db)
            return jsonify(ok=True, summary=v["summary"], rules=v["rules"])

    @app.route("/bank/ai-rules/check/rules/<int:rule_id>")
    @gate
    @endpoint
    def bank_ai_rules_check_rule(rule_id):
        with SessionFactory() as db:
            v = compute(db)
            names = {r["id"]: r["title"] for r in v["rules"]}
            rows = [_row(v["movements"][tid], rule_id, names) for tid, _w, _y in v["hits"].get(rule_id, [])]
            rows.sort(key=lambda r: r["description"].casefold())
            return jsonify(ok=True, rows=rows)

    @app.route("/bank/ai-rules/check/list/<which>")
    @gate
    @endpoint
    def bank_ai_rules_check_list(which):
        if which not in ("conflicts", "unread"):
            raise ValueError("Unknown list.")
        with SessionFactory() as db:
            v = compute(db)
            names = {r["id"]: r["title"] for r in v["rules"]}
            ids = v["conflicts"] if which == "conflicts" else [t for t, mv in v["movements"].items() if not mv["rules"]]
            rows = [_row(v["movements"][t], None, names) for t in ids]
            rows.sort(key=lambda r: r["description"].casefold())
            return jsonify(ok=True, rows=rows)
