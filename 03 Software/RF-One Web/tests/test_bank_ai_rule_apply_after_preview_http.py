"""Bank > AI Rules — Salva e Applica after a valid Preview (BANK_AI_RULES_010).

The defect: a multi-line rule is sent by the browser with CRLF line ends
(form encoding) while the window's field holds LF, so the window never saw
its own preview as current and "Salva e Applica" ran the preview again,
forever. The window now compares both in one form; this test covers the
server side of the same flow, on a throwaway database, over HTTP:

* a multi-line rule (CRLF, as the browser sends it), opened from a draft,
  "Crea WHO mancanti" on, "Tutte le transazioni esistenti": Preview, then
  Salva e Applica with the same text, option and scope applies THAT preview,
  moves the rule to the operative ones and removes the draft — one rule;
* when the preview cannot authorize the application, the refusal names the
  precise reason (no preview, preview not completed, text, scope, option,
  selection) and nothing is written;
* a preview authorizes one complete application: the same request again is
  refused with the reason, nothing applied twice, no duplicate rule.

The AI provider is replaced INSIDE THIS TEST ONLY by a stand-in. Never touches
a real bank file, AWS, or any working database.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_apply_after_preview_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-apply-after-preview-secret"
os.environ.pop("RFONE_BANK_AI_MODE", None)

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
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
# As the browser sends a multi-line field: CRLF line ends.
RULE = ("Se la descrizione contiene “Zelle payment to” seguito da “JPM”, cerca entrambi i delimitatori.\r\n\r\n"
        "Estrai come WHO il testo dopo “Zelle payment to” e prima del primo “JPM”.\r\n\r\n"
        "Se manca un delimitatore non modificare la transazione.")


def interpretation(rule: str) -> dict:
    if "Zelle payment to" not in rule:
        return {"kind": "OTHER", "reason": "not this test's rule", "unsupported": ["?"],
                "coverage": [{"instruction": "?", "represented_by": "nothing"}]}
    return {"kind": "STRUCTURED",
            "conditions": [{"field": "description", "op": "contains", "value": "Zelle payment to"},
                           {"field": "description", "op": "contains", "value": "JPM"}],
            "who": {"mode": "between", "start": "Zelle payment to", "end": "JPM", "start_at": "anywhere",
                    "end_case": "ignore"},
            "why": None, "status": None, "only_if_who_differs": False, "replace_existing": False, "branches": [],
            "unsupported": [],
            "coverage": [{"instruction": "descrizione contiene “Zelle payment to” … “JPM”",
                          "represented_by": "conditions"},
                         {"instruction": "WHO tra i delimitatori", "represented_by": "who.between"},
                         {"instruction": "delimitatore mancante: nessuna modifica", "represented_by": "who.between"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_apply", display_name="AI Apply", password="AiApply123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_apply").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Apply, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Apply Checking", institution="CHASE", last_four="3002",
                                       currency="USD")
        s.add(checking)
        s.flush()
        ids = []
        for i, text in enumerate(("Zelle payment to Test Builder JPM99aa01", "Zelle payment to Test Painter JPM99bb02",
                                  "OTHER STORE")):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2 + i),
                transaction_date=date(2026, 9, 2 + i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"apply-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        s.commit()

    ai_client.generate_json = lambda prompt: interpretation(prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0])
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_apply", "password": "AiApply123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids[0]), "date_from": "2026-09-01",
                "date_to": "2026-09-30", "rule_text": RULE, "create_missing_who": "on", "scope_all": "on"}
        form.update({k: str(v) for k, v in data.items()})
        for k in [k for k, v in data.items() if v is None]:
            form.pop(k, None)
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    def counts():
        with SessionFactory() as s:
            return dict(rules=s.scalar(select(func.count(m.BankAiRule.id))),
                        versions=s.scalar(select(func.count(m.BankAiRuleVersion.id))),
                        drafts=s.scalar(select(func.count(m.BankAiRuleDraft.id))),
                        applications=s.scalar(select(func.count(m.BankAiRuleApplication.id))),
                        decisions=s.scalar(select(func.count(m.BankTransactionExplanation.id))))

    # ----------------------------------------------------- the draft, the preview
    status, draft = post("/bank/ai-rules/drafts")
    status, preview = post("/bank/ai-rules/preview", draft_id=draft["draft_id"])
    check("1. Preview of the multi-line rule (CRLF, as the browser sends it) completes; the text comes back as sent",
          preview["ok"] and preview["rule_text"] == RULE.strip() and "\r\n" in preview["rule_text"]
          and preview["matches"] == 2, detail=str({k: preview.get(k) for k in ("ok", "matches", "error")}))
    before = counts()

    # ------------------------------------------------ precise reasons, nothing written
    def refused(label, expected, **data):
        status, answer = post("/bank/ai-rules/save-apply", draft_id=draft["draft_id"], **data)
        check(label, status == 409 and answer["needs_preview"] and expected in answer["error"]
              and counts() == before, detail=f"{status} {answer}")

    refused("2a. no preview: says there is none, nothing written", "there is no Preview")
    refused("2b. text changed after the preview: says so, nothing written",
            f"not the one of Preview #{preview['preview_id']}", preview_id=preview["preview_id"],
            rule_text=RULE + " Altro.")
    refused("2c. scope changed after the preview: names both scopes, nothing written",
            f"Preview #{preview['preview_id']} was made for “Tutte le transazioni esistenti”",
            preview_id=preview["preview_id"], scope_all=None, scope_selected="on", selected_ids=f"{ids[0]}")
    refused("2d. “Crea WHO mancanti” changed after the preview: says so, nothing written",
            "“Crea WHO mancanti” is off now", preview_id=preview["preview_id"], create_missing_who=None)
    status, selected_preview = post("/bank/ai-rules/preview", scope_all=None, scope_selected="on",
                                    selected_ids=f"{ids[0]},{ids[1]}")
    before = counts()
    refused("2e. selection changed after the preview: says so, nothing written",
            f"the selected movements are not those of Preview #{selected_preview['preview_id']}",
            preview_id=selected_preview["preview_id"], scope_all=None, scope_selected="on", selected_ids=f"{ids[0]}")
    os.environ["RFONE_BANK_AI_MODE"] = "SESSION"
    try:
        post("/bank/ai-rules/preview", rule_text=RULE + "\r\nNuova riga.")
    finally:
        os.environ.pop("RFONE_BANK_AI_MODE", None)
    with SessionFactory() as s:
        waiting = s.scalar(select(func.max(m.BankAiRulePreview.id)))
    before = counts()
    refused("2f. a preview that did not complete (waiting for the session): says so with its message",
            f"Preview #{waiting} did not complete (FAILED): In attesa della sessione", preview_id=waiting,
            rule_text=RULE + "\r\nNuova riga.")

    # --------------------------------------------- same text, option, scope: applies
    status, done = post("/bank/ai-rules/save-apply", draft_id=draft["draft_id"], preview_id=preview["preview_id"])
    after = counts()
    with SessionFactory() as s:
        changed = {t.id for t in s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.explanation_id.is_not(None)))}
        whos = set(s.scalars(select(m.BankOccurrence.canonical_name)))
    check("3. Salva e Applica with the same text, option and scope applies THAT preview: rule operative, draft "
          "removed, one rule, one application",
          status == 200 and done["ok"] and done["applied"] and done["complete"] and done["draft_removed"]
          and after["rules"] == 1 and after["drafts"] == before["drafts"] - 1 and after["applications"] == 1
          and changed == {ids[0], ids[1]} and {"TEST BUILDER", "TEST PAINTER"} <= whos,
          detail=f"{status} {done} {after} {changed}")
    page = client.get("/bank/ai-rules").data.decode()
    check("3b. the rule is listed among the operative rules", f'data-rule-id="{done["rule_id"]}"' in page)

    # ---------------------------------------------------- never applied twice
    status, again = post("/bank/ai-rules/save-apply", rule_id=done["rule_id"], preview_id=preview["preview_id"])
    check("4. the same request again (same preview): refused with the reason, nothing applied twice",
          status == 409 and "has already been applied" in again["error"] and counts() == after, detail=str(again))
    status, again_new = post("/bank/ai-rules/save-apply", draft_id=draft["draft_id"], preview_id=preview["preview_id"])
    check("4b. resent as from the old window (draft id, no rule id): refused BEFORE saving — no duplicate rule",
          status == 409 and "has already been applied" in again_new["error"] and counts() == after,
          detail=str(again_new))

    # ------------------------------------------------------- the window's script
    script = client.get("/static/js/bank-ai-rules.js").data.decode()
    check("5. the window compares the text in one form (CRLF = LF) and no longer asks to press again blindly",
          "replace(/\\r\\n?/g, \"\\n\")" in script and "press Salva e Applica again" not in script
          and "staleReason()" in script)

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
