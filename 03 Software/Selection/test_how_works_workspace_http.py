#!/usr/bin/env python
"""Contextual help ("How … works" window) on the Selection workspace and on
the Selection Old pages that are not configuration lists.

Runs the real Flask app as deployed (behind RF-One's login, under
/selection/) on a throwaway SQLite database. ALL DATA IS SYNTHETIC. No
e-mail leaves the process (nothing is approved and sent) and no AI provider
can be reached (`isolated_ai_client`).

For every page reached it checks: status 200, the link opening the page's
own section (`data-how-works="<section>"`), the section itself
(`id="help-<section>"`), the label ("How Selection works" / "How Selection
Old works" on the module homes, "How this page works" elsewhere) and that
the help window is rendered exactly once. It also checks that help follows
page permissions (a supervisor's help does not offer the manager's buttons)
and that the full guide /how-it-works is assembled from the same sections.

The Acting Identity page exists only without the RF-One login: the script
re-runs itself in that mode (`--plain`) for that one page.

    python test_how_works_workspace_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO

PLAIN = "--plain" in sys.argv
TMP = tempfile.mkdtemp(prefix="selection_how_works_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-how-works-test-secret"
if PLAIN:
    os.environ.pop("RFONE_SELECTION_REQUIRE_RFONE_LOGIN", None)
    os.environ.pop("RFONE_WEB_BASE_URL", None)
else:
    os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
    os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
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

CV_A = """Jordan Example
jordan@example.test  (407) 555-0101

EXPERIENCE
Server, Trattoria Esempio, Orlando, FL | Mar 2021 - Present
- Table service for 40 covers, upselling wine
Food Runner, Bistro Prova, Orlando, FL | Jan 2019 - Feb 2021
- Ran food to tables
"""
CV_B = """Casey Sample
casey@example.test

EXPERIENCE
Server, Osteria Demo, Tampa, FL | Jun 2020 - Present
- Table service, trained two new servers
"""
CV_C = """Riley Placeholder
riley@example.test

EXPERIENCE
Waiter, Caffe Finto, Miami, FL | Feb 2018 - Present
- Table service and wine pairing
"""

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


def token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1)


def help_ok(client, url: str, section: str, label: str = "How this page works") -> str:
    r = client.get(url)
    html = text(r)
    checks = {
        "status 200": r.status_code == 200,
        "link": f'data-how-works="{section}"' in html,
        "section": f'id="help-{section}"' in html,
        "label": f">{label}</button>" in html,
        "one window": html.count('id="rf-help-dialog"') == 1,
    }
    bad = [k for k, ok in checks.items() if not ok]
    check(f"{url} -> {section}", not bad, f"status {r.status_code}; missing: {', '.join(bad)}")
    return html


def run_plain() -> None:
    """Acting Identity: reachable only without the RF-One login."""
    client = selection_app.app.test_client()
    help_ok(client, "/identity/switch", "selection-old-identity-switch")


def run_login_mode() -> None:
    app = selection_app.app
    with selection_app.SessionFactory() as s:
        accounts = {}
        for username, admin, role in (("owner", True, None), ("sup", False, "SUPERVISOR")):
            acc = account_svc.create_account(s, username=username, display_name=f"Synthetic {username.title()}",
                                             password="synthetic-password-1", is_admin=admin)
            account_svc.set_domain_access(s, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=role)
            accounts[username] = (acc.id, acc.session_version)
        s.commit()

    def internal(username: str):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = accounts[username]
        return client

    owner, sup = internal("owner"), internal("sup")

    # --- Selection workspace ------------------------------------------------
    home = help_ok(owner, "/selection/", "selection-dashboard", "How Selection works")
    check("module home help explains the flow and the owner's buttons",
          "<h2>How Selection works</h2>" in home and "<h3>Typical flow</h3>" in home and "<dt>+ New position</dt>" in home)
    check("the old guide link was replaced by the window (no second help link in the tabs)",
          "selection-help-link" not in home)
    help_ok(owner, "/selection/?stato=DRAFT", "selection-dashboard", "How Selection works")
    sup_home = help_ok(sup, "/selection/", "selection-dashboard", "How Selection works")
    check("permissions: a supervisor's help does not offer New position or Close / Reopen",
          "<dt>+ New position</dt>" not in sup_home and "<dt>Close / Reopen</dt>" not in sup_home
          and "Your access: <strong>read only</strong>" in sup_home)
    guide = text(owner.get("/selection/how-it-works"))
    check("the full guide still opens and is built from the same sections",
          "<h1>How Selection works</h1>" in guide
          and all(f'id="help-{s}"' in guide for s in (
              "selection-dashboard", "selection-position-new", "selection-position-setup",
              "selection-position-applications", "selection-position-evaluation", "selection-position-interviews",
              "selection-position-decisions", "selection-position-configuration", "selection-compare",
              "selection-candidate", "selection-cv-text"))
          and 'id="rf-help-dialog"' not in guide)

    t = token(home)
    help_ok(owner, "/selection/posizioni/nuova", "selection-position-new")
    r = owner.post("/selection/posizioni/nuova", data={
        "csrf_token": t, "title": "Server", "role_code": "SERVER", "location": "Mount Dora",
        "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(accounts["owner"][0]),
        "description": "We need a server."}, follow_redirects=True)
    pid = int(re.search(r"/selection/posizioni/(\d+)/requisiti/aggiungi", text(r)).group(1))
    owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
        "csrf_token": t, "name": "Server experience", "description": "server waiter table service",
        "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
    owner.post(f"/selection/posizioni/{pid}/dettagli", data={
        "csrf_token": t, "headcount": "1", "job_ad_en": "Join our team in Mount Dora as a Server.",
        "questions": "Are you available to work weekends?\nWhen could you start?"})
    owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
    owner.post(f"/selection/posizioni/{pid}/cv", data={
        "csrf_token": t, "cv": [(BytesIO(CV_A.encode()), "jordan.txt"), (BytesIO(CV_B.encode()), "casey.txt")]},
        content_type="multipart/form-data")

    base = f"/selection/posizioni/{pid}"
    for tab, section in (("posizione", "selection-position-setup"), ("candidature", "selection-position-applications"),
                         ("valutazione", "selection-position-evaluation"), ("colloqui", "selection-position-interviews"),
                         ("decisioni", "selection-position-decisions"),
                         ("configuration", "selection-position-configuration")):
        help_ok(owner, f"{base}?tab={tab}", section)
    help_ok(owner, f"{base}?tab=anything-else", "selection-position-decisions")
    evaluation = text(owner.get(f"{base}?tab=valutazione"))
    pc_ids = sorted(set(re.findall(r'name="pc_id" value="(\d+)"', evaluation)))
    check("two synthetic résumés were uploaded to the position", len(pc_ids) == 2, str(pc_ids))
    sup_setup = help_ok(sup, f"{base}?tab=posizione", "selection-position-setup")
    check("permissions: a supervisor's position help is read-only",
          "You can read this position but not change it." in sup_setup
          and "<dt>Approve and open position / Approve changes</dt>" not in sup_setup)
    if len(pc_ids) == 2:
        help_ok(owner, f"{base}/confronto?pc_id={pc_ids[0]}&pc_id={pc_ids[1]}", "selection-compare")
        cand = help_ok(owner, f"{base}/candidati/{pc_ids[0]}", "selection-candidate")
        check("candidate help keeps the page in English", "Valutazione" not in cand and "Configurazione" not in cand)
        sup_cand = help_ok(sup, f"{base}/candidati/{pc_ids[0]}", "selection-candidate")
        check("permissions: a supervisor's candidate help offers no booking, decision or sending",
              "<dt>Approve and send</dt>" not in sup_cand and "<dt>Approve and send</dt>" in cand)
        help_ok(owner, f"{base}/candidati/{pc_ids[0]}/testo", "selection-cv-text")

    # --- Selection Old ------------------------------------------------------
    old = help_ok(owner, "/selection/candidates", "selection-old-home", "How Selection Old works")
    check("Selection Old home help explains the flow", "<h3>Typical flow</h3>" in old)
    ups = []
    # Different people from the workspace résumés above (the same document would be a duplicate).
    old_cvs = [cv.replace(first, other).replace("example.test", "old.example.test")
               for cv, first, other in ((CV_A, "Jordan", "Alex"), (CV_B, "Casey", "Bea"), (CV_C, "Riley", "Cal"))]
    for name, cv in zip(("alex.txt", "bea.txt", "cal.txt"), old_cvs):
        ups.append(owner.post("/selection/api/upload", data={
            "target_role": "SERVER", "resume_file": (BytesIO(cv.encode()), name)},
            content_type="multipart/form-data").get_json())
    check("synthetic résumés imported in Selection Old", all(u and u.get("status") == "COMPLETED" for u in ups), str(ups))
    cid, aid = ups[0]["candidate_id"], ups[0]["application_id"]
    help_ok(owner, f"/selection/candidate/{cid}", "selection-old-candidate")
    help_ok(owner, "/selection/applications", "selection-old-applications")
    help_ok(owner, f"/selection/applications/compare?ids={ups[0]['application_id']}&ids={ups[1]['application_id']}",
            "selection-old-applications-compare")
    help_ok(owner, f"/selection/applications/{aid}", "selection-old-application")
    help_ok(owner, f"/selection/applications/{aid}/dossier", "selection-old-dossier")
    decision = help_ok(owner, f"/selection/applications/{aid}/decision", "selection-old-decision-summary")
    check("login mode: the decision help offers no identity switching", "not you?" not in decision and "(switch)" not in decision)
    help_ok(owner, f"/selection/applications/{aid}/audit", "selection-old-audit")
    help_ok(owner, f"/selection/applications/{aid}/communications", "selection-old-communications")
    help_ok(owner, "/selection/identity-matches", "selection-old-identity-matches")

    r = owner.post("/selection/requirements/new-custom", data={"name": "Synthetic server set", "target_role": "SERVER"})
    rs_id = int(re.search(r"/requirements/(\d+)", r.headers["Location"]).group(1))
    r = owner.post(f"/selection/candidate/{cid}/fit-assessments", data={"requirement_set_id": str(rs_id)})
    fa = re.search(r"/fit-assessments/(\d+)", r.headers.get("Location", ""))
    check("a fit assessment was created", fa is not None, r.headers.get("Location"))
    if fa:
        help_ok(owner, f"/selection/fit-assessments/{fa.group(1)}", "selection-old-fit-assessment")

    r = owner.post("/selection/sessions/new", data={"name": "Synthetic session", "target_role": "SERVER"})
    sid = re.search(r"/sessions/(\d+)", r.headers.get("Location", ""))
    jp = None
    if sid:
        r = owner.post(f"/selection/sessions/{sid.group(1)}/job-postings/generate", data={"created_by": "Synthetic"})
        jp = re.search(r"/job-postings/(\d+)", r.headers.get("Location", ""))
    check("a job posting was generated", jp is not None, r.headers.get("Location"))
    if jp:
        help_ok(owner, f"/selection/job-postings/{jp.group(1)}", "selection-old-job-posting")


try:
    with isolated_ai_client():
        if PLAIN:
            run_plain()
        else:
            run_login_mode()
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

if not PLAIN:
    plain = subprocess.run([sys.executable, os.path.abspath(__file__), "--plain"], capture_output=True, text=True,
                           cwd=os.path.dirname(os.path.abspath(__file__)))
    print(plain.stdout.strip())
    if plain.returncode != 0:
        failures.append("plain mode (Acting Identity)")
        print(plain.stderr[-2000:])
    print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
