"""Bank > AI Rules — WHO "to_end": after one of several start texts and the first following marker, up to the END
of the description (BANK_AI_RULES_015).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rule.

* PAYPAL *AIRBNB HMSSZ842DA → AIRBNB HMSSZ842DA, PAYPAL *TEMU → TEMU (mandatory examples); PYPAL is an
  alternative start; any case; codes and numbers stay; no marker → not matching; nothing after → doubtful;
* the WHO's default WHY; a WHO not in the list: created only with "Crea WHO mancanti" (otherwise not applied);
  no default WHY → the WHY is left empty, to be completed, never invented;
* such a movement is NOT settled by AI rules (WHO without WHY); one with WHO and WHY is;
* the interpretation is shown as it is (text up to the END of the description), never simplified;
* a marker or start text not written in the rule makes the interpretation invalid.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_to_end_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-to-end-secret"
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
RULE = ("Se la descrizione contiene \"PAYPAL\" oppure \"PYPAL\", senza distinzione tra maiuscole e minuscole: estrai il "
        "testo dopo il primo asterisco (*) che segue PAYPAL/PYPAL, fino alla fine della descrizione; togli gli spazi "
        "iniziali e finali e converti in MAIUSCOLO: questo è il WHO. Assegna il WHY di default del WHO; se non ne ha, "
        "lascia il WHY da completare senza inventarlo. Se manca l'asterisco o il testo dopo è vuoto, non applicare.")
FULL = {"kind": "STRUCTURED", "conditions": [],
        "who": {"mode": "to_end", "starts": ["PAYPAL", "PYPAL"], "after": "*", "start_at": "anywhere"},
        "why": {"mode": "who_default", "if_missing": "clear"}, "for_whom": None, "status": None,
        "only_if_who_differs": False, "replace_existing": True, "branches": [], "unsupported": [],
        "coverage": [{"instruction": "PAYPAL oppure PYPAL, maiuscole indifferenti", "represented_by": "who.to_end starts"},
                     {"instruction": "testo dopo il primo * fino alla fine, MAIUSCOLO", "represented_by": "who.to_end"},
                     {"instruction": "WHY di default, altrimenti da completare", "represented_by": "why.who_default clear"},
                     {"instruction": "manca * o testo vuoto: non applicare", "represented_by": "who.to_end"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_te", display_name="AI TE", password="AiTePass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_te").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF TE, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="TE Checking",
                                   institution="CHASE", last_four="9001", currency="USD")
        s.add(card)
        s.flush()
        why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).first()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        s.add(m.BankOccurrence(canonical_name="AIRBNB HMSSZ842DA", occurrence_type_id=counterparty.id,
                               status="ACTIVE", default_transaction_reason_id=why.id))
        ids = {}
        for i, (key, text) in enumerate((("airbnb", "PAYPAL *AIRBNB HMSSZ842DA"), ("temu", "PAYPAL *TEMU"),
                                         ("pypal", "pypal *Uber  Eats 12 "), ("no_star", "PAYPAL INST XFER"),
                                         ("empty", "PAYPAL *"), ("other", "AMAZON MKTP")), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"te-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        s.commit()
        why_id, why_name = why.id, why.name

    ai_client.generate_json = lambda prompt: FULL
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_te", "password": "AiTePass123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def preview(**extra):
        data = {"csrf_token": csrf, "rule_text": RULE, "origin_transaction_id": str(ids["airbnb"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30", "scope_all": "on"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    a = {"starts": ["PAYPAL", "PYPAL"], "after": "*", "start_at": "anywhere"}
    check("1. the mandatory examples: PAYPAL *AIRBNB HMSSZ842DA → AIRBNB HMSSZ842DA, PAYPAL *TEMU → TEMU",
          ai_rules.extract_to_end("PAYPAL *AIRBNB HMSSZ842DA", a) == ("MATCH", "AIRBNB HMSSZ842DA")
          and ai_rules.extract_to_end("PAYPAL *TEMU", a) == ("MATCH", "TEMU"))
    check("2. PYPAL and any case; codes and numbers kept; no marker → no match; nothing after → empty",
          ai_rules.extract_to_end("pypal *Uber  Eats 12 ", a) == ("MATCH", "UBER EATS 12")
          and ai_rules.extract_to_end("PAYPAL INST XFER", a)[0] == "NO_MARKER"
          and ai_rules.extract_to_end("PAYPAL *", a)[0] == "EMPTY"
          and ai_rules.extract_to_end("AMAZON MKTP", a)[0] == "NO_PREFIX")
    spec, reason = ai_rules.validate_interpretation(FULL, RULE)
    bad = ai_rules.validate_interpretation({**FULL, "who": {**FULL["who"], "after": "#"}}, RULE)
    check("3. the interpretation is valid with no condition (the extraction is the condition); a marker not "
          "written in the rule is refused",
          spec is not None and spec["who"]["starts"] == ["PAYPAL", "PYPAL"] and bad[0] is None, detail=str(reason))

    p_off = preview()
    off = {i["id"]: i for i in p_off.get("match_items", [])}
    check("4. matches only the descriptions with PAYPAL/PYPAL and a following '*'; '*' with nothing after is doubtful",
          p_off.get("ok") and set(off) == {ids["airbnb"], ids["temu"], ids["pypal"]}
          and {i["id"] for i in p_off.get("doubt_items", [])} == {ids["empty"]}, detail=str(p_off.get("error")))
    check("5. existing WHO → its default WHY is proposed", off[ids["airbnb"]]["proposed_who"] == "AIRBNB HMSSZ842DA"
          and off[ids["airbnb"]]["proposed_why"] == why_name and off[ids["airbnb"]]["plan"] == "UPDATED")
    check("6. WHO not in the list and “Crea WHO mancanti” off: not applied, said so",
          off[ids["temu"]]["plan"] == "UNRESOLVED" and "Crea WHO mancanti" in off[ids["temu"]]["plan_note"])
    lines = p_off.get("interpretation_lines") or []
    check("7. the window shows the extraction as it is: up to the END of the description, nothing removed",
          any("up to the END of the description" in x and "“PAYPAL” or “PYPAL”" in x and "“*”" in x for x in lines),
          detail=str(lines))

    p_on = preview(create_missing_who="on")
    on = {i["id"]: i for i in p_on.get("match_items", [])}
    check("8. “Crea WHO mancanti” on: TEMU will be created; no default WHY → WHY left to complete, never invented",
          on[ids["temu"]]["plan"] == "UPDATED" and on[ids["temu"]]["proposed_who_is_new"]
          and not on[ids["temu"]]["proposed_why"] and "da completare" in on[ids["temu"]]["plan_note"],
          detail=on[ids["temu"]]["plan_note"])

    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=True,
                                             apply_future=False, origin_transaction_id=ids["airbnb"], account_id=None)
        s.commit()
        rule_id = saved.rule.id
    p_rule = preview(create_missing_who="on", rule_id=str(rule_id))
    with SessionFactory() as s:
        ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, rule_id), scope="ALL", selected_ids=None,
                                      preview_id=p_rule["preview_id"], account_id=None)
        s.commit()
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        temu = s.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "TEMU"))
        settled = ai_rules.ai_settled(s)
    check("9. applied: AIRBNB gets WHO + default WHY; TEMU is created and assigned, its WHY left empty",
          current["airbnb"].transaction_reason_id == why_id and temu is not None
          and current["temu"].occurrence_id == temu.id and current["temu"].transaction_reason_id is None)
    check("10. AIRBNB (WHO and WHY) is settled by the AI rule; TEMU (WHY to complete) is NOT",
          settled.get(ids["airbnb"]) == rule_id and ids["temu"] not in settled, detail=str(settled))
    again = preview(create_missing_who="on", only_unsettled="on", rule_id=str(rule_id))
    again_ids = {i["id"] for i in again.get("match_items", [])}
    check("11. with “Solo movimenti non ancora sistemati”: TEMU is considered again, AIRBNB is left out",
          ids["temu"] in again_ids and ids["airbnb"] not in again_ids and again.get("excluded_ai_settled") == 1,
          detail=str({k: again.get(k) for k in ("excluded_ai_settled", "excluded_by_rule")}))

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
