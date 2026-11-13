"""Bank > AI Rules — Open and Delete of an operative rule (BANK_AI_RULES_014).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rule.

* Open: the rule's JSON (text, options, origin) for the window; a rule that no longer exists says so (JSON 404);
* Delete: CSRF required; the rule leaves the page and is never executed again — not by Preview's other-rule
  checks, Apply or the import; it cannot be reactivated or saved; a draft of a change to it becomes a draft of a new
  rule;
* the classifications it applied are NOT changed (decisions and allocations identical) and their provenance stays
  (the application items, the "settled by AI rule #N" provenance, the decisions' notes).

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_delete_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-delete-secret"
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
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation.ai_rules import AiRuleError  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = None                # with an active WHY of the catalog, set in main()
SPEC = {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "ACME"}],
        "who": {"mode": "fixed", "name": "ACME SUPPLY"}, "why": None, "for_whom": None, "status": None,
        "only_if_who_differs": False, "replace_existing": False, "branches": [], "unsupported": [],
        "coverage": [{"instruction": "contiene ACME → WHO ACME SUPPLY", "represented_by": "condition + who.fixed"}]}


def main() -> int:
    global RULE
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_del", display_name="AI DEL", password="AiDelPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_del").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF DEL, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="DEL Checking", institution="CHASE", last_four="8001",
                                       currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        why = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                        .order_by(m.BankTransactionReason.id)).first()
        RULE = f"Se la descrizione contiene “ACME”, assegna WHO “ACME SUPPLY” e WHY “{why.name}”."
        SPEC["why"] = {"mode": "fixed", "name": why.name}
        s.add(m.BankOccurrence(canonical_name="ACME SUPPLY", occurrence_type_id=counterparty.id, status="ACTIVE"))
        ids = []
        for i in range(1, 3):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=f"ACME INVOICE {i}",
                description_normalized=f"ACME INVOICE {i}", amount_minor=-1000 - i, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"del-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        s.commit()

    ai_client.generate_json = lambda prompt: SPEC
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_del", "password": "AiDelPass123!", "csrf_token": csrf})
    page_url = "/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30"
    csrf = CSRF_RE.search(client.get(page_url).data.decode()).group(1)

    preview = client.post("/bank/ai-rules/preview", data={
        "csrf_token": csrf, "rule_text": RULE, "origin_transaction_id": str(ids[0]), "date_from": "2026-09-01",
        "date_to": "2026-09-30", "scope_all": "on"}, headers={"X-Requested-With": "fetch"}).get_json()
    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=False,
                                             apply_future=True, origin_transaction_id=ids[0], account_id=None)
        s.commit()
        rule_id = saved.rule.id
        ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, rule_id), scope="ALL", selected_ids=None,
                                      preview_id=preview["preview_id"], account_id=None)
        s.commit()
        draft = ai_rules.save_draft(s, draft_id=None, rule_text=RULE + " (modifica)", origin_transaction_id=ids[0],
                                    account_id=None, ai_rule_id=rule_id)
        s.commit()
        draft_id = draft.id

    def snapshot():
        with SessionFactory() as s:
            decisions = [s.get(m.FinancialTransaction, i).explanation_id for i in ids]
            explanations = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
            allocations = s.scalar(select(func.count(m.BankTransactionAllocation.id)))
            items = s.scalar(select(func.count(m.BankAiRuleApplicationItem.id)))
            settled = ai_rules.ai_settled(s)
            notes = [s.get(m.BankTransactionExplanation, d).explanation_notes for d in decisions]
            return decisions, explanations, allocations, items, settled, notes

    opened = client.get(f"/bank/ai-rules/rules/{rule_id}").get_json()
    check("1. Open: the rule's text, version and origin for the window", opened.get("ok")
          and opened.get("rule_text") == RULE and opened.get("version_no") == 1 and opened["origin"]["id"] == ids[0])
    before = snapshot()
    check("2. setup: the rule classified both movements (settled by it)",
          before[4] == {ids[0]: rule_id, ids[1]: rule_id}, detail=str(before[4]))

    no_csrf = client.post(f"/bank/ai-rules/rules/{rule_id}/delete", data={})
    with SessionFactory() as s:
        still = s.get(m.BankAiRule, rule_id).deleted_at is None
    check("3. Delete needs the CSRF token", still and no_csrf.status_code in (400, 403))

    done = client.post(f"/bank/ai-rules/rules/{rule_id}/delete", data={"csrf_token": csrf, "date_from": "2026-09-01",
                                                                       "date_to": "2026-09-30"})
    page = client.get(page_url).data.decode()
    check("4. Delete: back to the page, which says so; the rule is no longer listed",
          done.status_code == 302 and f"AI rule #{rule_id} deleted" in page
          and f'data-rule-id="{rule_id}"' not in page, detail=str(done.status_code))
    after = snapshot()
    check("5. NOTHING on movements changed: same decisions, no decision or allocation added or removed",
          after[:3] == before[:3], detail=f"{before[:3]} → {after[:3]}")
    check("6. the provenance stays: application items, 'settled by AI rule #N', the decisions' notes",
          after[3] == before[3] and after[4] == before[4] and after[5] == before[5]
          and all((n or "").startswith(f"AI Rule #{rule_id} ") for n in after[5]))
    gone = client.get(f"/bank/ai-rules/rules/{rule_id}")
    check("7. Open of a deleted rule says it no longer exists (JSON, not a blank failure)",
          gone.status_code == 404 and "no longer exists" in (gone.get_json() or {}).get("error", ""))
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        executed = ([r for r, _ in ai_rules._active_rule_specs(s)], ai_rule_operations.import_context(s))
        refusals = []
        for attempt in (
                lambda: ai_rule_operations.apply_rule(s, rule=rule, scope="ALL", selected_ids=None,
                                                      preview_id=preview["preview_id"], account_id=None),
                lambda: ai_rule_operations.set_status(s, rule_id=rule_id, active=True),
                lambda: ai_rule_operations.save_rule(s, rule_id=rule_id, rule_text=RULE, create_missing_who=False,
                                                     apply_future=False, origin_transaction_id=ids[0], account_id=None)):
            try:
                attempt()
                refusals.append(False)
            except AiRuleError:
                refusals.append(True)
        s.rollback()
        draft_after = s.get(m.BankAiRuleDraft, draft_id)
        state = (rule.status, rule.apply_future, rule.deleted_at is not None, len(rule.versions))
    check("8. never executed again: not among the active rules, not at import, Apply refused",
          rule_id not in executed[0] and executed[1] is None and refusals[0], detail=str(executed))
    check("9. it cannot be reactivated or saved; its versions are kept",
          refusals[1] and refusals[2] and state == ("INACTIVE", False, True, 1), detail=str(state))
    check("10. a draft of a change to it becomes a draft of a new rule", draft_after.ai_rule_id is None)
    again = client.post(f"/bank/ai-rules/rules/{rule_id}/delete", data={"csrf_token": csrf})
    check("11. deleting it again: says it no longer exists, nothing else happens",
          again.status_code == 302 and "no longer exists" in client.get(page_url).data.decode())

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
