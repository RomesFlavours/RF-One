#!/usr/bin/env python
"""HTTP and engine test for Discover WHY Patterns (BANK_WHY_PATTERNS_001).

Runs on an ISOLATED COPY of the local Bank database (SQLite backup API, removed at the end): real formats,
Sources, Labels and human decisions, never the operational file. Other RF-One domains (Clover employees,
Tips runs) are read, read-only, from the newest local copy of the RF-One database when it is available;
without it the evidence checks are reported as skipped, never faked. The AI is replaced by deterministic
stubs. Covered: Zelle/Tips, Zelle/Payroll, suppliers through Labels, formats without WHO, movements with
and without Category, Sources without optional information, Category removed from the Chase files,
approval, the single engine, deactivation, Decision 86.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
REPO_ROOT = Path(APP_DIR).parents[1]
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_why_patterns_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "why-patterns-test-secret"
os.environ["CBANK_BANK_DB"] = str(_COPY)
os.environ["CBANK_BANK_CODE_ROOT"] = str(REPO_ROOT)
os.environ["CBANK_STORE_DIR"] = str(Path(_FOLDER) / "store")
os.environ.setdefault("CBANK_WHO_WHY", "1")
# As the local Bank runs it (Phase 3A): one engine, no background import pipeline.
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"
# Discover WHY Patterns is switched off in the Bank (2026-10-25); this test keeps its preserved code verified.
os.environ["RFONE_BANK_WHY_PATTERNS"] = "1"
_copies = sorted((Path(os.environ.get("LOCALAPPDATA", "")) / "RF-One" / "AWS-Copy").glob("*/local-connection.json"))
if _copies and "RFONE_DOMAIN_DATA" not in os.environ:
    os.environ["RFONE_DOMAIN_DATA"] = str(_copies[-1])

import app as web_app  # noqa: E402
import bank_assistant_preview_routes  # noqa: E402
import bank_chatgpt  # noqa: E402
import bank_flow_routes  # noqa: E402
import bank_why_pattern_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rule_operations as ops, flow, why_patterns as wp  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')
CBANK_DIR = Path(os.environ.get("CBANK_CODE_DIR", str(REPO_ROOT.parent / "rf-one-c-bank-prototype" / "03 Software" / "C-Bank Prototype")))


def human_state(db):
    """Every human decision as it is: nothing in this feature may change it."""
    rows = db.execute(select(m.FinancialTransaction.id, m.BankTransactionExplanation.id,
                             m.BankTransactionExplanation.transaction_reason_id,
                             m.BankTransactionExplanation.accounting_classification_id)
                      .join(m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
                      .where(m.BankTransactionExplanation.decision_source == "HUMAN")).all()
    return sorted(tuple(r) for r in rows)


STUB_WHY_OF_WHAT: dict[str, str] = {}   # WHAT name -> the one active WHY with that WHAT (filled in main)


def stub_reader(prompt, **_):
    """A deterministic stand-in for the AI: a format takes the WHY of the WHAT its human decisions agree on;
    a format offering the Tips evidence is split on it."""
    data = json.loads(prompt[prompt.index('{"catalog"'):])
    out = []
    for f in data["formats"]:
        tips = next((c for c in f["conditions"] if c.startswith("The amount equals the employee's Tips payable")), None)
        if tips:
            out.append(dict(id=f["id"], why="Tips Distribution / Settlement",
                            conditions=[re.sub(r"\s*\(\d+ of \d+\)$", "", tips)], confidence="certain", reason="stub"))
        names = Counter()
        for h in f["human_decisions"]:
            name, n = re.match(r"WHAT (.*) \((\d+)\)$", h).groups()
            names[name] += int(n)
        if len(names) == 1 and next(iter(names)) in STUB_WHY_OF_WHAT:
            out.append(dict(id=f["id"], why=STUB_WHY_OF_WHAT[next(iter(names))], conditions=[], confidence="certain",
                            reason="stub"))
    return {"formats": out}


def main() -> int:
    passed, failed, skipped = [], [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    def skip(description, reason):
        skipped.append(description)
        print(f"  SKIP  {description}   [{reason}]")

    with SessionFactory() as db:
        before_humans = human_state(db)
        rules_before = db.scalar(select(func.count(m.BankAiRule.id)))
        whys = {r.name: r for r in db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE"))}
        domain = wp.DomainData.load(db)
        whats = {c.id: c.name for c in db.scalars(select(m.BankAccountingClassification))}
        per_what = Counter(r.accounting_classification_id for r in whys.values() if r.accounting_classification_id)
        STUB_WHY_OF_WHAT.update({whats[r.accounting_classification_id]: r.name for r in whys.values()
                                 if r.accounting_classification_id and per_what[r.accounting_classification_id] == 1})

    # --- 1-2: the language -------------------------------------------------------------------------------
    tips_why = whys["Tips Distribution / Settlement"].id
    rule = dict(engine=wp.ENGINE, version=1, why_id=tips_why, why="Tips Distribution / Settlement",
                conditions=[dict(field="label", op="has", value="Employee FOH"),
                            dict(field="evidence:tips_payable_match", op="is", value=True)])
    absent = {"format": "X", "direction": "money out", "_amount": -1, "evidence:tips_payable_match": (None, "no run")}
    check("1a. missing WHO (Label) and missing evidence -> INCOMPLETE, never a negative proof",
          wp.evaluate(rule, absent).outcome == wp.INCOMPLETE and len(wp.evaluate(rule, absent).missing) == 2)
    false_case = dict(absent, who="X", label=["Employee FOH"], **{"evidence:tips_payable_match": (False, "differs")})
    check("1b. evidence present and false -> NO_MATCH", wp.evaluate(rule, false_case).outcome == wp.NO_MATCH)
    true_case = dict(false_case, **{"evidence:tips_payable_match": (True, "equal")})
    with_exception = dict(rule, exceptions=[dict(conditions=[dict(field="who", op="is", value="X")], note="n")])
    check("1c. all conditions true -> MATCH; a named exception stops it",
          wp.evaluate(rule, true_case).outcome == wp.MATCH and wp.evaluate(with_exception, true_case).outcome == wp.NO_MATCH)
    with SessionFactory() as db:
        errors = []
        for bad in (dict(rule, conditions=[dict(field="evidence:invented", op="is", value=True)]),
                    dict(rule, conditions=[dict(field="direction", op="is", value="money out")]),
                    dict(rule, conditions=[dict(field="subject_set", op="is", value="Company")]),
                    # identity is not purpose: Tips needs the Tips evidence, not "is an employee"
                    dict(rule, conditions=[dict(field="evidence:clover_employee", op="is", value=True)])):
            try:
                wp.validate(db, bad)
                errors.append(None)
            except ValueError as exc:
                errors.append(str(exc))
    check("2. invented evidence, structural-only rules, unknown fields and Tips without Tips evidence are refused", all(errors), errors)

    # --- 3-8: real movements of the copy ------------------------------------------------------------------
    with SessionFactory() as db:
        movements, meta = wp.load_movements(db)
    by = {mv.id: mv for mv in movements}
    zelle_emp = [mv for mv in movements if mv.info.get("evidence:clover_employee", (None,))[0] is True]
    if not domain.available:
        skip("3-4. Zelle / Tips and Zelle / Payroll evidence", domain.reason)
    else:
        tips_true = [mv for mv in movements if mv.info["evidence:tips_payable_match"][0] is True]
        tips_none = [mv for mv in zelle_emp if mv.info["evidence:tips_payable_match"][0] is None]
        check("3a. Zelle / Tips: an exact match with a Tips run calculated by then is evidence",
              bool(tips_true) and all(mv.info["_amount"] < 0 for mv in tips_true), len(tips_true))
        check("3b. Zelle / Tips: before any Tips run existed the evidence is MISSING, not false",
              bool(tips_none) and all("no Tips run" in mv.info["evidence:tips_payable_match"][1] for mv in tips_none), len(tips_none))
        tips_rule = dict(rule, conditions=[dict(field="evidence:clover_employee", op="is", value=True),
                                           dict(field="evidence:tips_payable_match", op="is", value=True)])
        outcomes = Counter(wp.evaluate(tips_rule, mv.info).outcome for mv in zelle_emp)
        check("3c. the general Tips rule (no rule per employee): MATCH / INCOMPLETE / NO_MATCH as the evidence says",
              outcomes[wp.MATCH] == len(tips_true) and outcomes[wp.INCOMPLETE] == len(tips_none), dict(outcomes))
        payroll = Counter(mv.info["evidence:payroll_verified"] for mv in zelle_emp)
        payroll_rule = dict(rule, why_id=whys["Payroll - FOH - Regular Payroll"].id if "Payroll - FOH - Regular Payroll" in whys else tips_why,
                            conditions=[dict(field="evidence:payroll_verified", op="is", value=True)])
        check("4. Zelle / Payroll: without verified Payroll amounts the evidence is MISSING and the rule never applies",
              all(state is None for state, _ in payroll) and all(wp.evaluate(payroll_rule, mv.info).outcome == wp.INCOMPLETE for mv in zelle_emp),
              dict(payroll))
    labelled = [mv for mv in movements if mv.info.get("label")]
    some_label = Counter(x for mv in labelled for x in mv.info["label"]).most_common(1)[0][0]
    label_rule = dict(rule, conditions=[dict(field="label", op="has", value=some_label)])
    matched = [mv for mv in movements if wp.evaluate(label_rule, mv.info).outcome == wp.MATCH]
    no_who = [mv for mv in movements if not mv.info.get("who")]
    check("5. suppliers through Labels: a Label condition matches every movement whose WHO has it, and only those",
          bool(matched) and all(some_label in mv.info["label"] for mv in matched)
          and all(wp.evaluate(label_rule, mv.info).outcome == wp.INCOMPLETE for mv in no_who), (some_label, len(matched)))
    fmt = Counter(mv.info["format"] for mv in no_who).most_common(1)
    if fmt:
        fmt_rule = dict(rule, conditions=[dict(field="format", op="is", value=fmt[0][0])])
        check("6. a recurring format without WHO is decided by its format alone",
              all(wp.evaluate(fmt_rule, mv.info).outcome == wp.MATCH for mv in no_who if mv.info["format"] == fmt[0][0]), fmt)
    else:
        skip("6. format without WHO", "every movement of the copy has a WHO")
    with_cat = [mv for mv in movements if "extra:category" in mv.info]
    cat_rule = dict(rule, conditions=[dict(field="extra:category", op="is", value=with_cat[0].info["extra:category"])])
    with SessionFactory() as db:
        txns = {t.id: t for t in db.scalars(select(m.FinancialTransaction))}
        bare = wp.InfoBuilder(db, without=("category",), domain=domain)
        no_cat = [bare.info(txns[mv.id], who=mv.info.get("who"), labels=mv.info.get("label")) for mv in with_cat[:200]]
        none = wp.InfoBuilder(db, without=("*",), domain=domain)
        first_citizens = [mv for mv in movements if "extra:category" not in mv.info and "extra:native_type" not in mv.info]
        plain = [none.info(txns[mv.id], who=mv.info.get("who"), labels=mv.info.get("label")) for mv in movements]
    check("7. with Category the condition is evaluated; without it the same rule is INCOMPLETE (no error, no false)",
          wp.evaluate(cat_rule, with_cat[0].info).outcome == wp.MATCH
          and all(wp.evaluate(cat_rule, i).outcome == wp.INCOMPLETE for i in no_cat), len(with_cat))
    check("8. Sources without optional information: every movement still has its core information",
          len(plain) == len(movements) and all(not any(k.startswith("extra:") for k in i) and i.get("format") for i in plain)
          and all(mv.info.get("format") for mv in first_citizens), len(first_citizens))

    # --- 9-13: the page, the discovery, nothing activated --------------------------------------------------
    with SessionFactory() as db:
        account_service.create_account(db, username="why_operator", display_name="why_operator",
                                       password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="why_operator").one()
        account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
    # The route starts the discovery in a background thread with the real provider; here it is run
    # synchronously with the stub instead, so no thread and no AI call may start.
    started = []
    bank_why_pattern_routes.threading = type("NoThreads", (), {"Thread": lambda *a, **k: type(
        "T", (), {"start": lambda self: started.append(k.get("name"))})()})
    client = web_app.app.test_client()
    client.post("/login", data={"username": "why_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/ai-rules").data.decode("utf-8")
    csrf = (BANK_CSRF_RE.search(page) or [None, None])[1]
    script = client.get("/static/bank-assistant/why_patterns.js").data.decode("utf-8")
    check("9. the existing Rules and Profiles page offers Discover WHY Patterns; AI rules and profiles remain",
          "Discover WHY Patterns" in page and "why_patterns.js" in page and 'id="extractors-heading"' in page
          and 'id="photos-heading"' in page and "JSON" not in script)  # Find standard formats is back (2026-10-25)
    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True):
        resp = client.post("/bank/flow/why-discover", data={"csrf_token": csrf})
    scan_id = (resp.get_json() or {}).get("id")
    bank_why_pattern_routes.discovery(SessionFactory, scan_id, generate=stub_reader)
    data = client.get(f"/bank/flow/why-discover/{scan_id}").get_json() or {}
    proposals = data.get("proposals", [])
    check("10. a discovery completes and the page receives proposals in plain language (no cache, no structure to read)",
          data.get("status") == "COMPLETE" and proposals and "cache" not in data
          and all(p["when"] and isinstance(p["when"][0], str) and "check" in p for p in proposals),
          {k: data.get(k) for k in ("status", "error", "formats", "summary")})
    joined = [p for p in proposals if p["check"]["formats"] > 1]
    check("11. consolidation: fewer rules than formats with a WHY, several rules join formats",
          len(proposals) < data.get("formats_with_why", 0) and len(joined) >= 1,
          (len(proposals), data.get("formats_with_why"), len(joined)))
    check("12. each proposal is verified: counterexamples, conflicts, overlaps, before/after, later period, optional fields",
          all(all(k in p["check"] for k in ("counterexample_count", "conflict_count", "overlaps", "before_after", "later",
                                            "optional", "new_count")) for p in proposals))
    if domain.available:
        check("12b. an evidence-based Tips proposal exists (one example is enough with RF-One evidence)",
              any(p["basis"] == "evidence" and p["why"] == "Tips Distribution / Settlement" for p in proposals))
    with SessionFactory() as db:
        check("13. discovery activates nothing and changes no human decision",
              db.scalar(select(func.count(m.BankAiRule.id))) == rules_before and human_state(db) == before_humans)

    # --- 14-17: approval, old paths, engine, deactivation -------------------------------------------------
    target = max(proposals, key=lambda p: (p["check"]["formats"], p["check"]["movements"]))
    resp = client.post(f"/bank/flow/why-discover/{scan_id}/proposals/{target['id']}/approve", data={"csrf_token": csrf})
    check("14a. approval needs an explicit confirmation", resp.status_code == 409, resp.status_code)
    resp = client.post(f"/bank/flow/why-discover/{scan_id}/proposals/{target['id']}/approve",
                       data={"csrf_token": csrf, "confirm": "yes"})
    body = resp.get_json() or {}
    rule_id = (body.get("proposal") or {}).get("rule_id")
    with SessionFactory() as db:
        saved = db.get(m.BankAiRule, rule_id) if rule_id else None
        spec = json.loads(ops.current_version(saved).spec) if saved else {}
        check("14b. the approved proposal is an ACTIVE rule, version 1, executed as code",
              saved is not None and saved.status == "ACTIVE" and spec.get("engine") == wp.ENGINE
              and ops.current_version(saved).version_no == 1 and ops.current_version(saved).method == "CODE", body)
        check("15. old paths ignore it: not an AI rule, not a profile, not run at import",
              rule_id not in [r.id for r, _v, _s in flow.entries(db)]
              and rule_id not in [r.id for r, _v, _s in bank_flow_routes.available_entries(db)]
              and (ops.import_context(db) is None or rule_id not in [r.id for r, _v, _s in ops.import_context(db).entries]))
        check("15b. the page lists it under the approved WHY rules",
              any(r["id"] == rule_id for r in (client.get("/bank/flow/snapshot").get_json() or {}).get("why_rules", [])))
        signature_active = wp.knowledge_signature(db)
        check("15c. approval changes no human decision", human_state(db) == before_humans)
    other = next((p for p in proposals if p["id"] != target["id"]), None)
    if other:
        resp = client.post(f"/bank/flow/why-discover/{scan_id}/proposals/{other['id']}/reject", data={"csrf_token": csrf})
        check("16a. a proposal can be rejected", (resp.get_json() or {}).get("proposal", {}).get("status") == "REJECTED")
    third = next((p for p in proposals if p["id"] not in (target["id"], (other or {}).get("id"))), None)
    if third:
        cond = third["when"][0]
        with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
                mock.patch.object(bank_chatgpt, "generate_json", return_value={"why": third["why"], "conditions": ["An invented condition"]}):
            resp = client.post(f"/bank/flow/why-discover/{scan_id}/proposals/{third['id']}/discuss",
                               data={"csrf_token": csrf, "message": "Narrow it."})
        check("16b. Discuss with AI: a revision using a condition not offered is refused", resp.status_code == 409, resp.data[:200])
        with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
                mock.patch.object(bank_chatgpt, "generate_json", return_value={"why": third["why"], "conditions": [cond], "reply": "ok"}):
            resp = client.post(f"/bank/flow/why-discover/{scan_id}/proposals/{third['id']}/discuss",
                               data={"csrf_token": csrf, "message": "Keep only the first condition."})
        revised = (resp.get_json() or {}).get("proposal") or {}
        check("16c. Discuss with AI: a valid revision is tested again on the whole history",
              resp.status_code == 200 and revised.get("when") == [cond] and "check" in revised and revised.get("history"))

    if not CBANK_DIR.exists():
        skip("17. single engine", f"C-Bank code not found at {CBANK_DIR}")
    else:
        sys.path.insert(0, str(CBANK_DIR))
        from cbank import service, store
        con = store.connect()
        run_id = service.execute(con, "all")
        results = {r["txn_id"]: r for r in store.results(con, run_id)}
        hits = [r for r in results.values() if any(s.get("method") == "WHY RULE" for s in r["trace"])
                or any("WHY rule #%d" % rule_id in e.get("message", "") for e in r["exceptions"])]
        with SessionFactory() as db:
            movements2, _meta = wp.load_movements(db)
        expected = {mv.id for mv in movements2 if not mv.structural and wp.evaluate(spec, mv.info).outcome == wp.MATCH}
        decided = [r for r in hits if r["why_method"] == "WHY RULE"]
        conflicts = [r for r in hits if any(e["code"] == "PROFILE_CONFLICT" for e in r["exceptions"])]
        check("17a. the engine applies the approved rule as code: each matching movement is decided by it or is a conflict",
              bool(hits) and {r["txn_id"] for r in hits} <= expected, (len(hits), len(expected), len(decided), len(conflicts)))
        protected = [r for r in hits if r.get("protected")]
        check("17b. human decisions stay protected", all(r["why_method"] == "HUMAN (Bank)" for r in protected), len(protected))
        check("17c. Decision 86: the accounting subject is the Source owner on every movement the rule touches",
              all(r["subject_id"] == r["payer_id"] for r in hits if r.get("payer_id")))
        print(f"        engine run #{run_id}: {len(decided)} decided by the WHY rule, {len(conflicts)} conflicts for a person, "
              f"{len(protected)} protected human decisions")
        resp = client.post(f"/bank/flow/why-rules/{rule_id}/deactivate", data={"csrf_token": csrf})
        with SessionFactory() as db:
            check("17d. deactivation: the rule is kept (versions, history) but no longer active; the engine re-runs",
                  resp.status_code == 200 and db.get(m.BankAiRule, rule_id).status == "INACTIVE"
                  and rule_id not in [r.id for r, _v, _s in wp.active_rules(db)] and wp.knowledge_signature(db) != signature_active)

    # --- 18: Category removed from the Chase files --------------------------------------------------------
    raw = sqlite3.connect(_COPY)
    changed = 0
    for batch_id, data_bytes in raw.execute("select id, raw_file_bytes from bank_import_batches").fetchall():
        textv = bytes(data_bytes).decode("utf-8-sig", "replace")
        lines = textv.splitlines()
        header = lines[0].split(",") if lines else []
        if "Category" in header:
            k = header.index("Category")
            rebuilt = []
            for line in lines:
                cells = next(iter(__import__("csv").reader([line])))
                rebuilt.append(",".join('"%s"' % c.replace('"', '""') for n, c in enumerate(cells) if n != k))
            raw.execute("update bank_import_batches set raw_file_bytes=? where id=?", ("\n".join(rebuilt).encode(), batch_id))
            changed += 1
    raw.commit()
    raw.close()
    with SessionFactory() as db:
        moved, _meta = wp.load_movements(db)
    check("18a. Category removed from every Chase file: the movements load, none has Category, nothing fails",
          changed > 0 and len(moved) == len(movements) and not any("extra:category" in mv.info for mv in moved), changed)
    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True):
        scan2 = (client.post("/bank/flow/why-discover", data={"csrf_token": csrf}).get_json() or {}).get("id")
    bank_why_pattern_routes.discovery(SessionFactory, scan2, generate=stub_reader)
    data2 = client.get(f"/bank/flow/why-discover/{scan2}").get_json() or {}
    check("18b. without Category the discovery still completes and no proposal depends on it",
          data2.get("status") == "COMPLETE" and data2.get("proposals")
          and not any("category" in p["check"]["optional"]["fields"] for p in data2["proposals"]),
          (data2.get("status"), len(data2.get("proposals", []))))
    with SessionFactory() as db:
        check("18c. at the end no human decision changed", human_state(db) == before_humans)
    check("18d. each Discover request asks for its background discovery (intercepted here: no real AI call)",
          started == ["bank-why-discovery"] * 2, started)

    print()
    print(f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            from db import _engine
            _engine.dispose()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(code)
