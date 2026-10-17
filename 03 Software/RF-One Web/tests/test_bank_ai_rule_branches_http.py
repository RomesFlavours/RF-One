"""Bank > AI Rules — "Personal" and if / otherwise branches (BANK_AI_RULES_007).

On a throwaway database, over HTTP. The AI provider is replaced INSIDE THIS
TEST ONLY by a stand-in that interprets the rules; the application itself
never simulates an answer.

* "Personal" is the Source's Personal classification in Bank — the owner
  recorded on the Source, for a card the owner of the account it settles to
  on the date — three-valued: Personal / not Personal / missing. A missing
  classification is never "not Personal": the case is "Da verificare";
* "carta Personal" = a card AND classified Personal;
* a rule with branches (PRATO): WHO for every match, WHY by branch — Personal
  card → Owner Personal — Food, not Personal → Marketing / Advertising,
  classification missing → WHY "Da verificare", never the not-Personal WHY;
  no branch → WHY unchanged; interpreted once, executed by code, reused;
* the window shows each branch's conditions and assignments, and the data checked;
* a part the engine cannot express is declared, never dropped; a saved v1
  structure that read Personal as "owner is a Person" is never executed;
* BONNE VIE SALON and Zelle/JPM keep working.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_branches_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-branches-secret"

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
from rfone_data_store.bank_reconciliation import card_configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PRATO = ("Se la descrizione contiene “Prato Winter Park”, senza distinzione tra maiuscole e minuscole: assegna WHO "
         "“PRATO”; se la Source è una carta Personal, assegna WHY “Owner Personal — Food”; se la Source è classificata "
         "come non Personal, assegna WHY “Marketing / Advertising”; se la classificazione manca o è incerta, segnala il "
         "WHY come “Da verificare”. Se la descrizione non contiene “Prato Winter Park”, la regola non si applica.")
PUBLIX_PERSONAL = "Se la descrizione contiene “PUBLIX” e la carta è Personal, assegna WHO \"PUBLIX\" e WHY \"Owner Personal — Food\"."
PUBLIX_NOT = "Se la descrizione contiene “PUBLIX” e la Source non è Personal, assegna WHO \"PUBLIX\"."
SALON = "Se la descrizione contiene “bonne vie salon”, assegna WHO \"BONNE VIE SALON\" e WHY \"Owner Personal — Other\"."
ZELLE = ("Se la descrizione comincia con “Zelle payment to” e contiene “JPM”, il WHO è il testo tra “Zelle payment to” "
         "e “JPM”. Non modificare il WHY.")
UNSUPPORTED = "Se la descrizione contiene “PUBLIX” e l’importo supera 100 dollari, assegna WHO \"PUBLIX\"."


def interpretation(rule: str) -> dict:
    contains = lambda text: {"field": "description", "op": "contains", "value": text}  # noqa: E731
    if rule == PRATO:
        return {"kind": "STRUCTURED", "conditions": [contains("Prato Winter Park")],
                "who": {"mode": "fixed", "name": "PRATO"}, "why": None,
                "branches": [
                    {"conditions": [{"field": "source_type", "op": "is", "value": "card"},
                                    {"field": "source_class", "op": "is", "value": "Personal"}],
                     "why": {"mode": "fixed", "name": "Owner Personal — Food"}},
                    {"conditions": [{"field": "source_class", "op": "is", "value": "not Personal"}],
                     "why": {"mode": "fixed", "name": "Marketing / Advertising"}},
                    {"conditions": [{"field": "source_class", "op": "is", "value": "missing"}],
                     "why": {"mode": "to_verify"}}]}
    if rule == PUBLIX_PERSONAL:
        return {"kind": "STRUCTURED", "conditions": [contains("PUBLIX"), {"field": "source_type", "op": "is", "value": "card"},
                                                     {"field": "source_class", "op": "is", "value": "Personal"}],
                "who": {"mode": "fixed", "name": "PUBLIX"}, "why": {"mode": "fixed", "name": "Owner Personal — Food"}}
    if rule == PUBLIX_NOT:
        return {"kind": "STRUCTURED", "conditions": [contains("PUBLIX"),
                                                     {"field": "source_class", "op": "is", "value": "not Personal"}],
                "who": {"mode": "fixed", "name": "PUBLIX"}, "why": None}
    if rule == SALON:
        return {"kind": "STRUCTURED", "conditions": [contains("bonne vie salon")],
                "who": {"mode": "fixed", "name": "BONNE VIE SALON"}, "why": {"mode": "fixed", "name": "Owner Personal — Other"}}
    if rule == ZELLE:
        return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "starts_with", "value": "Zelle payment to"}],
                "who": {"mode": "between", "start": "Zelle payment to", "end": "JPM"}, "why": None}
    return {"kind": "OTHER", "reason": "the amount condition (“importo supera 100 dollari”) cannot be expressed"}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_branches", display_name="AI Branches",
                                       password="AiBranches123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_branches").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Branch, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        owners = m.ReportingEntity(code="RE_OWN", name="Owners - Personal", entity_type="PERSONAL", status="ACTIVE")
        s.add(owners)
        s.flush()

        def instrument(name, kind, *, legal=None, person=None, last="0000"):
            i = m.PaymentInstrument(legal_entity_id=legal, owner_reporting_entity_id=person, instrument_type=kind,
                                    display_name=name, institution="CHASE", last_four=last, currency="USD")
            s.add(i)
            s.flush()
            return i

        personal_account = instrument("Owner Checking", "BANK_ACCOUNT", person=owners.id, last="1001")
        company_account = instrument("Company Checking", "BANK_ACCOUNT", legal=llc.id, last="1002")
        personal_card = instrument("Personal Card", "CREDIT_CARD", last="2001")
        company_card = instrument("Company Card", "CREDIT_CARD", last="2002")
        orphan_card = instrument("Card Without Settlement", "CREDIT_CARD", last="2003")
        card_configuration.assign_settlement_account(
            s, credit_card_payment_instrument_id=personal_card.id, settlement_bank_account_id=personal_account.id,
            valid_from=date(2026, 1, 1))
        card_configuration.assign_settlement_account(
            s, credit_card_payment_instrument_id=company_card.id, settlement_bank_account_id=company_account.id,
            valid_from=date(2026, 1, 1))
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        for name in ("PUBLIX", "BONNE VIE SALON", "PRATO"):
            s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE"))
        s.flush()
        seq = [0]

        def tx(inst, day, description, amount=-2000):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=inst.id, bank_source="CHASE_CARD", posting_date=day, transaction_date=day,
                description_original=description, description_normalized=description, amount_minor=amount,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"branch-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        t = {
            "prato_personal_card": tx(personal_card, date(2026, 9, 2), "TST*PRATO WINTER PARK"),
            "prato_company_card": tx(company_card, date(2026, 9, 3), "tst*prato winter park"),
            "prato_missing": tx(orphan_card, date(2026, 9, 4), "TST*PRATO WINTER PARK"),
            "prato_personal_account": tx(personal_account, date(2026, 9, 5), "PRATO WINTER PARK TRANSFER"),
            "publix_personal_card": tx(personal_card, date(2026, 9, 6), "PUBLIX #1488"),
            "publix_company_card": tx(company_card, date(2026, 9, 7), "PUBLIX #1661"),
            "publix_missing": tx(orphan_card, date(2026, 9, 8), "PUBLIX #2000"),
            "salon": tx(personal_card, date(2026, 9, 9), "BONNE VIE SALON"),
            "zelle": tx(company_account, date(2026, 9, 10), "Zelle payment to Giovanna Wine Rep JPM99cy6r3de"),
            "other": tx(company_account, date(2026, 9, 11), "OTHER VENDOR"),
        }
        s.commit()
        ids = {k: v.id for k, v in t.items()}
        whys = {r.name: r.id for r in s.scalars(select(m.BankTransactionReason))}
        prato_id = s.scalars(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "PRATO")).one()

    calls = {"n": 0}

    def stand_in(prompt: str) -> dict:
        calls["n"] += 1
        if "Translate the rule into conditions" in prompt:
            rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
            # structured-v3 (BANK_AI_RULES_008): every interpretation accounts for the rule's instructions.
            return {"coverage": [{"instruction": rule, "represented_by": "conditions, branches, WHO and WHY"}],
                    **interpretation(rule)}
        return {"items": []}

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_branches", "password": "AiBranches123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def preview(rule, origin, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids[origin]),
                "date_from": "2026-09-01", "date_to": "2026-09-30"}
        data.update(extra)
        response = client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"})
        return response.get_json()

    def by_id(p):
        return {i["id"]: i for i in p["match_items"] + p["doubt_items"]}

    # ---------------------------------------------------------------- Personal
    with SessionFactory() as s:
        rows = {r.id: r for r in ai_rules.period_rows(s, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))}
        classes = {k: (rows[ids[k]].source_class, rows[ids[k]].source_class_basis) for k in
                   ("prato_personal_card", "prato_company_card", "prato_missing", "prato_personal_account")}
    check("1. Personal is the Source's recorded owner (for a card: via its settlement account), three-valued",
          classes["prato_personal_card"][0] == "PERSONAL" and "via settlement account Owner Checking" in classes["prato_personal_card"][1]
          and classes["prato_company_card"][0] == "NOT_PERSONAL" and classes["prato_missing"][0] is None
          and "no settlement account" in classes["prato_missing"][1] and classes["prato_personal_account"][0] == "PERSONAL",
          detail=str(classes))

    calls["n"] = 0
    p = preview(PUBLIX_PERSONAL, "publix_personal_card")
    items = by_id(p)
    check("2. PUBLIX “carta Personal”: the Personal card matches, the company card does not, the card without a "
          "classification is Da verificare (a doubt), executed by code",
          p["method"] == "CODE" and set(i["id"] for i in p["match_items"]) == {ids["publix_personal_card"]}
          and ids["publix_company_card"] not in items and items[ids["publix_missing"]]["why_to_verify"]
          and items[ids["publix_missing"]] in p["doubt_items"] and "To verify" in items[ids["publix_missing"]]["reason"],
          detail=str({k: v.get("plan_note") for k, v in items.items()}))
    p = preview(PUBLIX_NOT, "publix_company_card")
    items = by_id(p)
    check("3. PUBLIX “Source non Personal”: only the company card; a missing classification is NOT “not Personal”",
          set(i["id"] for i in p["match_items"]) == {ids["publix_company_card"]}
          and items[ids["publix_missing"]] in p["doubt_items"], detail=str(list(items)))

    # ---------------------------------------------------------------- PRATO
    calls["n"] = 0
    p = preview(PRATO, "prato_personal_card")
    items = by_id(p)
    check("4. PRATO is interpreted ONCE and executed by code on every movement",
          p["ok"] and p["method"] == "CODE" and p["ai_calls"] == 1 and calls["n"] == 1, detail=str(p.get("error")))
    pc, cc, ms, pa = (items[ids[k]] for k in ("prato_personal_card", "prato_company_card", "prato_missing",
                                                "prato_personal_account"))
    check("5. Personal card → WHO PRATO, WHY Owner Personal — Food (branch 1)",
          pc["proposed_who"] == "PRATO" and pc["proposed_why"] == "Owner Personal — Food" and "branch 1" in pc["reason"])
    check("5b. not Personal (company card, lower case description) → WHY Marketing / Advertising (branch 2)",
          cc["proposed_who"] == "PRATO" and cc["proposed_why"] == "Marketing / Advertising" and "branch 2" in cc["reason"])
    check("5c. classification missing → WHO PRATO, WHY Da verificare — never Marketing / Advertising",
          ms["proposed_who"] == "PRATO" and ms["proposed_why"] is None and ms["why_to_verify"]
          and "no settlement account" in ms["reason"] and "WHY To verify: not assigned" in ms["plan_note"],
          detail=str(ms))
    check("5d. a Personal bank account matches no branch: WHO PRATO, WHY unchanged",
          pa["proposed_who"] == "PRATO" and pa["proposed_why"] is None and not pa["why_to_verify"]
          and "no branch applies" in pa["reason"])
    check("5e. movements without “Prato Winter Park” are not matched", ids["other"] not in items and ids["salon"] not in items)
    lines = p["interpretation_lines"]
    check("6. the window shows the rule's and every branch's conditions and assignments, and the data checked",
          lines[0] == "IF the description contains “Prato Winter Park” (upper/lower case alike)"
          and "WHO: PRATO (existing)" in lines
          and "BRANCH 1 — IF the Source is a card AND the Source is classified Personal → WHY: Owner Personal — Food "
              "(existing, OWNER_PERSONAL_FOOD)" in lines
          and "BRANCH 2 — IF the Source is classified not Personal → WHY: Marketing / Advertising (existing, "
              "MARKETING_ADVERTISING)" in lines
          and "BRANCH 3 — IF the Source is without a Personal classification (missing) → WHY: To verify" in lines
          and any(line.startswith("Data checked — Personal / not Personal = the Source's owner") for line in lines),
          detail=json.dumps(lines, ensure_ascii=False))
    calls["n"] = 0
    again = preview(PRATO, "prato_personal_card")
    check("7. the same rule again: the interpretation is reused — no AI call", again["ai_calls"] == 0 and calls["n"] == 0
          and again["interpretation_reused"])

    # ------------------------------------------------- applying PRATO on ALL
    def post(path, **data):
        form = {"csrf_token": csrf, "rule_text": PRATO, "origin_transaction_id": str(ids["prato_personal_card"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30"}
        form.update(data)
        return client.post(path, data=form, headers={"X-Requested-With": "fetch"}).get_json()

    p_all = post("/bank/ai-rules/preview", scope_all="on")
    applied = post("/bank/ai-rules/save-apply", scope_all="on", preview_id=str(p_all["preview_id"]))
    with SessionFactory() as s:
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=ids[k]) for k in
                   ("prato_personal_card", "prato_company_card", "prato_missing", "prato_personal_account")}
        got = {k: (e.occurrence_id, e.transaction_reason_id) if e else None for k, e in current.items()}
        items = {i.financial_transaction_id: i for i in s.scalars(select(m.BankAiRuleApplicationItem))}
    check("8. applied (on this test database): each branch's WHY; the missing classification gets the WHO only",
          applied["ok"] and got == {"prato_personal_card": (prato_id, whys["Owner Personal — Food"]),
                                    "prato_company_card": (prato_id, whys["Marketing / Advertising"]),
                                    "prato_missing": (prato_id, None),
                                    "prato_personal_account": (prato_id, None)}
          and "WHY To verify" in items[ids["prato_missing"]].note, detail=f"{got} {applied.get('application')}")

    # ---------------------------------------------- BONNE VIE SALON and Zelle
    p = preview(SALON, "salon")
    check("9. BONNE VIE SALON still works (code, existing WHO and WHY)",
          p["method"] == "CODE" and [i["id"] for i in p["match_items"]] == [ids["salon"]]
          and p["match_items"][0]["proposed_why"] == "Owner Personal — Other")
    p = preview(ZELLE, "zelle")
    check("10. Zelle/JPM still works (WHO between, WHY unchanged)",
          p["method"] == "CODE" and p["match_items"][0]["proposed_who"] == "GIOVANNA WINE REP"
          and p["match_items"][0]["proposed_why"] is None)

    # ------------------------------------------ unsupported parts, v1 structures
    p = preview(UNSUPPORTED, "publix_personal_card")
    check("11. a part the engine cannot express is declared, and no simplified version is executed",
          p["method"] == "AI" and "importo supera 100 dollari" in (p["interpretation_rejected"] or ""))
    check("11b. validation: a non-last branch without conditions, or a branch that assigns nothing, is refused",
          ai_rules.validate_interpretation({"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains",
                                            "value": "x"}], "who": None, "why": None,
                                            "branches": [{"conditions": [], "why": {"mode": "to_verify"}},
                                                         {"conditions": [], "why": {"mode": "to_verify"}}]}, "x")[0] is None
          and ai_rules.validate_interpretation({"kind": "STRUCTURED", "conditions": [{"field": "description",
                                                "op": "contains", "value": "x"}], "who": None, "why": None,
                                                "branches": [{"conditions": [{"field": "source_class", "op": "is",
                                                                              "value": "Personal"}]}]}, "x")[1]
          == "branch 1 assigns nothing"
          and ai_rules.validate_interpretation({"kind": "STRUCTURED", "conditions": [{"field": "source_owner_kind",
                                                "op": "is", "value": "Person"}], "who": {"mode": "fixed", "name": "x"}},
                                               "x")[1] == "the condition field “source_owner_kind” is not supported")

    v1 = {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "PUBLIX"},
                                               {"field": "source_owner_kind", "op": "is", "value": "Person"}],
          "who": {"mode": "fixed", "name": "PUBLIX"}, "why": None}
    with SessionFactory() as s:
        rule = m.BankAiRule(title="old v1", status="ACTIVE", apply_future=True)
        s.add(rule)
        s.flush()
        s.add(m.BankAiRuleVersion(rule_id=rule.id, version_no=1, rule_text="old", create_missing_who=False,
                                  method="CODE", spec=json.dumps(v1)))
        s.commit()
        old_rule_id = rule.id
        context = ai_rule_operations.import_context(s)
        in_context = context is not None and any(r.id == old_rule_id for r, _v, _s in context.entries)
        try:
            ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, old_rule_id), scope="ALL", selected_ids=None,
                                          preview_id=None, account_id=None)
            refused = ""
        except ai_rules.AiRuleError as exc:
            refused = str(exc)
        s.rollback()
    check("12. a saved v1 structure that read Personal as “owner is a Person” is never executed (import, apply)",
          not in_context and "saved interpretation is outdated" in refused, detail=refused)
    with SessionFactory() as s:
        explanations = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    check("13. nothing else was written: decisions only from the PRATO application above",
          explanations == 4, detail=str(explanations))

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway file
            pass
