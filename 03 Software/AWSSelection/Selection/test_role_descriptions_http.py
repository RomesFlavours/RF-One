#!/usr/bin/env python
"""Default Job descriptions per Role. ALL DATA IS SYNTHETIC, on a throwaway SQLite database.

Checks: every Role in the list has a default description; a new Job with an empty
description gets its Role's default; text the manager wrote is kept; changing the
Role of a Draft swaps a default description but never the manager's own text;
the New Job form carries the defaults; Role names are capitalized.

    python test_role_descriptions_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="selection_role_desc_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-role-desc-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_SMTP_HOST",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV", "RFONE_SELECTION_ARUBA_KEY"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from workspace import routes  # noqa: E402
from workspace.role_descriptions import ROLE_DESCRIPTIONS  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


try:
    with isolated_ai_client():
        check("1. every Role in the list has a default description",
              set(code for code, _ in routes.ROLE_CHOICES) == set(ROLE_DESCRIPTIONS), "")
        check("1. no em dashes in the defaults", not any("—" in t for t in ROLE_DESCRIPTIONS.values()))
        check("1. Role names are capitalized",
              routes.ROLE_LABEL["FOOD_RUNNER"] == "Food Runner" and routes.ROLE_LABEL["LINE_COOK"] == "Line Cook"
              and routes.ROLE_LABEL["GENERAL_MANAGER"] == "General Manager")

        app = selection_app.app
        with selection_app.SessionFactory() as s:
            acc = account_svc.create_account(s, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(s, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            ids = (acc.id, acc.session_version)
            s.commit()
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = ids
        page = owner.get("/selection/posizioni/nuova").get_data(as_text=True)
        t = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        check("2. the New Job form carries the defaults", "No experience is required; we teach you the menu." in page)

        def new_job(role, description=""):
            r = owner.post("/selection/posizioni/nuova", data={
                "csrf_token": t, "title": "", "role_code": role, "location": "Mount Dora",
                "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(ids[0]),
                "description": description}, follow_redirects=True)
            return int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))

        def job(pid):
            with selection_app.SessionFactory() as s:
                return s.get(ws.Position, pid)

        p1 = new_job("FOOD_RUNNER")
        check("3. empty description: the Role's default is saved", job(p1).description == ROLE_DESCRIPTIONS["FOOD_RUNNER"])
        check("3. empty title: the capitalized Role name", job(p1).title == "Food Runner")
        form = owner.get(f"/selection/posizioni/{p1}/job").get_data(as_text=True)
        check("3. the Job form shows the description", "check every plate before it leaves" in form)

        p2 = new_job("SERVER", "Evenings and weekends, two people.")
        check("4. the manager's own text is kept", job(p2).description == "Evenings and weekends, two people.")

        def change_role(pid, role, description):
            owner.post(f"/selection/posizioni/{pid}/job", data={
                "csrf_token": t, "role_code": role, "location": "Mount Dora", "timezone": "America/New_York",
                "title": "", "headcount": "1", "description": description, "questions": ""})

        change_role(p1, "BUSSER", ROLE_DESCRIPTIONS["FOOD_RUNNER"])
        check("5. Role change swaps a default description", job(p1).description == ROLE_DESCRIPTIONS["BUSSER"])
        change_role(p2, "HOST", "Evenings and weekends, two people.")
        check("5. Role change never overwrites the manager's text",
              job(p2).description == "Evenings and weekends, two people." and job(p2).role_code == "HOST")
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
