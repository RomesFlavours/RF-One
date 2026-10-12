"""Bank > AI Rules — "Solo movimenti non ancora sistemati da regole AI" (BANK_AI_RULES_013).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rules.

* "settled by an AI rule" = the movement's CURRENT decision was written by an AI rule application (an UPDATED
  item with that decision) — recorded provenance, never deduced from a WHO / WHY; the AI rule is known;
* a preview, a movement already as the rule says (UNCHANGED), a decision changed afterwards by a person: NOT
  settled;
* the option is selected by default on the page; with it, Preview and Apply leave out the AI-settled movements and
  say how many (per rule); without it they are considered, and manual decisions stay PROTECTED;
* the option is part of what a preview authorizes: Apply with another choice is refused;
* the draft keeps the choice.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_only_unsettled_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-only-unsettled-secret"
os.environ.pop("RFONE_BANK_AI_MODE", None)
os.environ.pop("RFONE_BANK_CLAUDE_CODE_CLI", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rule_operations  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
WHY_NAME = None            # an active WHY of the catalog, set in main()
RULE_ONE = RULE_TWO = None


def spec(name, replace):
    return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "ACME"}],
            "who": {"mode": "fixed", "name": name}, "why": {"mode": "fixed", "name": WHY_NAME}, "for_whom": None,
            "status": None,
            "only_if_who_differs": False, "replace_existing": replace, "branches": [], "unsupported": [],
            "coverage": [{"instruction": "contiene ACME → WHO", "represented_by": "condition + who.fixed"}]}


def main() -> int:
    global WHY_NAME, RULE_ONE, RULE_TWO
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_ou", display_name="AI OU", password="AiOuPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_ou").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF OU, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="OU Checking", institution="CHASE", last_four="7001",
                                       currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        why = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                        .order_by(m.BankTransactionReason.id)).first()
        WHY_NAME = why.name
        RULE_ONE = f"Se la descrizione contiene “ACME”, assegna WHO “ACME ONE” e WHY “{WHY_NAME}”."
        RULE_TWO = (f"Se la descrizione contiene “ACME”, assegna WHO “ACME TWO” e WHY “{WHY_NAME}”, sostituendo "
                    "quelli decisi da altre regole.")
        for name in ("ACME ONE", "ACME TWO", "PUBLIX"):
            s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE"))
        s.flush()
        ids = {}
        for i, key in enumerate(("settled", "manual", "changed", "fresh", "same"), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=f"ACME INVOICE {i}",
                description_normalized=f"ACME INVOICE {i}", amount_minor=-1000 - i, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"ou-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        publix = s.scalar(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "PUBLIX"))
        acme_one = s.scalar(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "ACME ONE"))
        recognition._create_decision_row(s, s.get(m.FinancialTransaction, ids["manual"]), occurrence_id=publix,
                                         transaction_reason_id=None, recognition_rule_id=None, decision_source="HUMAN",
                                         decision_status="HUMAN_CONFIRMED", confidence=None, explanation_notes="manual")
        recognition._create_decision_row(s, s.get(m.FinancialTransaction, ids["same"]), occurrence_id=acme_one,
                                         transaction_reason_id=why.id, recognition_rule_id=None, decision_source="RULE",
                                         decision_status="AUTO_APPLIED", confidence=None, explanation_notes="earlier")
        s.commit()

    def stand_in(prompt):
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        return spec("ACME ONE", False) if rule == RULE_ONE else spec("ACME TWO", True)

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_ou", "password": "AiOuPass123!", "csrf_token": csrf})
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    check("1. the page offers the option, selected by default",
          '<input type="checkbox" name="only_unsettled" id="ai-rule-only-unsettled" checked>' in page)

    def preview(rule, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids["settled"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30", "scope_all": "on"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    def save_and_apply(rule, preview_data, **options):
        with SessionFactory() as s:
            saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=rule, create_missing_who=False,
                                                 apply_future=False, origin_transaction_id=ids["settled"],
                                                 account_id=None, generate=stand_in)
            s.commit()
            rule_obj = s.get(m.BankAiRule, saved.rule.id)
            application = ai_rule_operations.apply_rule(s, rule=rule_obj, scope=options.pop("scope", "ALL"),
                                                        selected_ids=options.pop("selected", None),
                                                        preview_id=preview_data["preview_id"], account_id=None,
                                                        **options)
            s.commit()
            return saved.rule.id, ai_rule_operations.application_as_dict(application)

    # ---------------------------------------- rule one, applied to ONE movement only
    with SessionFactory() as s:
        before = ai_rules.ai_settled(s)
    p1 = preview(RULE_ONE, scope_all="", scope_selected="on", selected_ids=f"{ids['settled']},{ids['same']}")
    with SessionFactory() as s:
        after_preview = ai_rules.ai_settled(s)
    check("2. a preview settles nothing", before == {} and after_preview == {} and p1.get("ok"))
    rule_one, a1 = save_and_apply(RULE_ONE, p1, scope="SELECTED", selected=[ids["settled"], ids["same"]])
    with SessionFactory() as s:
        settled = ai_rules.ai_settled(s)
    check("3. after the application is saved, the movement is settled — by THAT AI rule",
          settled == {ids["settled"]: rule_one} and a1["updated"] == 1 and a1["unchanged"] == 1, detail=str(settled))

    # ---------------------------------------- a person changes a movement the AI rule wrote
    p1b = preview(RULE_ONE, scope_all="", scope_selected="on", selected_ids=str(ids["changed"]))
    with SessionFactory() as s:
        rule_obj = s.get(m.BankAiRule, rule_one)
        ai_rule_operations.apply_rule(s, rule=rule_obj, scope="SELECTED", selected_ids=[ids["changed"]],
                                      preview_id=p1b["preview_id"], account_id=None)
        s.commit()
        settled_mid = ai_rules.ai_settled(s)
        publix = s.scalar(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "PUBLIX"))
        recognition._create_decision_row(s, s.get(m.FinancialTransaction, ids["changed"]), occurrence_id=publix,
                                         transaction_reason_id=None, recognition_rule_id=None, decision_source="HUMAN",
                                         decision_status="HUMAN_CONFIRMED", confidence=None, explanation_notes="fixed")
        s.commit()
        settled = ai_rules.ai_settled(s)
    check("4. a decision changed afterwards by a person is no longer settled by the AI rule",
          ids["changed"] in settled_mid and ids["changed"] not in settled)
    check("5. an UNCHANGED movement (already as the rule said) and one never applied are not settled",
          ids["same"] not in settled and ids["fresh"] not in settled)

    # ---------------------------------------- rule two: option ON vs OFF
    with SessionFactory() as s:                 # two active rules would be in CONFLICT on every ACME movement
        ai_rule_operations.set_status(s, rule_id=rule_one, active=False)
        s.commit()
    on = preview(RULE_TWO, only_unsettled="on")
    off = preview(RULE_TWO)
    on_ids = {i["id"]: i for i in on.get("match_items", [])}
    off_ids = {i["id"]: i for i in off.get("match_items", [])}
    check("6. option ON: the AI-settled movement is left out and counted, per rule",
          on.get("only_unsettled") and on.get("excluded_ai_settled") == 1
          and on.get("excluded_by_rule") == {str(rule_one): 1} and ids["settled"] not in on_ids
          and on.get("examined") == 4, detail=str({k: on.get(k) for k in ("examined", "excluded_ai_settled",
                                                                          "excluded_by_rule")}))
    check("7. option OFF: it is considered (and replaced: the rule replaces other rules' values); the manual "
          "decision stays PROTECTED either way",
          not off.get("only_unsettled") and off.get("excluded_ai_settled") == 0 and off.get("examined") == 5
          and off_ids[ids["settled"]]["plan"] == "UPDATED" and off_ids[ids["manual"]]["plan"] == "PROTECTED"
          and on_ids[ids["manual"]]["plan"] == "PROTECTED")
    check("8. the two previews authorize different things (different keys)", on["scope_key"] != off["scope_key"])

    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE_TWO, create_missing_who=False,
                                             apply_future=False, origin_transaction_id=ids["settled"],
                                             account_id=None, generate=stand_in)
        s.commit()
        rule_two = saved.rule.id
        try:
            ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, rule_two), scope="ALL", selected_ids=None,
                                          preview_id=off["preview_id"], account_id=None, only_unsettled=True)
            refused = None
        except ai_rule_operations.NeedsPreview as exc:
            refused = str(exc)
        s.rollback()
    check("9. Apply with the option ON on a preview made with it OFF is refused, saying why",
          refused is not None and "Solo movimenti non ancora sistemati" in refused, detail=str(refused))
    on_rule = preview(RULE_TWO, only_unsettled="on", rule_id=str(rule_two))
    with SessionFactory() as s:
        application = ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, rule_two), scope="ALL",
                                                    selected_ids=None, preview_id=on_rule["preview_id"],
                                                    account_id=None, only_unsettled=True)
        s.commit()
        a2 = ai_rule_operations.application_as_dict(application)
        settled = ai_rules.ai_settled(s)
        who_settled = recognition.get_current_explanation(s, financial_transaction_id=ids["settled"]).occurrence_id
        acme_one = s.scalar(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "ACME ONE"))
    check("10. Apply with the option: the AI-settled movement untouched, the count recorded on the application",
          a2["only_unsettled"] and a2["excluded_ai_settled"] == 1 and who_settled == acme_one
          and settled.get(ids["settled"]) == rule_one, detail=str(a2))
    check("11. the movements the second rule saved are now settled by IT; the manual one by none",
          settled.get(ids["fresh"]) == rule_two and settled.get(ids["same"]) == rule_two
          and ids["manual"] not in settled and ids["changed"] not in settled, detail=str(settled))

    # ---------------------------------------- the draft keeps the choice
    draft = client.post("/bank/ai-rules/drafts", data={"csrf_token": csrf, "rule_text": RULE_TWO,
                                                       "origin_transaction_id": str(ids["fresh"])},
                        headers={"X-Requested-With": "fetch"}).get_json()
    reopened = client.get(f"/bank/ai-rules/drafts/{draft['draft_id']}").get_json()
    draft_on = client.post("/bank/ai-rules/drafts", data={"csrf_token": csrf, "rule_text": RULE_TWO,
                                                          "origin_transaction_id": str(ids["fresh"]),
                                                          "only_unsettled": "on"},
                           headers={"X-Requested-With": "fetch"}).get_json()
    reopened_on = client.get(f"/bank/ai-rules/drafts/{draft_on['draft_id']}").get_json()
    check("12. a draft keeps the choice (off and on)",
          reopened.get("only_unsettled") is False and reopened_on.get("only_unsettled") is True)

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
