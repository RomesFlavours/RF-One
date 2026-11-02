#!/usr/bin/env python
"""How Works on the five Selection tabs (UI_HOW_WORKS_001, `03 Software/Shared UI/How Works Standard.md`).
ALL DATA IS SYNTHETIC. Throwaway SQLite database, AI off (no network), no email.

Each tab — Selection, Applications, Evaluation, Interviews, Decisions — and the candidate dossier shows one
visible "How Works" link that opens its own section of "How Selection works", never the top of the guide; the
section exists; the Applications section explains CV upload, duplicates, the SP analysis, the ranking, Reject
and Restore. A Role without a CV Selection SP profile gets the same Applications link.

    python test_how_works_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_how_works_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-how-works-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace.sp import profiles as spp  # noqa: E402
from workspace.sp import rules as sp_rules  # noqa: E402

failures: list[str] = []
GUIDE = "/selection/how-it-works"


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


def nav(html: str) -> str:
    m = re.search(r'<nav class="nav-tabs selection-navigation".*?</nav>', html, re.S)
    return m.group(0) if m else ""


def how_works(html: str) -> tuple[str, str, str] | None:
    """(data-how-works, href, visible label) of the page's How Works link, if any."""
    m = re.search(r'<a class="selection-help-link" data-how-works="([^"]*)" href="([^"]*)"[^>]*>([^<]*)</a>', nav(html))
    return m.groups() if m else None


def tab_hrefs(html: str) -> dict[str, str]:
    return {label: href for href, label in
            re.findall(r'<a href="([^"]+)" class="[^"]*">(Selection|Applications|Evaluation|Interviews|Decisions)</a>',
                       nav(html))}


try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as db:
            acc = account_svc.create_account(db, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(db, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            db.commit()
            owner_id = (acc.id, acc.session_version)
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_id
        t = re.search(r'name="csrf_token" value="([^"]+)"', text(owner.get("/selection/posizioni/nuova"))).group(1)

        # A published Server Job (CV Selection SP role), AI off, and one uploaded CV.
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "role_code": "SERVER", "location": "Mount Dora", "headcount": "1",
            "timezone": "America/New_York", "manager_account_id": str(owner_id[0]), "description": "Synthetic Job."})
        pid = int(re.search(r"/selection/posizioni/(\d+)/job", r.headers["Location"]).group(1))
        data = {"csrf_token": t, "role_code": "SERVER", "location": "Mount Dora", "headcount": "1", "title": "Server",
                "timezone": "America/New_York", "description": "Synthetic Job.", "job_ad_en": "Synthetic ad.",
                "questions": "When could you start?", "profile": "Evening table service.", "action": "publish"}
        for req in spp.default_requirements("SERVER"):
            data.update({f"sp_crit_{req['id']}": req["criticality"], f"sp_weight_{req['id']}": str(req["weight"]),
                         f"sp_active_{req['id']}": "1"})
        for rule in sp_rules.defaults("SERVER"):
            data[f"rule_{rule}"] = "1"
        owner.post(f"/selection/posizioni/{pid}/job", data=data)
        owner.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "cv": [(BytesIO(
            b"Ava Sample\nava@example.test\n\nEXPERIENCE\nServer, Trattoria Esempio, Mount Dora, FL | Jan 2023 - Present\n"),
            "ava.txt")]}, content_type="multipart/form-data")

        guide = text(owner.get(GUIDE))
        applications = text(owner.get(f"/selection/posizioni/{pid}/sp"))
        hrefs = tab_hrefs(applications)
        check("0. Job published and the five tabs are reachable from Applications",
              set(hrefs) == {"Selection", "Applications", "Evaluation", "Interviews", "Decisions"}, hrefs)

        # 1-5. Each tab: one visible How Works link to its own section, and the section exists.
        for i, (label, code) in enumerate([("Selection", "selection"), ("Applications", "applications"),
                                           ("Evaluation", "evaluation"), ("Interviews", "interviews"),
                                           ("Decisions", "decisions")], start=1):
            page = text(owner.get(hrefs.get(label, "/selection/")))
            link = how_works(page)
            check(f"{i}. {label}: 'How Works' opens {GUIDE}#{code} and the guide has that section",
                  link == (code, f"{GUIDE}#{code}", "How Works") and nav(page).count("selection-help-link") == 1
                  and f'<section class="card" id="{code}">' in guide and f'class="active">{label}<' in nav(page), link)

        # 6. The candidate dossier belongs to Evaluation.
        pc_id = re.search(rf"/selection/posizioni/{pid}/candidati/(\d+)", text(owner.get(hrefs["Evaluation"])))
        dossier = text(owner.get(f"/selection/posizioni/{pid}/candidati/{pc_id.group(1)}")) if pc_id else ""
        check("6. Candidate dossier: 'How Works' opens the Evaluation section",
              how_works(dossier) == ("evaluation", f"{GUIDE}#evaluation", "How Works"), how_works(dossier))

        # 7. The Applications section explains what the Applications page does.
        section = re.search(r'<section class="card" id="applications">(.*?)</section>', guide, re.S)
        body = section.group(1) if section else ""
        topics = {"CV upload": "Upload CVs", "duplicates": "Exact duplicate", "possible duplicates": "Possible duplicate",
                  "SP analysis": "CV Selection SP", "analyze": "Re-analyze all", "ranking": "<h3>Ranking</h3>",
                  "reorder": "▲▼", "last upload": "Last Upload", "Reject": "<b>Reject</b>", "Restore": "<b>Restore</b>"}
        check("7. Applications Help explains upload, duplicates, SP analysis, ranking, Reject and Restore",
              all(v in body for v in topics.values()), [k for k, v in topics.items() if v not in body])

        # 8. The guide is reachable, with breadcrumb, and every tab code has exactly one section.
        check("8. Guide: one section per tab, in the RF-One shell with its breadcrumb",
              all(guide.count(f'id="{c}"') == 1 for c in ("selection", "applications", "evaluation", "interviews",
                                                         "decisions"))
              and "How Selection works" in guide and 'class="breadcrumb"' in guide)

        # 9. A Role without a CV Selection SP profile: Applications is position.html, same link.
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "role_code": "DISHWASHER", "location": "Mount Dora", "headcount": "1",
            "timezone": "America/New_York", "manager_account_id": str(owner_id[0]), "description": "Synthetic Job."})
        other = int(re.search(r"/selection/posizioni/(\d+)/job", r.headers["Location"]).group(1))
        page = text(owner.get(f"/selection/posizioni/{other}?tab=candidature"))
        check("9. Role without SP profile: Applications shows the same 'How Works' link",
              how_works(page) == ("applications", f"{GUIDE}#applications", "How Works"), how_works(page))
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("RESULT:", "ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
