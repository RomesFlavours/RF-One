#!/usr/bin/env python
"""Open positions list (/selection/careers), shown inside the website's
Careers page. ALL DATA IS SYNTHETIC, on a throwaway SQLite database.

Checks: no RF-One login needed; only OPEN positions are listed, each with
its location and a link to its own public page in a new tab; closing a
position removes it and reopening brings it back; only the website (and the
Wix hosts) may show the page inside theirs; nothing internal leaks.

    python test_careers_openings_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="selection_openings_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-openings-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_SMTP_HOST",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV", "RFONE_SELECTION_ARUBA_KEY"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def token(html: str) -> str:
    return (re.search(r'name="csrf_token" value="([^"]+)"', html) or
            re.search(r'name="csrf-token" content="([^"]+)"', html)).group(1)


try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as s:
            acc = account_svc.create_account(s, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(s, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            owner_ids = (acc.id, acc.session_version)
            s.commit()
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_ids
        t = token(owner.get("/selection/").get_data(as_text=True))

        def new_position(title, location, ad, publish=True):
            r = owner.post("/selection/posizioni/nuova", data={
                "csrf_token": t, "title": title, "role_code": "SERVER", "location": location,
                "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(owner_ids[0]),
                "description": "Synthetic."}, follow_redirects=True)
            pid = int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))
            owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
                "csrf_token": t, "name": "Synthetic requirement", "description": "service",
                "criticality": "MUST_HAVE", "category": "Experience", "trainability": "TRAINABLE"})
            owner.post(f"/selection/posizioni/{pid}/dettagli", data={
                "csrf_token": t, "headcount": "1", "job_ad_en": ad, "questions": "When could you start?"})
            if publish:
                owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
            with selection_app.SessionFactory() as s:
                return pid, s.get(ws.Position, pid).public_token

        visitor = app.test_client()
        empty = visitor.get("/selection/careers")
        check("1. no open positions: friendly message, no RF-One login asked",
              empty.status_code == 200 and "no open roles right now" in empty.get_data(as_text=True))

        long_ad = "Join our opening team in Mount Dora. " + "We teach the menu and the wine list. " * 12
        p1, tok1 = new_position("Server", "Mount Dora", long_ad)
        p2, tok2 = new_position("Food Runner", "Winter Park", "Run food with care.")
        p3, tok3 = new_position("Host", "Winter Park", "Draft only.", publish=False)

        r = visitor.get("/selection/careers")
        html = r.get_data(as_text=True)
        check("2. lists every open position with title and location",
              "Server" in html and "Mount Dora" in html and "Food Runner" in html and "Winter Park" in html)
        check("2. a draft position is not listed", "Draft only." not in html and tok3 not in html)
        check("2. each Apply opens that position's own page in a new tab",
              f'href="/selection/jobs/{tok1}" target="_blank" rel="noopener"' in html
              and f'href="/selection/jobs/{tok2}" target="_blank" rel="noopener"' in html)
        check("2. a long job ad is shortened on the list, ending at a whole sentence",
              html.count("We teach the menu") < 12 and "the wine list.…" not in html and "…" not in html)
        check("2. sorted by location, then title", html.index("Mount Dora") < html.index("Winter Park"))
        check("2. nothing internal: no internal links, ids or RF-One header",
              "/selection/posizioni" not in html and "site-header" not in html and "csrf" not in html)

        csp = r.headers.get("Content-Security-Policy", "")
        check("3. only the website and the Wix hosts may show the list inside their page",
              csp.startswith("frame-ancestors ") and "https://www.romesflavours.com" in csp
              and "https://*.filesusr.com" in csp and "*" not in csp.replace("https://*.", ""), csp)
        check("3. not cached, not indexed",
              r.headers.get("Cache-Control") == "no-store" and "noindex" in r.headers.get("X-Robots-Tag", ""))

        owner.post(f"/selection/posizioni/{p2}/stato", data={"csrf_token": t, "action": "close", "back": "/selection/"})
        html = visitor.get("/selection/careers").get_data(as_text=True)
        check("4. closing a position removes it from the list at once", tok2 not in html and tok1 in html)
        owner.post(f"/selection/posizioni/{p2}/stato", data={"csrf_token": t, "action": "reopen", "back": "/selection/"})
        check("4. reopening brings it back", tok2 in visitor.get("/selection/careers").get_data(as_text=True))

        check("5. the job page itself is unchanged (no frame header added there)",
              "Content-Security-Policy" not in visitor.get(f"/selection/jobs/{tok1}").headers)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
