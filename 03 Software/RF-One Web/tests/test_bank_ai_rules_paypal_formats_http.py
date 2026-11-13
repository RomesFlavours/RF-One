"""Bank > AI Rules — digits removed, a letter required, exact formats (BANK_AI_RULES_021).

On a throwaway database, over HTTP and through the service. The AI provider is replaced INSIDE THIS TEST ONLY by
a stand-in that interprets the rules. The two-format rule mirrors the Product Owner's PayPal rule:

* FORMAT 1 — the description starts with "ORIG CO NAME:PAYPAL" followed by a space or the end: WHO between
  "IND ID:" and "IND NAME:"; FORMAT 2 — "PAYPAL", only spaces, "*": WHO up to the end;
* digits 0-9 removed from the extracted text ("WIX 1259622963" → WIX); no letter left → no WHO, "Da verificare";
* a missing delimiter or another format → the movement is not changed (not matched);
* the generic ORIG CO NAME rule excludes exactly FORMAT 1 ("not_starts_with_word"), so the two never conflict;
* Preview "Solo WHO" with "Crea WHO mancanti": WIX / TEMU proposed, no WHY, numeric-only = doubt.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_paypal_formats_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-paypal-formats-secret"
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
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PAYPAL_RULE = ("FORMATO 1: la descrizione comincia con “ORIG CO NAME:PAYPAL” seguito da uno spazio o dalla fine: il WHO "
               "è il testo tra “IND ID:” e “IND NAME:”. FORMATO 2: la descrizione comincia con “PAYPAL”, eventuali spazi "
               "e “*”: il WHO è il testo dopo il primo “*” fino alla fine. In entrambi rimuovi le cifre da 0 a 9; se non "
               "resta almeno una lettera il WHO è da verificare. Non applicare ad altri formati.")
GENERIC_RULE = ("Se la descrizione comincia con “ORIG CO NAME:” ma non comincia con “ORIG CO NAME:PAYPAL” seguito da uno "
                "spazio o dalla fine, il WHO è il testo tra “ORIG CO NAME:” e “ORIG ID:”.")
COV = [{"instruction": "the whole rule", "represented_by": "branches / conditions + extraction options"}]
PAYPAL_SPEC = {
    "kind": "STRUCTURED", "conditions": [], "who": None, "why": None, "for_whom": None, "status": None,
    "only_if_who_differs": False, "replace_existing": True, "unsupported": [], "coverage": COV,
    "branches": [
        {"conditions": [{"field": "description", "op": "starts_with_word", "value": "ORIG CO NAME:PAYPAL"}],
         "who": {"mode": "between", "start": "IND ID:", "end": "IND NAME:", "start_at": "anywhere",
                 "end_case": "ignore", "strip_digits": True, "require_letter": True}},
        {"conditions": [{"field": "description", "op": "starts_with", "value": "PAYPAL"}],
         "who": {"mode": "to_end", "starts": ["PAYPAL"], "start_at": "beginning", "after": "*",
                 "after_adjacent": True, "strip_digits": True, "require_letter": True}},
    ]}
GENERIC_SPEC = {
    "kind": "STRUCTURED", "who": {"mode": "between", "start": "ORIG CO NAME:", "end": "ORIG ID:", "start_at": "beginning",
                                  "end_case": "ignore"},
    "conditions": [{"field": "description", "op": "not_starts_with_word", "value": "ORIG CO NAME:PAYPAL"}],
    "why": None, "for_whom": None, "status": None, "only_if_who_differs": False, "replace_existing": True,
    "branches": [], "unsupported": [], "coverage": COV}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    spec, reason = ai_rules.validate_interpretation(PAYPAL_SPEC, PAYPAL_RULE)
    check("1. the two-format interpretation is valid (no rule-level condition: one branch per format, no otherwise)",
          spec is not None and spec["branches"][0]["who"]["strip_digits"] and spec["branches"][1]["who"]["after_adjacent"],
          detail=str(reason))
    gspec, greason = ai_rules.validate_interpretation(GENERIC_SPEC, GENERIC_RULE)
    check("2. the generic rule with “not_starts_with_word” is valid", gspec is not None, detail=str(greason))
    bad = ai_rules.validate_interpretation({**GENERIC_SPEC, "who": {**GENERIC_SPEC["who"], "after_adjacent": True}},
                                           GENERIC_RULE)
    check("3. “after_adjacent” without a “to_end” marker is refused", bad[0] is None)

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_pf", display_name="AI PF", password="AiPfPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_pf").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF PF, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="PF Checking",
                                   institution="CHASE", last_four="9301", currency="USD")
        s.add(card)
        s.flush()
        ids = {}
        for i, (key, text) in enumerate((
                ("wix", "ORIG CO NAME:PAYPAL         ORIG ID:PAYPALSI77 DESC DATE:260305 IND ID:WIX 1259622963   "
                        "IND NAME:GIUSEPPE MIRAGLIA TRN: 0640200014TC"),
                ("numeric", "ORIG CO NAME:PAYPAL ORIG ID:PAYPALSI77 IND ID:1050950454780 IND NAME:GIUSEPPE MIRAGLIA"),
                ("no_ind_name", "ORIG CO NAME:PAYPAL ORIG ID:PAYPALSI77 IND ID:WIX 1259622963"),
                ("paypalsi", "ORIG CO NAME:PAYPALSI ORIG ID:X IND ID:ACME IND NAME:Y"),
                ("temu", "PAYPAL *TEMU"),
                ("temu_spaces", "  paypal   *Temu 42  "),
                ("inst", "PAYPAL INST XFER"),
                ("inst_star", "PAYPAL INST *ODD"),
                ("other", "ORIG CO NAME:ADP WAGE PAY ORIG ID:9333 DESC DATE:260107"),
        ), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"pf-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        s.commit()
        rows = {r.id: r for r in ai_rules.scope_rows(s, scope=ai_rules.SCOPE_ALL, date_from=None, date_to=None)}
        res = {k: ai_rules.execute(spec, rows[v]) for k, v in ids.items()}
        gres = {k: ai_rules.execute(gspec, rows[v]) for k, v in ids.items()}

    check("4. IND ID:WIX 1259622963 IND NAME: → WIX (digits removed)",
          res["wix"].outcome == "MATCH" and res["wix"].who == "WIX", detail=str(res["wix"]))
    check("5. PAYPAL *TEMU → TEMU; any case and spaces before “*”; digits removed",
          res["temu"].who == "TEMU" and res["temu_spaces"].who == "TEMU", detail=f"{res['temu']} {res['temu_spaces']}")
    check("6. extracted text only digits → no WHO, “Da verificare”",
          res["numeric"].outcome == "MATCH" and res["numeric"].who is None and res["numeric"].who_verify,
          detail=str(res["numeric"]))
    check("7. missing delimiter (no IND NAME:) → not changed",
          res["no_ind_name"].outcome != "MATCH", detail=str(res["no_ind_name"]))
    check("8. other formats are not this rule's: PAYPALSI, PAYPAL INST XFER, PAYPAL INST *…, any other description",
          all(res[k].outcome == "NO_MATCH" or res[k].outcome == "NO_MARKER" for k in ("paypalsi", "inst", "inst_star", "other")),
          detail=str({k: res[k].outcome for k in ("paypalsi", "inst", "inst_star", "other")}))
    check("9. the generic rule excludes exactly FORMAT 1 and still takes the others (incl. ORIG CO NAME:PAYPALSI)",
          gres["wix"].outcome == "NO_MATCH" and gres["numeric"].outcome == "NO_MATCH"
          and gres["other"].who == "ADP WAGE PAY" and gres["paypalsi"].who == "PAYPALSI",
          detail=str({k: (gres[k].outcome, gres[k].who) for k in ("wix", "other", "paypalsi")}))

    rules_by_text = {PAYPAL_RULE: PAYPAL_SPEC, GENERIC_RULE: GENERIC_SPEC}

    def stand_in(prompt):
        return rules_by_text[prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]]

    ai_client.generate_json = stand_in
    with SessionFactory() as s:
        ids_rules = {}
        for text in (GENERIC_RULE, PAYPAL_RULE):
            saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=text, create_missing_who=True,
                                                 apply_future=False, origin_transaction_id=ids["wix"], account_id=None)
            ids_rules[text] = saved.rule.id
        s.commit()
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_pf", "password": "AiPfPass123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)
    p = client.post("/bank/ai-rules/preview", data={
        "csrf_token": csrf, "rule_text": PAYPAL_RULE, "origin_transaction_id": str(ids["wix"]),
        "date_from": "2026-09-01", "date_to": "2026-09-30", "scope_all": "on", "create_missing_who": "on",
        "who_only": "on", "rule_id": str(ids_rules[PAYPAL_RULE])}, headers={"X-Requested-With": "fetch"}).get_json()
    items = {i["id"]: i for i in p.get("match_items", [])}
    doubts = {i["id"]: i for i in p.get("doubt_items", [])}
    check("10. Preview “Solo WHO” + “Crea WHO mancanti”: WIX and TEMU proposed as new WHO, no WHY, no conflict with "
          "the generic rule",
          p.get("ok") and items[ids["wix"]]["proposed_who"] == "WIX" and items[ids["wix"]]["proposed_who_is_new"]
          and items[ids["temu"]]["proposed_who"] == "TEMU" and not items[ids["wix"]]["proposed_why"]
          and all(i["plan"] == "UPDATED" for i in items.values()), detail=str({k: (v["proposed_who"], v["plan"])
                                                                              for k, v in items.items()}))
    check("11. the numeric-only movement is a doubt (“Da verificare”), never applied",
          ids["numeric"] in doubts and ids["numeric"] not in items and doubts[ids["numeric"]]["who_to_verify"],
          detail=str(doubts.get(ids["numeric"])))
    check("12. nothing else matches (other formats, missing delimiter)",
          set(items) == {ids["wix"], ids["temu"], ids["temu_spaces"]}, detail=str(sorted(items)))
    check("13. the interpretation shows the options in words",
          any("every digit 0-9 removed" in x and "no letter left" in x for x in p.get("interpretation_lines") or []))
    with SessionFactory() as s:
        decisions = s.scalar(select(m.FinancialTransaction.explanation_id).where(m.FinancialTransaction.id == ids["wix"]))
    check("14. the preview wrote nothing", decisions is None)

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
