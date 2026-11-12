#!/usr/bin/env python
"""Publish job ad (SELECTION_PUBLISH_JOB_AD_001). ALL DATA IS SYNTHETIC, on a throwaway SQLite database.

Checks: on an Active Job, Publish job ad puts only the ad text live (application page and Careers
list); the confirmed requirements version and questions stay as they were; no candidate evaluation
and no full confirmation runs; the action is in the Job history; a Draft Job cannot use it.

    python test_publish_job_ad_http.py
"""

from __future__ import annotations

import html as html_lib
import os
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser

TMP = tempfile.mkdtemp(prefix="selection_publish_ad_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-publish-ad-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_SMTP_HOST",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV", "RFONE_SELECTION_ARUBA_KEY"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from workspace import routes  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

failures: list[str] = []
calls = {"analyze": 0, "approve": 0}


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


class FormReader(HTMLParser):
    """The values a browser would submit from the Job form (inputs, checked boxes, selects, textareas)."""

    def __init__(self):
        super().__init__()
        self.fields, self.textarea, self.select = {}, None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        name = a.get("name")
        if tag == "input" and name and (a.get("type") != "checkbox" or "checked" in a):
            self.fields[name] = a.get("value", "")
        elif tag == "textarea" and name:
            self.textarea = name
            self.fields[name] = ""
        elif tag == "select" and name:
            self.select = name
        elif tag == "option" and self.select and "selected" in a:
            self.fields[self.select] = a.get("value", "")

    def handle_data(self, data):
        if self.textarea:
            self.fields[self.textarea] += data

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.textarea = None
        elif tag == "select":
            self.select = None


try:
    with isolated_ai_client():
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
        home = owner.get("/selection/").get_data(as_text=True)
        t = (re.search(r'name="csrf_token" value="([^"]+)"', home) or
             re.search(r'name="csrf-token" content="([^"]+)"', home)).group(1)

        def job(pid):
            with selection_app.SessionFactory() as s:
                return s.get(ws.Position, pid)

        def new_job(role):
            r = owner.post("/selection/posizioni/nuova", data={
                "csrf_token": t, "title": "", "role_code": role, "location": "Mount Dora",
                "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(ids[0]),
                "description": ""}, follow_redirects=True)
            return int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))

        def job_form(pid):
            page = owner.get(f"/selection/posizioni/{pid}/job").get_data(as_text=True)
            reader = FormReader()
            reader.feed(page[page.index('id="job-form"'):])
            return page, {k: html_lib.unescape(v) for k, v in reader.fields.items()}

        def save(pid, action, **changes):
            _, data = job_form(pid)
            data.update(changes, csrf_token=t, action=action)
            return owner.post(f"/selection/posizioni/{pid}/job", data=data, follow_redirects=True)

        for role in ("FOOD_RUNNER", "SERVER"):
            pid = new_job(role)
            draft_html, _ = job_form(pid)
            check(f"{role}: a Draft Job has no Publish job ad button", 'value="publish_ad"' not in draft_html)
            save(pid, "draft", job_ad_en="Old ad text.")
            save(pid, "publish_ad")
            check(f"{role}: a Draft Job cannot use Publish job ad", job(pid).approved_job_ad_en is None)
            owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
                "csrf_token": t, "name": "Synthetic requirement", "description": "service",
                "criticality": "MUST_HAVE", "category": "Experience", "trainability": "TRAINABLE"})
            owner.post(f"/selection/posizioni/{pid}/dettagli", data={
                "csrf_token": t, "headcount": "1", "job_ad_en": "Old ad text.", "questions": "When could you start?"})
            owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
            before = job(pid)
            check(f"{role}: the Job is Active with the old ad",
                  before.status == "OPEN" and before.approved_job_ad_en == "Old ad text.",
                  f"{before.status} {before.approved_job_ad_en!r}")
            active_html, _ = job_form(pid)
            check(f"{role}: an Active Job shows Publish job ad", 'value="publish_ad"' in active_html)

            orig_analyze, orig_approve = routes.engine.analyze, routes._approve_position

            def fake_analyze(*a, **k):
                calls["analyze"] += 1

            def fake_approve(*a, **k):
                calls["approve"] += 1
                return True

            routes.engine.analyze, routes._approve_position = fake_analyze, fake_approve
            try:
                r = save(pid, "publish_ad", job_ad_en="New proper ad text for the website.",
                         questions="A question that is not confirmed?")
            finally:
                routes.engine.analyze, routes._approve_position = orig_analyze, orig_approve
            after = job(pid)
            check(f"{role}: the new ad is live", after.approved_job_ad_en == "New proper ad text for the website.")
            check(f"{role}: no candidate evaluation and no full confirmation ran",
                  calls == {"analyze": 0, "approve": 0}, str(calls))
            check(f"{role}: confirmed requirements version unchanged",
                  after.approved_snapshot_id == before.approved_snapshot_id)
            check(f"{role}: confirmed questions unchanged",
                  after.approved_questions_json == before.approved_questions_json
                  and "A question that is not confirmed?" not in after.approved_questions_json)
            page = owner.get(f"/selection/jobs/{after.public_token}").get_data(as_text=True)
            careers = owner.get("/selection/careers").get_data(as_text=True)
            check(f"{role}: application page and Careers list show the new ad",
                  "New proper ad text for the website." in page and "New proper ad text for the website." in careers)
            with selection_app.SessionFactory() as s:
                kinds = [e.kind for e in s.query(ws.WorkspaceEvent).filter_by(position_id=pid)]
            check(f"{role}: recorded in the Job history", "AD_PUBLISHED" in kinds)
            owner.post(f"/selection/posizioni/{pid}/stato", data={"csrf_token": t, "action": "close", "back": "/selection/"})
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
