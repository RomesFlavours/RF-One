"""Bank > AI Rules — SESSION mode interpreted automatically by the local Claude Code CLI (BANK_AI_RULES_012).

On a throwaway database, over HTTP. The CLI process is replaced INSIDE THIS TEST ONLY (`claude_code_cli._run` /
`subprocess.run`): no real CLI, no AI, no AWS is called.

* enabled only explicitly (RFONE_BANK_CLAUDE_CODE_CLI); unset → the preview waits for the session, as before;
* ONE preview request of a rule never interpreted → the CLI is asked once with the exact interpretation prompt,
  the answer is validated and saved (provider CLAUDE_CODE_CLI, its model), the rule runs by code and the preview
  is COMPLETED in that same request — no second click;
* the same text again: the saved interpretation is reused, the CLI is not asked;
* a partial answer (OTHER / unsupported) is BLOCKED, never executed in part;
* a CLI error, or an answer that is not JSON, makes the preview FAILED with the concrete reason; nothing saved;
* the CLI is run in print mode, with no tools, no session kept, a neutral folder and the configured model;
* the page names the CLI as the interpreter; nothing is applied to movements.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_cli_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-cli-secret"
os.environ["RFONE_BANK_AI_MODE"] = "SESSION"
os.environ.pop("RFONE_BANK_CLAUDE_CODE_CLI", None)
os.environ.pop("RFONE_BANK_CLAUDE_CODE_MODEL", None)

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
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import claude_code_cli  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = "Se la descrizione contiene “ACME SUPPLY”, assegna WHO “ACME SUPPLY”."
RULE_PARTIAL = "Se la descrizione contiene “ACME SUPPLY” e il giorno è festivo, assegna WHO “ACME SUPPLY”."
RULE_ERROR = "Se la descrizione contiene “ACME SUPPLY”, assegna WHO “ACME SUPPLY”. (errore CLI)"
RULE_NOT_JSON = "Se la descrizione contiene “ACME SUPPLY”, assegna WHO “ACME SUPPLY”. (non JSON)"
STRUCTURED = {"kind": "STRUCTURED",
              "conditions": [{"field": "description", "op": "contains", "value": "ACME SUPPLY"}],
              "who": {"mode": "fixed", "name": "ACME SUPPLY"}, "why": None, "for_whom": None, "status": None,
              "only_if_who_differs": False, "replace_existing": False, "branches": [], "unsupported": [],
              "coverage": [{"instruction": "contiene ACME SUPPLY → WHO ACME SUPPLY",
                            "represented_by": "condition + who.fixed"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_cli", display_name="AI CLI", password="AiCliPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_cli").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF CLI, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="CLI Checking", institution="CHASE", last_four="6001",
                                       currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        s.add(m.BankOccurrence(canonical_name="ACME SUPPLY", occurrence_type_id=counterparty.id, status="ACTIVE"))
        ids = []
        for i, text in enumerate(("ACME SUPPLY INV 1", "acme supply inv 2", "OTHER VENDOR"), start=1):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, i),
                transaction_date=date(2026, 9, i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"cli-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        s.commit()

    def provider_must_not_be_called(prompt):
        raise AssertionError("the AI provider must never be called in SESSION mode")

    ai_client.generate_json = provider_must_not_be_called
    calls: list[str] = []

    def fake_run(exe, prompt):
        calls.append(prompt)
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule == RULE_ERROR:
            return json.dumps({"type": "result", "subtype": "success", "is_error": True,
                               "result": "Invalid API key · Please run /login"})
        if rule == RULE_NOT_JSON:
            return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                               "result": "I think the rule means ACME."})
        if rule == RULE_PARTIAL:
            answer = {"kind": "OTHER", "reason": "“il giorno è festivo” cannot be expressed",
                      "coverage": STRUCTURED["coverage"], "unsupported": ["il giorno è festivo"]}
        else:
            answer = STRUCTURED
        return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                           "result": "```json\n" + json.dumps(answer) + "\n```"})

    claude_code_cli._run = fake_run
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_cli", "password": "AiCliPass123!", "csrf_token": csrf})
    page_url = "/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30"
    csrf = CSRF_RE.search(client.get(page_url).data.decode()).group(1)

    def preview(rule, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids[0]),
                "date_from": "2026-09-01", "date_to": "2026-09-30"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    def interpretations():
        with SessionFactory() as s:
            return s.scalar(select(func.count(m.BankAiRuleInterpretation.id)))

    def decisions():
        with SessionFactory() as s:
            return [s.get(m.FinancialTransaction, i).explanation_id for i in ids]

    before = decisions()
    # ---------------------------------------------------- not enabled: as before
    waiting = preview(RULE)
    check("1. not enabled: SESSION mode waits for the session, the CLI is not asked",
          not waiting.get("ok") and (waiting.get("error") or "").startswith(ai_rules.SESSION_WAIT_MARKER)
          and not calls and not claude_code_cli.available())

    # ---------------------------------------------------- enabled
    fake_exe = os.path.join(tempfile.gettempdir(), "rfone-test-fake-claude.exe")
    open(fake_exe, "w").close()
    os.environ["RFONE_BANK_CLAUDE_CODE_CLI"] = fake_exe
    os.environ["RFONE_BANK_CLAUDE_CODE_MODEL"] = "claude-opus-5-5"
    try:
        page = client.get(page_url).data.decode()
        check("2. enabled: the page names the local Claude Code CLI as the interpreter (no AWS)",
              'data-ai-provider="CLAUDE_CODE_CLI"' in page and "nessun provider AWS" in page)
        count_before = interpretations()
        one = preview(RULE)
        check("3. ONE request: the CLI is asked once with the exact prompt, the preview is COMPLETED by code",
              one.get("ok") and one.get("status") == "COMPLETED" and one.get("method") == "CODE" and len(calls) == 1
              and "RULE:\n" + RULE in calls[0] and "Translate the rule into conditions" in calls[0]
              and one.get("matches") == 2, detail=str({k: one.get(k) for k in ("status", "error", "matches")}))
        with SessionFactory() as s:
            saved = s.scalars(select(m.BankAiRuleInterpretation).order_by(m.BankAiRuleInterpretation.id.desc())).first()
            saved_info = (saved.provider, saved.model, saved.spec is not None)
        check("4. the interpretation is validated and saved as CLAUDE_CODE_CLI with its model; shown as such",
              saved_info == ("CLAUDE_CODE_CLI", "claude-opus-5-5", True) and interpretations() == count_before + 1
              and one.get("interpretation_provider") == "CLAUDE_CODE_CLI", detail=str(saved_info))
        calls.clear()
        again = preview(RULE)
        check("5. the same text again: reused, the CLI is not asked", again.get("ok") and not calls
              and again.get("interpretation_reused"))
        partial = preview(RULE_PARTIAL)
        check("6. a partial answer is BLOCKED with its reason, never executed in part",
              not partial.get("ok") and "Bloccata" in (partial.get("error") or "")
              and "festivo" in (partial.get("error") or "") and not partial.get("match_items"))
        count_before = interpretations()
        error = preview(RULE_ERROR)
        not_json = preview(RULE_NOT_JSON)
        check("7. a CLI error or a non-JSON answer: FAILED with the concrete reason, nothing saved",
              not error.get("ok") and "login" in (error.get("error") or "") and not not_json.get("ok")
              and "did not answer with JSON" in (not_json.get("error") or "") and interpretations() == count_before,
              detail=f"{error.get('error')} | {not_json.get('error')}")
        check("8. nothing is applied to movements", decisions() == before)

        captured = {}

        def fake_subprocess_run(args, **kwargs):
            captured.update(args=args, cwd=kwargs.get("cwd"), input=kwargs.get("input"))
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(
                {"type": "result", "subtype": "success", "is_error": False, "result": '{"kind": "OTHER"}'}), stderr="")

        real_run, real_subprocess_run = fake_run, subprocess.run
        del claude_code_cli._run                         # back to the module's own function
        import importlib
        importlib.reload(claude_code_cli)
        claude_code_cli.subprocess.run = fake_subprocess_run
        try:
            answer = claude_code_cli.generate_json("PROMPT")
        finally:
            claude_code_cli.subprocess.run = real_subprocess_run
        args = captured.get("args") or []
        check("9. the CLI runs in print mode, JSON output, no tools, no session kept, the model, a neutral folder",
              answer == {"kind": "OTHER"} and args[:2] == [fake_exe, "-p"] and "--no-session-persistence" in args
              and args[args.index("--tools") + 1] == "" and args[args.index("--model") + 1] == "claude-opus-5-5"
              and args[args.index("--output-format") + 1] == "json" and captured.get("input") == "PROMPT"
              and "rfone-bank-claude-code-cli" in (captured.get("cwd") or ""), detail=str(captured))
        _ = real_run
    finally:
        os.environ.pop("RFONE_BANK_CLAUDE_CODE_CLI", None)
        os.environ.pop("RFONE_BANK_CLAUDE_CODE_MODEL", None)
        try:
            os.remove(fake_exe)
        except OSError:
            pass
    check("10. 'off' and a missing path are not enabled",
          not claude_code_cli.available() and (os.environ.__setitem__("RFONE_BANK_CLAUDE_CODE_CLI", "off") or True)
          and not claude_code_cli.available()
          and (os.environ.__setitem__("RFONE_BANK_CLAUDE_CODE_CLI", r"C:\nowhere\claude.exe") or True)
          and not claude_code_cli.available())
    os.environ.pop("RFONE_BANK_CLAUDE_CODE_CLI", None)

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
