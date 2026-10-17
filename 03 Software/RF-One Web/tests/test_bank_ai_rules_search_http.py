"""Bank > AI Rules — the rules' search (BANK_AI_RULES_023).

On a throwaway database, over HTTP. No AI is called: the rules are written
directly, as saved operative rules with one version.

* a search field with "Search" to its right, on the same row, in the
  Operative AI Rules section; a GET form, so Enter and Search do the same;
* it filters the rules by name (the Title, or the automatic summary) and by
  content (the current version's text), ignoring case;
* an empty search shows every rule again;
* the period and "Classificazione" stay as they were, and the search stays
  through them and through Disable / Activate.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_search_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-search-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULES = [  # (user title, text)
    ("Spesa Publix", "Se la descrizione contiene “PUBLIX”, assegna WHO \"PUBLIX\"."),
    (None, "Se la descrizione comincia con “Zelle payment to”, il WHO è il testo fino a “JPM”."),
    ("Ristorante Season", "Se la descrizione contiene \"Season 52\", assegna WHO \"SEASON 52\"."),
]


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_search", display_name="AI Search", password="AiSearch123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_search").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        ids = []
        for title, text in RULES:
            rule = m.BankAiRule(title=" ".join(text.split())[:200], user_title=title, status="ACTIVE",
                                apply_future=False)
            s.add(rule)
            s.flush()
            s.add(m.BankAiRuleVersion(rule_id=rule.id, version_no=1, rule_text=text, create_missing_who=False,
                                      method=m.AI_RULE_METHOD_CODE, spec="{}"))
            ids.append(rule.id)
        s.commit()

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_search", "password": "AiSearch123!", "csrf_token": csrf})

    def shown(**args) -> tuple[set[int], str]:
        page = client.get("/bank/ai-rules", query_string=args).data.decode()
        section = page[page.index('id="ai-operative-rules"'):page.index('id="ai-rules-period"')]
        return {int(i) for i in re.findall(r'<tr data-rule-id="(\d+)"', section)}, page

    every, page = shown()
    form = page[page.index('class="compact-form filter-row review-search ai-rules-search"'):]
    form = form[:form.index("</form>")]
    check("1. a GET search form in the rules' section, Search to the right of the field (Enter submits it too)",
          'name="rule_q"' in form and form.index('name="rule_q"') < form.index(">Search</button>")
          and 'type="submit"' in form and every == set(ids))

    found, page = shown(rule_q="publix")
    check("2. by name/content, lower case finds “PUBLIX” and the Title “Spesa Publix”", found == {ids[0]},
          detail=str(found))
    found, _ = shown(rule_q="ZELLE PAYMENT")
    check("3. by content, upper case, on a rule without a Title", found == {ids[1]}, detail=str(found))
    found, page = shown(rule_q="ristorante")
    check("4. by the Title only (not in the text)", found == {ids[2]} and "1 rule of 3 found" in page.replace("<strong>", "")
          .replace("</strong>", ""), detail=str(found))
    found, page = shown(rule_q="assegna who")
    check("5. a text common to several rules shows each of them", found == {ids[0], ids[2]}, detail=str(found))
    found, page = shown(rule_q="nothing like this")
    check("6. no match: no rule, and the page says so", found == set() and "No rule matches your search" in page)
    found, page = shown(rule_q="   ")
    check("7. an empty search shows every rule again", found == set(ids) and "found for" not in page)

    found, page = shown(rule_q="publix", date_from="2026-09-01", date_to="2026-09-30", cls="no_who")
    period = page[page.index('id="ai-rules-period"'):]
    period = period[:period.index("</form>")]
    check("8. the search works together with the period and Classificazione", found == {ids[0]}, detail=str(found))
    search_form = page[page.index('ai-rules-search"'):]
    search_form = search_form[:search_form.index("</form>")]
    check("8b. the search form carries the period and Classificazione; the period form carries the search",
          'name="date_from" value="2026-09-01"' in search_form and 'name="cls" value="no_who"' in search_form
          and 'name="rule_q" value="publix"' in period, detail=search_form[:400])

    csrf = CSRF_RE.search(page).group(1)
    response = client.post(f"/bank/ai-rules/rules/{ids[0]}/status",
                           data={"csrf_token": csrf, "active": "0", "rule_q": "publix", "cls": "all"})
    check("9. Disable keeps the search on the way back, and the rule's behaviour is unchanged",
          response.status_code == 302 and "rule_q=publix" in response.headers["Location"])
    with SessionFactory() as s:
        check("9b. the rule was disabled exactly as before", s.get(m.BankAiRule, ids[0]).status == "INACTIVE")

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
