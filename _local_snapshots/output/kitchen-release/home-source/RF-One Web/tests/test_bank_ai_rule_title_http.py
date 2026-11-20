"""Bank > AI Rules — the rule's Title (BANK_AI_RULES_022).

On a throwaway database, over HTTP. The AI provider is replaced INSIDE THIS
TEST ONLY by a stand-in that interprets the rules; the application itself
never simulates an answer.

* the Title typed above the text is kept by Save Draft and by Salva, and is
  given back when the draft or the rule is opened;
* the list of operative rules shows the Title as the main identifier, the
  number "#id" as the secondary reference; a rule without a Title says so;
* a Title can be added to an existing rule saved without one;
* changing ONLY the Title (its own endpoint) never reinterprets, versions or
  reapplies the rule — even when the general instructions changed since,
  which would make Salva reinterpret it — and nothing on movements changes;
* a deleted rule's Title cannot be changed.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_title_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-title-secret"
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
RULE = "Se la descrizione contiene “SHOP TITLE”, assegna WHO \"SHOP TITLE\"."


def interpretation(_rule: str) -> dict:
    return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "SHOP TITLE"}],
            "who": {"mode": "fixed", "name": "SHOP TITLE"}, "why": None, "branches": [], "status": None,
            "only_if_who_differs": False, "replace_existing": False, "unsupported": [],
            "coverage": [{"instruction": "descrizione contiene “SHOP TITLE”", "represented_by": "conditions"},
                         {"instruction": "assegna WHO SHOP TITLE", "represented_by": "who.fixed"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_title", display_name="AI Title", password="AiTitle123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_title").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Title, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Title Checking", institution="CHASE", last_four="3002",
                                       currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        s.add(m.BankOccurrence(canonical_name="SHOP TITLE", occurrence_type_id=counterparty.id, status="ACTIVE"))
        ids = []
        for i, text in enumerate(("SHOP TITLE ONE", "SHOP TITLE TWO")):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2 + i),
                transaction_date=date(2026, 9, 2 + i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"title-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        s.commit()

    calls = {"n": 0}

    def stand_in(prompt: str) -> dict:
        calls["n"] += 1
        return interpretation(prompt)

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_title", "password": "AiTitle123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids[0]), "date_from": "2026-09-01",
                "date_to": "2026-09-30", "rule_text": RULE}
        form.update({k: str(v) for k, v in data.items() if v is not None})
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    def state(rule_id):
        with SessionFactory() as s:
            rule = s.get(m.BankAiRule, rule_id)
            return dict(user_title=rule.user_title, title=rule.title, status=rule.status,
                        apply_future=rule.apply_future, last_applied_at=rule.last_applied_at,
                        versions=s.scalar(select(func.count(m.BankAiRuleVersion.id))),
                        applications=s.scalar(select(func.count(m.BankAiRuleApplication.id))),
                        decisions=s.scalar(select(func.count(m.BankTransactionExplanation.id))),
                        interpretations=s.scalar(select(func.count(m.BankAiRuleInterpretation.id))))

    # ---------------------------------------------------------- window and drafts
    page = client.get("/bank/ai-rules").data.decode()
    check("1. the AI Rule window has a Title field above the rule text",
          'id="ai-rule-user-title"' in page and page.index('id="ai-rule-user-title"') < page.index('id="ai-rule-text"'))
    status, draft = post("/bank/ai-rules/drafts", user_title="  Spesa   Publix  ")
    reopened = client.get(f"/bank/ai-rules/drafts/{draft['draft_id']}").get_json()
    page = client.get("/bank/ai-rules").data.decode()
    check("2. Save Draft keeps the Title (one line) and gives it back when the draft is opened; the drafts list shows it",
          draft["ok"] and reopened["user_title"] == "Spesa Publix" and "<strong>Spesa Publix</strong>" in page,
          detail=str(reopened))

    # ------------------------------------------------------- an untitled rule
    status, saved = post("/bank/ai-rules/save", user_title="")
    rule_id = saved["rule_id"]
    page = client.get("/bank/ai-rules").data.decode()
    check("3. a rule saved without a Title: the list says so and keeps the number as reference",
          saved["ok"] and state(rule_id)["user_title"] is None and "No title" in page and f"#{rule_id} &middot;" in page,
          detail=str(saved))

    # ---------------------------------------------- the Title alone, on its own
    client.post("/bank/ai-rules/instructions", data={"csrf_token": csrf, "instructions": "Nuove istruzioni."})
    before, calls_before = state(rule_id), calls["n"]
    status, titled = post(f"/bank/ai-rules/rules/{rule_id}/title", user_title="Shop Title — acquisti")
    after = state(rule_id)
    unchanged = {k: v for k, v in before.items() if k != "user_title"}
    check("4. a Title added to an existing rule is saved alone: no AI call, no new version, no application, no "
          "decision, nothing else changed — even after the general instructions changed",
          status == 200 and titled["ok"] and after["user_title"] == "Shop Title — acquisti"
          and {k: v for k, v in after.items() if k != "user_title"} == unchanged and calls["n"] == calls_before,
          detail=f"{before} {after} calls={calls['n'] - calls_before}")

    page = client.get("/bank/ai-rules").data.decode()
    row = page[page.index(f'data-rule-id="{rule_id}"'):]
    row = row[:row.index("</tr>")]
    check("5. the list shows the Title as the main identifier and #id as the secondary reference",
          row.index("Shop Title — acquisti") < row.index(f"#{rule_id}")
          and '<strong class="ai-rule-name">Shop Title — acquisti</strong>' in row, detail=row[:300])
    check("5b. Delete names the rule by its Title", f'data-rule-name="Shop Title — acquisti (#{rule_id})"' in page)
    opened = client.get(f"/bank/ai-rules/rules/{rule_id}").get_json()
    check("6. opening the rule gives the Title back", opened["user_title"] == "Shop Title — acquisti")

    status, renamed = post(f"/bank/ai-rules/rules/{rule_id}/title", user_title="Shop Title")
    status, cleared = post(f"/bank/ai-rules/rules/{rule_id}/title", user_title="   ")
    check("7. the Title can be modified, and emptied", renamed["user_title"] == "Shop Title"
          and cleared["user_title"] == "" and state(rule_id)["user_title"] is None)

    # ----------------------------------------- Salva keeps / writes the Title
    status, resaved = post("/bank/ai-rules/save", rule_id=rule_id, user_title="Shop Title v2")
    check("8. Salva writes the Title typed in the window; the Title is not part of the version",
          resaved["ok"] and state(rule_id)["user_title"] == "Shop Title v2", detail=str(resaved))

    with SessionFactory() as s:
        from rfone_data_store.bank_reconciliation import ai_rule_operations
        ai_rule_operations.delete_rule(s, rule_id=rule_id, account_id=None)
        s.commit()
    status, refused = post(f"/bank/ai-rules/rules/{rule_id}/title", user_title="After delete")
    check("9. a deleted rule's Title cannot be changed", status == 400 and not refused["ok"]
          and state(rule_id)["user_title"] == "Shop Title v2", detail=str(refused))

    # ------------------------- the list's display order: Title A→Z, any case
    made = {}
    for title in ("zeta rule", "Alpha rule", "beta rule", ""):
        status, saved_rule = post("/bank/ai-rules/save", user_title=title)
        made[title or "(none)"] = saved_rule["rule_id"]

    def listed() -> list[int]:
        page_now = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
        return [int(x) for x in re.findall(r'<tr data-rule-id="(\d+)"', page_now)]

    check("10. the rules are listed by Title A→Z ignoring case, untitled rules last",
          listed() == [made["Alpha rule"], made["beta rule"], made["zeta rule"], made["(none)"]], detail=str(listed()))
    post(f"/bank/ai-rules/rules/{made['zeta rule']}/title", user_title="Aardvark rule")
    check("10b. after a Title change and a reload the order follows the new Title",
          listed() == [made["zeta rule"], made["Alpha rule"], made["beta rule"], made["(none)"]], detail=str(listed()))

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
