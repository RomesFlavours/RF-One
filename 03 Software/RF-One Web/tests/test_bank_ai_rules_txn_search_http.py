"""Bank > AI Rules — the movements' search (BANK_AI_RULES_024).

On a throwaway database, over HTTP. No AI is called.

* a "Search transactions" field above the movements, Search to its right on
  the same row; a GET form, so Enter and Search do the same;
* the same search as Bank Reconciliation: the description, the current WHO,
  the current WHY, the Source's name — any case, literally;
* empty: every movement the period and "Classificazione" show, again;
* independent of "Search rules", and kept with the period and Classificazione;
* it never changes the selection (the excluded ids follow Classificazione
  only) nor the Preview scope.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date
from html import unescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_txn_search_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-txn-search-secret"

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
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PERIOD = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_txn", display_name="AI Txn", password="AiTxn123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_txn").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Txn, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Search Checking", institution="CHASE", last_four="3003",
                                       currency="USD")
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="CREDIT_CARD", display_name="Amex Gold",
                                   institution="AMEX", last_four="1004", currency="USD")
        s.add_all([checking, card])
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        who = m.BankOccurrence(canonical_name="FLORIDA POWER", occurrence_type_id=counterparty.id, status="ACTIVE")
        s.add(who)
        why = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                        .order_by(m.BankTransactionReason.name)).first()
        s.flush()
        ids = []
        for i, (text, instrument) in enumerate((("PUBLIX SUPER MARKET 1234", checking), ("FPL ELECTRIC BILL", checking),
                                                ("RANDOM SHOP 50%_OFF", card), ("ZELLE PAYMENT TO MARIO", checking))):
            t = m.FinancialTransaction(
                payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2 + i),
                transaction_date=date(2026, 9, 2 + i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"txn-search-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        fpl = s.get(m.FinancialTransaction, ids[1])
        recognition._create_decision_row(s, fpl, occurrence_id=who.id, transaction_reason_id=why.id,
                                         decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW",
                                         confidence=None, explanation_notes="test")
        why_name = why.name
        s.add(m.BankAiRule(title="regola PUBLIX", user_title="Spesa", status="ACTIVE", apply_future=False))
        s.commit()

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_txn", "password": "AiTxn123!", "csrf_token": csrf})

    def shown(**args) -> tuple[set[int], str]:
        page = client.get("/bank/ai-rules", query_string={**PERIOD, **args}).data.decode()
        return {int(i) for i in re.findall(r'class="ai-rule-select" value="(\d+)"', page)}, page

    every, page = shown()
    form = page[page.index("ai-txn-search"):]
    form = form[:form.index("</form>")]
    check("1. a GET “Search transactions” form above the movements, Search to the right of the field",
          'name="q"' in form and form.index('name="q"') < form.index(">Search</button>")
          and page.index("ai-txn-search") < page.index('id="ai-rules-transactions"') and every == set(ids),
          detail=str(every))

    found, _ = shown(q="publix")
    check("2. by description, any case", found == {ids[0]}, detail=str(found))
    found, _ = shown(q="florida power")
    check("3. by the current WHO", found == {ids[1]}, detail=str(found))
    found, _ = shown(q=why_name.upper())
    check("4. by the current WHY", found == {ids[1]}, detail=f"{why_name}: {found}")
    found, _ = shown(q="amex gold")
    check("5. by the Source's name", found == {ids[2]}, detail=str(found))
    found, _ = shown(q="50%_")
    check("6. literally: % and _ are not wildcards", found == {ids[2]}, detail=str(found))
    found, page = shown(q="nothing like this")
    check("7. no match: no movement, and the page says so",
          found == set() and "No transactions match your search" in page)
    found, page = shown(q="  ")
    check("8. an empty search shows every movement again", found == set(ids) and "found for" not in page)

    found, page = shown(q="zelle", cls="no_who")
    bar = re.search(r'data-excluded-ids="([^"]*)"', page).group(1)
    _no_q, page_no_q = shown(cls="no_who")
    bar_no_q = re.search(r'data-excluded-ids="([^"]*)"', page_no_q).group(1)
    check("9. with Classificazione “Senza WHO”: the search narrows only within it", found == {ids[3]}, detail=str(found))
    check("10. the ids Classificazione excludes are the same with or without a search (the search's own limit "
          "is applied by the page and by the server, BANK_AI_RULES_025)",
          json.loads(unescape(bar)) == json.loads(unescape(bar_no_q)) == [ids[1]], detail=f"{bar} / {bar_no_q}")
    period = page[page.index('id="ai-rules-period"'):]
    period = period[:period.index("</form>")]
    txn_form = page[page.index("ai-txn-search"):]
    txn_form = txn_form[:txn_form.index("</form>")]
    check("11. kept with the period and Classificazione, both ways",
          'name="q" value="zelle"' in period and 'name="cls" value="no_who"' in txn_form
          and 'name="date_from" value="2026-09-01"' in txn_form)

    found, page = shown(q="publix", rule_q="spesa")
    rules = re.findall(r'<tr data-rule-id="(\d+)"', page)
    rule_form = page[page.index('id="ai-rules-search"') - 600:page.index('id="ai-rules-search"')]
    txn_form = page[page.index("ai-txn-search"):]
    txn_form = txn_form[:txn_form.index("</form>")]
    check("12. independent of “Search rules”: each filters its own list, and each form keeps the other",
          found == {ids[0]} and len(rules) == 1 and 'name="q" value="publix"' in rule_form
          and 'name="rule_q" value="spesa"' in txn_form, detail=f"{found} {rules}")

    # ------------------------------------------- BANK_AI_RULES_025: the selection's perimeter
    from rfone_data_store.selection.parsing import ai_client
    rule = "Se la descrizione contiene “SUPER MARKET”, assegna WHO \"FLORIDA POWER\"."
    ai_client.generate_json = lambda prompt: {
        "kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "SUPER MARKET"}],
        "who": {"mode": "fixed", "name": "FLORIDA POWER"}, "why": None, "branches": [], "status": None,
        "only_if_who_differs": False, "replace_existing": False, "unsupported": [],
        "coverage": [{"instruction": "contiene SUPER MARKET", "represented_by": "conditions"},
                     {"instruction": "assegna WHO", "represented_by": "who.fixed"}]}
    csrf = CSRF_RE.search(page).group(1)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids[0]), "rule_text": rule, "scope_selected": "on",
                "cls": "all", **PERIOD}
        form.update({k: str(v) for k, v in data.items()})
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    everything = ",".join(str(i) for i in ids)
    status, limited = post("/bank/ai-rules/preview", selected_ids=everything, q="publix")
    check("13. server: a Preview of the selection with a search examines ONLY the selected movements within it, "
          "whatever the page sent", status == 200 and limited["examined"] == 1, detail=str(limited.get("examined")))
    status, outside = post("/bank/ai-rules/preview", selected_ids=f"{ids[1]},{ids[3]}", q="publix")
    check("14. server: a selection with nothing within the search is refused", status == 400
          and "None of the selected movements" in outside["error"], detail=str(outside))
    status, no_search = post("/bank/ai-rules/preview", selected_ids=everything, q="")
    check("15. without a search the selection is as before (all the selected movements)",
          status == 200 and no_search["examined"] == len(ids), detail=str(no_search.get("examined")))

    status, saved = post("/bank/ai-rules/save-apply", selected_ids=everything, q="publix",
                         preview_id=limited["preview_id"])
    with SessionFactory() as s:
        app_ = s.get(m.BankAiRuleApplication, saved["application"]["application_id"]) if saved.get("ok") else None
        touched = sorted(i.financial_transaction_id for i in app_.items) if app_ else []
    check("16. server: Apply with the same search operates only within it (the preview of the limited selection "
          "authorizes it; the other selected movements are not even examined)",
          saved.get("ok") and saved["application"]["examined"] == 1 and touched == [ids[0]], detail=f"{saved} {touched}")

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
