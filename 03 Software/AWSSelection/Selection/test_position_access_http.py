#!/usr/bin/env python
"""Job (PDL) access answers (fix A1, 2026-11-15).

A missing Job answers 404, an existing Job outside the person's scope answers
403, an authorized Job is unchanged; the error page never answers 500 and never
shows the Job's data.  ALL DATA IS SYNTHETIC: throwaway SQLite database and
upload folder, deleted at the end; no AI, no email.

    python test_position_access_http.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="selection_access_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-access-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection import requirements_service as req  # noqa: E402
from workspace import routes  # noqa: E402
from workspace.role_catalog import JobRole  # noqa: E402

failures: list[str] = []
TITLE = "Synthetic Restricted Server Job"


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


try:
    app = selection_app.app
    with selection_app.SessionFactory() as db:
        ids = {}
        for username, admin, domain in (("owner", True, "SELECTION"), ("other", False, "SELECTION"),
                                        ("plain", False, "TIPS")):
            acc = account_svc.create_account(db, username=username, display_name=f"Synthetic {username.title()}",
                                             password="synthetic-password-1", is_admin=admin)
            account_svc.set_domain_access(db, account_id=acc.id, domain_code=domain, enabled=True, role_code=None)
            ids[username] = (acc.id, acc.session_version)
        db.commit()

    def client(username):
        c = app.test_client()
        with c.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = ids[username]
        return c

    with selection_app.SessionFactory() as db:
        db.add(JobRole(code="TEST_PDL", name="Synthetic PDL", name_key="synthetic-pdl", active=True, version=1))
        rs = req.create_requirement_set(db, restaurant_id=routes._restaurant_id(db), name="Synthetic", target_role="TEST_PDL")
        job = ws.Position(title=TITLE, role_code="TEST_PDL", location_label="Mount Dora", timezone="America/New_York",
                          status="OPEN", manager_account_id=ids["owner"][0], created_by_account_id=ids["owner"][0],
                          requirement_set_id=rs.id)
        db.add(job)
        db.commit()
        pid = job.id
    owner = client("owner")
    missing = pid + 1000

    paths = [f"/selection/posizioni/{{}}", f"/selection/posizioni/{{}}?tab=candidature",
             f"/selection/posizioni/{{}}/evaluation", f"/selection/posizioni/{{}}/sp/upload"]

    # Authorized Job: unchanged, help link right-aligned under the title divider still present.
    for path in paths:
        r = owner.get(path.format(pid))
        body = r.get_data(as_text=True)
        check(f"owner {path.format('<id>')} -> 200", r.status_code == 200, r.status_code)
        check(f"owner {path.format('<id>')} keeps the page help", 'id="selection-page-help"' in body)

    for who, expected in (("owner", 404), ("other", 404)):
        c = client(who)
        for path in paths:
            r = c.get(path.format(missing))
            body = r.get_data(as_text=True)
            check(f"{who} missing Job {path.format('<id>')} -> 404", r.status_code == expected, r.status_code)
            check(f"{who} missing Job error page keeps the help modal", 'id="selection-page-help"' in body)

    other = client("other")
    for path in paths:
        r = other.get(path.format(pid))
        body = r.get_data(as_text=True)
        check(f"other (not authorized) {path.format('<id>')} -> 403", r.status_code == 403, r.status_code)
        check(f"other {path.format('<id>')} shows no Job data", TITLE not in body and "Mount Dora" not in body)
        check(f"other {path.format('<id>')} error page keeps the help modal", 'id="selection-page-help"' in body)

    plain = client("plain")
    r = plain.get(f"/selection/posizioni/{pid}")
    body = r.get_data(as_text=True)
    check("account without Selection Domain is still refused (no 500)", r.status_code in (302, 401, 403),
          r.status_code)
    check("account without Selection Domain sees no Job data", TITLE not in body)
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
