"""Bank > AI Rules — the "Solo WHO" run mode (BANK_AI_RULES_018).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rules.

* "Solo WHO" executes only the WHO part: the rule's fixed WHY, the WHO's default WHY and For Whom are NOT applied;
  the rule itself (text, interpretation, versions) is unchanged;
* conflicts are about the WHO only: two rules agreeing on the WHO but not on WHY / For Whom are no conflict; a
  different WHO still is;
* a rule that names no WHO for a movement contributes nothing;
* "Crea WHO mancanti" is respected (created with it, UNRESOLVED without);
* the mode is part of what a preview authorizes (apply with another mode is refused) and is recorded on the
  preview and on the application;
* the page offers the mode, off by default.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_who_only_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-who-only-secret"
os.environ.pop("RFONE_BANK_AI_MODE", None)
os.environ.pop("RFONE_BANK_CLAUDE_CODE_CLI", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rule_operations  # noqa: E402
from rfone_data_store.bank_reconciliation import economic_allocation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation.ai_rules import AiRuleError  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULES = {}          # text -> spec, set in main()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_wo", display_name="AI WO", password="AiWoPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_wo").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF WO, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        entity = m.ReportingEntity(code="RE_WO", name="RFWO", entity_type="VIRTUAL", status="ACTIVE")
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="WO Checking",
                                   institution="CHASE", last_four="9201", currency="USD")
        s.add_all([entity, card])
        s.flush()
        whys = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                         .order_by(m.BankTransactionReason.id)).all()
        why_a, why_b = whys[0], whys[1]
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        s.add(m.BankOccurrence(canonical_name="ACME", occurrence_type_id=counterparty.id, status="ACTIVE",
                               default_transaction_reason_id=why_a.id))
        ids = {}
        for i, (key, text) in enumerate((("acme", "PAY TO ACME REF 1"), ("newco", "PAY TO NEWCO REF 2"),
                                         ("other", "SOMETHING ELSE")), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"wo-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        s.commit()
        why_a_name, why_b_name, entity_id = why_a.name, why_b.name, entity.id

    cov = [{"instruction": "the whole rule", "represented_by": "conditions + assignments"}]
    between = {"mode": "between", "start": "PAY TO", "end": "REF", "start_at": "beginning", "end_case": "ignore"}
    RULE_FULL = (f"Se la descrizione comincia con “PAY TO”, il WHO è il testo tra “PAY TO” e “REF”; WHY “{why_b_name}”; "
                 "For Whom = RFWO.")
    RULE_SAME_WHO = f"Se la descrizione contiene “ACME”, il WHO è “ACME” e il WHY è “{why_a_name}”."
    RULE_WHY_ONLY = f"Se la descrizione contiene “SOMETHING”, il WHY è “{why_a_name}”."
    RULES[RULE_FULL] = {"kind": "STRUCTURED", "conditions": [], "who": between, "why": {"mode": "fixed", "name": why_b_name},
                        "for_whom": {"mode": "fixed", "entity": "RFWO"}, "status": None, "only_if_who_differs": False,
                        "replace_existing": False, "branches": [], "unsupported": [], "coverage": cov}
    RULES[RULE_SAME_WHO] = {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "ACME"}],
                            "who": {"mode": "fixed", "name": "ACME"}, "why": {"mode": "fixed", "name": why_a_name},
                            "for_whom": None, "status": None, "only_if_who_differs": False, "replace_existing": False,
                            "branches": [], "unsupported": [], "coverage": cov}
    RULES[RULE_WHY_ONLY] = {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "SOMETHING"}],
                            "who": None, "why": {"mode": "fixed", "name": why_a_name}, "for_whom": None, "status": None,
                            "only_if_who_differs": False, "replace_existing": False, "branches": [], "unsupported": [],
                            "coverage": cov}

    def stand_in(prompt):
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        return RULES[rule]

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_wo", "password": "AiWoPass123!", "csrf_token": csrf})
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    check("1. the page offers “Solo WHO”, off by default",
          '<input type="checkbox" name="who_only" id="ai-rule-who-only">' in page)

    def save(rule, create):
        with SessionFactory() as s:
            saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=rule, create_missing_who=create,
                                                 apply_future=False, origin_transaction_id=ids["acme"],
                                                 account_id=None, generate=stand_in)
            s.commit()
            return saved.rule.id

    def preview(rule, rule_id, create, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids["acme"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30", "scope_all": "on", "rule_id": str(rule_id)}
        if create:
            data["create_missing_who"] = "on"
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    full_id = save(RULE_FULL, True)
    same_id = save(RULE_SAME_WHO, False)
    why_only_id = save(RULE_WHY_ONLY, False)

    normal = preview(RULE_FULL, full_id, True)
    normal_items = {i["id"]: i for i in normal.get("match_items", [])}
    check("2. normal mode: the WHY of the two rules differs on ACME → CONFLICT (as before)",
          normal_items[ids["acme"]]["plan"] == "CONFLICT", detail=normal_items[ids["acme"]]["plan_note"])
    wo = preview(RULE_FULL, full_id, True, who_only="on")
    wo_items = {i["id"]: i for i in wo.get("match_items", [])}
    check("3. “Solo WHO”: same WHO, different WHY → no conflict; only the WHO is proposed (no WHY, no For Whom)",
          bool(wo.get("who_only")) and wo_items[ids["acme"]]["plan"] == "UPDATED"
          and not wo_items[ids["acme"]]["proposed_why"] and not wo_items[ids["acme"]].get("proposed_for_whom"),
          detail=str(wo_items[ids["acme"]]))
    check("4. the mode is said in the interpretation", any(x.startswith("MODE “Solo WHO”")
                                                            for x in wo.get("interpretation_lines") or []))
    with SessionFactory() as s:
        try:
            ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, full_id), scope="ALL", selected_ids=None,
                                          preview_id=normal["preview_id"], account_id=None, who_only=True)
            refused = None
        except ai_rule_operations.NeedsPreview as exc:
            refused = str(exc)
        s.rollback()
    check("5. applying “Solo WHO” on a preview made without it is refused, saying why",
          refused is not None and "Solo WHO" in refused, detail=str(refused))

    with SessionFactory() as s:
        application = ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, full_id), scope="ALL",
                                                    selected_ids=None, preview_id=wo["preview_id"], account_id=None,
                                                    who_only=True)
        s.commit()
        a = ai_rule_operations.application_as_dict(application)
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        names = {o.id: o.canonical_name for o in s.scalars(select(m.BankOccurrence))}
        allocations = s.scalar(select(func.count(m.BankTransactionAllocation.id)))
        rule_text_now = ai_rule_operations.current_version(s.get(m.BankAiRule, full_id)).rule_text
    check("6. applied “Solo WHO”: WHO assigned (ACME existing, NEWCO created), NO WHY, NO For Whom",
          names[current["acme"].occurrence_id] == "ACME" and names[current["newco"].occurrence_id] == "NEWCO"
          and current["acme"].transaction_reason_id is None and current["newco"].transaction_reason_id is None
          and allocations == 0 and a["who_only"], detail=str(a))
    check("7. the rule is unchanged (its WHY / For Whom instructions kept for later)", rule_text_now == RULE_FULL)

    # a different WHO is still a conflict in "Solo WHO"
    RULE_OTHER_WHO = "Se la descrizione contiene “NEWCO”, il WHO è “NEWCO GROUP”."
    RULES[RULE_OTHER_WHO] = {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "NEWCO"}],
                             "who": {"mode": "fixed", "name": "NEWCO GROUP"}, "why": None, "for_whom": None,
                             "status": None, "only_if_who_differs": False, "replace_existing": True, "branches": [],
                             "unsupported": [], "coverage": cov}
    other_id = save(RULE_OTHER_WHO, True)
    conflict = {i["id"]: i for i in preview(RULE_OTHER_WHO, other_id, True, who_only="on").get("match_items", [])}
    check("8. “Solo WHO”: a different WHO from another active rule is still a CONFLICT",
          conflict[ids["newco"]]["plan"] == "CONFLICT" and "assigns WHO" in conflict[ids["newco"]]["plan_note"],
          detail=conflict[ids["newco"]]["plan_note"])
    why_only = preview(RULE_WHY_ONLY, why_only_id, False, who_only="on")
    check("9. a rule that names no WHO contributes nothing in “Solo WHO” (no match)",
          why_only.get("ok") and not why_only.get("match_items"), detail=str(why_only.get("matches")))
    no_create = preview(RULE_OTHER_WHO, other_id, False, who_only="on")
    nc = {i["id"]: i for i in no_create.get("match_items", [])}
    check("10. without “Crea WHO mancanti” a missing WHO is not created (UNRESOLVED or conflict, never applied)",
          nc[ids["newco"]]["plan"] in ("UNRESOLVED", "CONFLICT"), detail=nc[ids["newco"]]["plan_note"])
    _ = (AiRuleError, economic_allocation, entity_id)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
