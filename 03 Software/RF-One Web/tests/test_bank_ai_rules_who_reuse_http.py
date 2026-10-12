"""Bank > AI Rules — reusing existing WHO and cleaning the extracted text (BANK_AI_RULES_016).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rule. Invented names; KATOM is the Product Owner's mandatory example, not a case
in the code.

* the extracted text is cleaned (line breaks and tabs → spaces, spaces collapsed, trimmed, upper case) before it is
  compared, created or saved: no WHO is ever stored with a line break;
* an exact WHO first; otherwise an existing WHO that identifies the same subject (its name followed by
  abbreviations, suffixes or codes): "KATOMRESTAU PAY" → KATOM; never a vague similarity (a short name, a different
  word); two or more candidates → a DOUBT in Preview, none chosen, never applied;
* a reused WHO brings its default WHY; Preview shows the extracted text and the final WHO, saying it was reused;
* applying uses the existing WHO — no new WHO is created for it.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_who_reuse_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-who-reuse-secret"
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
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = ("Se la descrizione contiene \"PAYPAL\": il WHO è il testo dopo il primo asterisco (*) fino alla fine della "
        "descrizione, in MAIUSCOLO; assegna il WHY di default del WHO, vuoto se non ne ha.")
SPEC = {"kind": "STRUCTURED", "conditions": [],
        "who": {"mode": "to_end", "starts": ["PAYPAL"], "after": "*", "start_at": "anywhere"},
        "why": {"mode": "who_default", "if_missing": "clear"}, "for_whom": None, "status": None,
        "only_if_who_differs": False, "replace_existing": True, "branches": [], "unsupported": [],
        "coverage": [{"instruction": "testo dopo * fino alla fine", "represented_by": "who.to_end"},
                     {"instruction": "WHY di default", "represented_by": "why.who_default clear"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    same = ai_rules.same_subject
    check("1. same subject: KATOM is “KATOMRESTAU PAY” (abbreviation + suffix); a name followed by codes too",
          same("KATOM", "KATOMRESTAU PAY") and same("KATOMRESTAU", "KATOMRESTAU PAY")
          and same("TEMU", "TEMU 123456")
          and same("ACME SUPPLY", "ACME SUPPLY 4471 XZ"))
    check("2. never a vague similarity: a short name, a different word, the reverse direction, an identical name",
          not same("TEMU", "TEMUCO SA") and not same("ACME SUPPLY", "ACME SERVICES")
          and not same("GIOVANNA", "GIOVANNA WINE REP") and not same("DELTA", "DELTA DENTAL")
          and not same("AB", "AB 12")
          and not same("KATOMRESTAU PAY", "KATOM") and not same("KATOM", "KATOM") and not same("ATOM", "KATOMX"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_wr", display_name="AI WR", password="AiWrPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_wr").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF WR, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="WR Checking",
                                   institution="CHASE", last_four="9101", currency="USD")
        s.add(card)
        s.flush()
        why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).first()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        for name, default in (("KATOM", why.id), ("ZENITH", None), ("ZENITHCO", None), ("EXACTCO PAY", why.id)):
            s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                   default_transaction_reason_id=default))
        ids = {}
        for i, (key, text) in enumerate((("katom", "PAYPAL *KATOMRESTAU PAY"), ("exact", "PAYPAL *EXACTCO PAY"),
                                         ("ambiguous", "PAYPAL *ZENITHCO 778"),
                                         ("messy", "PAYPAL *  New\tVendor\r\n  Shop  "),
                                         ("short", "PAYPAL *TEMUCO SA")), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"wr-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        s.commit()
        why_id, why_name = why.id, why.name

    ai_client.generate_json = lambda prompt: SPEC
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_wr", "password": "AiWrPass123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)
    p = client.post("/bank/ai-rules/preview", data={
        "csrf_token": csrf, "rule_text": RULE, "origin_transaction_id": str(ids["katom"]), "date_from": "2026-09-01",
        "date_to": "2026-09-30", "scope_all": "on", "create_missing_who": "on"},
        headers={"X-Requested-With": "fetch"}).get_json()
    items = {i["id"]: i for i in p.get("match_items", [])}
    doubts = {i["id"]: i for i in p.get("doubt_items", [])}
    katom = items.get(ids["katom"]) or {}
    check("3. “KATOMRESTAU PAY” → the existing WHO KATOM, its default WHY; Preview shows the extracted text and says "
          "it was reused",
          katom.get("proposed_who") == "KATOM" and not katom.get("proposed_who_is_new")
          and katom.get("extracted_who") == "KATOMRESTAU PAY" and katom.get("proposed_why") == why_name
          and "WHO esistente KATOM riutilizzato" in (katom.get("reason") or "") and p.get("who_reused") == 1,
          detail=str({k: katom.get(k) for k in ("proposed_who", "extracted_who", "proposed_why", "reason")}))
    exact = items.get(ids["exact"]) or {}
    check("4. an exact WHO first (“EXACTCO PAY” exists): it is the one used, nothing “reused”",
          exact.get("proposed_who") == "EXACTCO PAY" and exact.get("extracted_who") == "EXACTCO PAY")
    amb = doubts.get(ids["ambiguous"]) or {}
    check("5. two existing WHO could be it (ZENITH, ZENITHCO): a DOUBT, none chosen, never applied",
          ids["ambiguous"] not in items and amb and "ZENITH, ZENITHCO" in (amb.get("reason") or "")
          and "never applied" in (amb.get("plan_note") or ""), detail=str(amb))
    messy = items.get(ids["messy"]) or {}
    check("6. line breaks and tabs cleaned before comparing: “NEW VENDOR SHOP” (a new WHO)",
          messy.get("proposed_who") == "NEW VENDOR SHOP" and messy.get("proposed_who_is_new"), detail=str(messy))
    short = items.get(ids["short"]) or {}
    check("7. “TEMUCO SA” is not reused for anything vague: a new WHO", short.get("proposed_who") == "TEMUCO SA"
          and short.get("proposed_who_is_new"))

    with SessionFactory() as s:
        whos_before = s.scalar(select(func.count(m.BankOccurrence.id)))
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=True,
                                             apply_future=False, origin_transaction_id=ids["katom"], account_id=None)
        s.commit()
    p_rule = client.post("/bank/ai-rules/preview", data={
        "csrf_token": csrf, "rule_text": RULE, "origin_transaction_id": str(ids["katom"]), "date_from": "2026-09-01",
        "date_to": "2026-09-30", "scope_all": "on", "create_missing_who": "on", "rule_id": str(saved.rule.id)},
        headers={"X-Requested-With": "fetch"}).get_json()
    with SessionFactory() as s:
        application = ai_rule_operations.apply_rule(s, rule=s.get(m.BankAiRule, saved.rule.id), scope="ALL",
                                                    selected_ids=None, preview_id=p_rule["preview_id"],
                                                    account_id=None)
        s.commit()
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        names = {o.id: o.canonical_name for o in s.scalars(select(m.BankOccurrence))}
        created = sorted(n for n in names.values() if n in ("NEW VENDOR SHOP", "TEMUCO SA", "KATOMRESTAU PAY"))
        whos_after = s.scalar(select(func.count(m.BankOccurrence.id)))
        with_breaks = [n for n in names.values() if any(c in n for c in "\r\n\t") or "  " in n or n != n.strip()]
    check("8. applied: KATOM reused (no “KATOMRESTAU PAY” created), its default WHY assigned",
          names[current["katom"].occurrence_id] == "KATOM" and current["katom"].transaction_reason_id == why_id
          and "KATOMRESTAU PAY" not in created, detail=str(created))
    check("9. the ambiguous movement is not changed", current["ambiguous"] is None)
    check("10. only the genuinely new WHO are created, all clean — no WHO with a line break, tab or double space",
          created == ["NEW VENDOR SHOP", "TEMUCO SA"] and whos_after == whos_before + 2 and not with_breaks
          and application.errors == 0, detail=f"{created} {with_breaks}")

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
