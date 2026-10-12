"""“+ New WHY Group” in the New WHY dialog (BANK_WHY_GROUP_CREATE_001).

Proves, on a throwaway database, that `POST /bank/whys/groups/create`:

* creates a WHY group from its name only — the code follows the catalog's
  UPPER_SNAKE convention, unique — and writes nothing else (no WHY, rule,
  classification);
* reuses the ACTIVE group of the same name (case / outer spaces aside),
  never duplicates it; similar names stay separate;
* refuses an empty name, a name held by an INACTIVE group (left unchanged),
  and a post without CSRF;
* the new group is offered to New WHY, which can save a WHY in it.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_why_group_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-why-group-secret"

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

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="groups", display_name="Groups",
                                           password="GroupsPass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="groups").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            s.add(m.BankReasonGroup(code="OLD_RETIRED", name="Old Retired", display_order=999, active=False))
            s.commit()

        def counts():
            with SessionFactory() as s:
                return {t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in (
                    m.BankReasonGroup, m.BankTransactionReason, m.BankRecognitionRule,
                    m.BankTransactionExplanation, m.BankOccurrenceReasonAssociation)}

        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "groups", "password": "GroupsPass123!", "csrf_token": csrf})
        page = client.get("/bank/review").data.decode()
        csrf = CSRF_RE.search(page).group(1)
        reconciled = client.get("/bank/review?view=reconciled").data.decode()
        # BANK_RULES_RESET_001: the old Rules page (/bank/classification) is
        # retired; the dialog lives on the Review pages that remain.
        check("1. New WHY offers + New WHY Group next to the group selector, with its dialog, on every page",
              all('id="why-group-new"' in h and ">+ New WHY Group</button>" in h and 'id="why-group-dialog"' in h
                  and 'id="why-group-name"' in h for h in (page, reconciled)))

        def create(name, with_csrf=True):
            data = {"name": name}
            if with_csrf:
                data["csrf_token"] = csrf
            return client.post("/bank/whys/groups/create", data=data, headers={"X-Requested-With": "fetch"})

        before = counts()
        resp = create("Business Travel")
        body = resp.get_json() or {}
        after = counts()
        with SessionFactory() as s:
            group = s.get(m.BankReasonGroup, body["group"]["id"]) if body.get("ok") else None
            shape = (group.code, group.name, group.active) if group else None
            last = s.scalar(select(func.max(m.BankReasonGroup.display_order)))
        check("2. the group is created from its name; the code follows the catalog convention",
              body.get("ok") and not body["reused"] and shape == ("BUSINESS_TRAVEL", "Business Travel", True)
              and group.display_order == last, str((body, shape)))
        check("3. only the group is written: no WHY, rule, classification or association",
              after["bank_reason_groups"] == before["bank_reason_groups"] + 1
              and all(after[k] == before[k] for k in after if k != "bank_reason_groups"), str((before, after)))
        for typed in ("business travel", "  BUSINESS TRAVEL  "):
            r = create(typed).get_json()
            check(f"4. “{typed}” is the same group: reused, no duplicate",
                  r["ok"] and r["reused"] and r["group"]["id"] == body["group"]["id"] and counts() == after)
        r = create("Business Travels").get_json()
        check("5. a merely similar name is a different group (not merged)", r["ok"] and not r["reused"]
              and r["group"]["id"] != body["group"]["id"])
        after = counts()
        for typed, why in (("   ", "empty"), ("old retired", "the name of an inactive group")):
            resp = create(typed)
            check(f"6. refused — {why} — nothing written", resp.status_code == 400 and counts() == after,
                  resp.get_data(as_text=True)[:200])
        with SessionFactory() as s:
            old = s.scalars(select(m.BankReasonGroup).where(m.BankReasonGroup.code == "OLD_RETIRED")).one()
        check("7. the inactive group is left unchanged", old.active is False and old.name == "Old Retired")
        resp = create("No Csrf Group", with_csrf=False)
        check("8. refused without CSRF", resp.status_code in (400, 403) and counts() == after)

        options = client.get("/bank/whys/create-options").get_json()
        check("9. the new group is offered to New WHY (alphabetical list)",
              any(g["name"] == "Business Travel" for g in options["groups"]))
        resp = client.post("/bank/whys/create", data={
            "csrf_token": csrf, "name": "Flights", "group_id": str(body["group"]["id"])},
            headers={"X-Requested-With": "fetch"})
        made = resp.get_json() or {}
        check("10. New WHY saves a WHY in the group just created (a separate step)",
              made.get("ok") and made["why"]["group_id"] == body["group"]["id"], str(made)[:200])
        check("11. still no transaction classified", counts()["bank_transaction_explanations"] == before["bank_transaction_explanations"])
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
