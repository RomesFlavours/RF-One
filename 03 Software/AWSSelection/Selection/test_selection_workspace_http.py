#!/usr/bin/env python
"""SELECTION_AI_INTEGRATION_001 — the integrated Selection, as deployed:
behind RF-One's login, under /selection/, on a throwaway SQLite database.
ALL DATA IS SYNTHETIC. No email leaves the process (the code sender is
replaced and the codes are read from it); no AI provider can be reached.

Essential path: RF-One login with an enabled account -> Selection ->
create and approve a position -> external access to the position page ->
registration and email verification -> résumé and online interview ->
the manager sees the application -> evaluation and decision.
Also: an RF-One account without SELECTION and an anonymous visitor are
refused; a signed-in candidate reaches no internal page; roles (owner,
supervisor, managers) are enforced server-side; a registered candidate
applies to a second position without registering again.

    python test_selection_workspace_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from datetime import timedelta
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_workspace_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-workspace-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision
provision(selection_app._engine)
from sqlalchemy import select  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, careers  # noqa: E402

CV_STRONG = """Jordan Example
jordan@example.test  (407) 555-0101

EXPERIENCE
Server, Trattoria Esempio, Orlando, FL | Mar 2021 - Present
- Table service for 40 covers, upselling wine
Food Runner, Bistro Prova, Orlando, FL | Jan 2019 - Feb 2021
- Ran food to tables
"""
CV_OTHER = """Casey Sample
casey@example.test

EXPERIENCE
Cashier, Store Demo, Tampa, FL | Jun 2020 - Present
- Cash register
"""
failures: list[str] = []
outbox: list[tuple[str, str]] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


def token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1)


def fake_deliver(*, to_address, full_name, code):
    outbox.append((to_address, code))


def last_code(email: str) -> str:
    return next(code for to, code in reversed(outbox) if to == email)


try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as s:
            accounts = {}
            for username, admin, domain, role in (("owner", True, "SELECTION", None), ("mgr", False, "SELECTION", None),
                                                  ("mgr2", False, "SELECTION", "MANAGER"),
                                                  ("sup", False, "SELECTION", "SUPERVISOR"),
                                                  ("plain", False, "TIPS", None)):
                acc = account_svc.create_account(s, username=username, display_name=f"Synthetic {username.title()}",
                                                 password="synthetic-password-1", is_admin=admin)
                account_svc.set_domain_access(s, account_id=acc.id, domain_code=domain, enabled=True, role_code=role)
                accounts[username] = (acc.id, acc.session_version)
            s.commit()

        def internal(username: str | None):
            client = app.test_client()
            if username:
                with client.session_transaction() as sess:
                    sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = accounts[username]
            return client

        # --- 1. RF-One login and Domain access ------------------------------
        anon = internal(None).get("/selection/")
        check("1. no RF-One session: sent to RF-One's login and back to Selection",
              anon.status_code == 302 and anon.headers["Location"] ==
              "https://rfone.example.test/login?next=%2Fselection%2F", anon.headers.get("Location"))
        check("1. an RF-One account without the SELECTION Domain gets 403",
              internal("plain").get("/selection/").status_code == 403)
        owner = internal("owner")
        home = owner.get("/selection/")
        html = text(home)
        check("1. an enabled account opens Selection on the Jobs list",
              home.status_code == 200 and '<html lang="en">' in html and "<h1>Jobs</h1>" in html)
        check("2. RF-One look: shell header, stylesheet, clickable path RF-One > Selection, loading indicator",
              'class="site-header"' in html and "css/rf-one.css" in html and "js/rf-one-busy.js" in html
              and 'href="https://rfone.example.test/">RF-One</a>' in html and '<span aria-current="page">Selection</span>' in html)
        check("2. no old Selection menu, no separate login or people page",
              "/selection/applications" not in html and "/selection/requirements" not in html
              and "Esci" not in html and "/persone" not in html)
        t = token(html)

        # --- 3. Create and approve a position (managed by mgr) ---------------
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "title": "Server", "role_code": "FOH_SUPERVISOR", "location": "Mount Dora",
            "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(accounts["mgr"][0]),
            "description": "We need a server."}, follow_redirects=True)
        # A Role without a CV Selection SP profile: Applications keeps the existing engines' proposal board.
        pid = int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))
        check('position management: a new Job is a Draft in the Jobs list, with Complete & Publish',
            re.search(rf'href="/selection/posizioni/{pid}/job" data-job-modal="[^"]*">Complete &amp; Publish</a>', text(owner.get('/selection/'))))
        config = text(owner.get(f'/selection/posizioni/{pid}?tab=configuration', follow_redirects=True))
        check('standard RF-One page: logo, breadcrumb, navigation; no Configuration tab',
            'shared-brand/logos/rf-one.png' in html and 'aria-label="Selection"' in html and
            'configuration-link' not in html and 'Configuration' not in html and 'AI for this Job' in config)
        check('position management: the Job settings (AI features) live in the Job form',
            'AI for this Job' not in html and 'name="feat_cv_evaluation"' in config)
        owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
            "csrf_token": t, "name": "Server experience", "description": "server waiter table service",
            "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
        owner.post(f"/selection/posizioni/{pid}/dettagli", data={
            "csrf_token": t, "headcount": "1", "job_ad_en": "Join our team in Mount Dora as a Server.",
            "questions": "Are you available to work weekends?\nWhen could you start?"})
        r = owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t}, follow_redirects=True)
        page = text(r)
        check("3. Job created and published: the application page is open",
              "Job active" in page and "/selection/jobs/" in page)
        check("3. the five steps are tabs at the same level",
              re.findall(r'>(Selection|Applications|Evaluation|Interviews|Decisions)</a>', page.split('aria-label="Selection"', 1)[1])
              == ["Selection", "Applications", "Evaluation", "Interviews", "Decisions"] and 'nav-tabs' in page)
        with selection_app.SessionFactory() as s:
            public_token = s.get(ws.Position, pid).public_token
        job_url = f"/selection/jobs/{public_token}"
        check('position management: approval publishes the position in the open list',
            f'/selection/posizioni/{pid}' in text(owner.get('/selection/')))
        check('position management: search filters positions',
            f'/selection/posizioni/{pid}' in text(owner.get('/selection/?q=server')) and
            'No results' in text(owner.get('/selection/?q=missing-synthetic-title')))
        r = owner.post(f'/selection/posizioni/{pid}/stato', data={'csrf_token': t, 'action': 'close',
            'back': '/selection/?stato=OPEN'})
        check('position management: close returns to the list, where the Job shows View history',
            r.location == '/selection/?stato=OPEN' and
            f'href="/selection/posizioni/{pid}?tab=decisioni">View history</a>' in text(owner.get('/selection/')))
        owner.post(f'/selection/posizioni/{pid}/stato', data={'csrf_token': t, 'action': 'reopen', 'back': '/selection/'})
        check('position management: reopen restores the existing approved application page',
            f'href="/selection/posizioni/{pid}?tab=candidature">Process</a>' in text(owner.get('/selection/')))
        check('position management: unknown state action is refused',
            owner.post(f'/selection/posizioni/{pid}/stato', data={'csrf_token': t, 'action': 'unknown'}).status_code == 400)

        # --- Roles, enforced server-side --------------------------------------
        mgr2 = internal("mgr2")
        check("roles: a manager does not see a position assigned to someone else",
              mgr2.get(f"/selection/posizioni/{pid}").status_code == 404
              and f"/selection/posizioni/{pid}" not in text(mgr2.get("/selection/")))
        sup = internal("sup")
        with sup.session_transaction() as sess:  # a supervisor's pages carry no form: give the session a token
            sup_t = sess[shared_session.SESSION_CSRF_KEY] = "synthetic-csrf"
        check("roles: a supervisor sees every position but cannot change it",
              sup.get(f"/selection/posizioni/{pid}").status_code == 200
              and sup.post(f"/selection/posizioni/{pid}/stato", data={"csrf_token": sup_t, "action": "close"}).status_code == 403)
        mgr = internal("mgr")
        check("roles: the assigned manager sees and manages the position",
              mgr.get(f"/selection/posizioni/{pid}").status_code == 200)

        # --- 4. External access to the position page -------------------------
        cand = app.test_client()
        page = text(cand.get(job_url))
        check("4. the public position page needs no RF-One login and asks to register first",
              "Join our team in Mount Dora" in page and "Receive Code" in page and "Full Name" in page
              and 'name="cv"' not in page)
        r = cand.post(job_url, data={"csrf_token": token(page), "consent": "1",
                                     "cv": (BytesIO(CV_STRONG.encode()), "jordan.txt")},
                      content_type="multipart/form-data", follow_redirects=True)
        check("4. applying without a verified identity is refused", "Please sign in or create your account" in text(r))
        ct = token(page)
        reg = {"csrf_token": ct, "full_name": "Jordan Example", "email": "Jordan@Example.test", "password": "synthetic-pass-1"}

        # --- 5. Registration and email verification --------------------------
        r = cand.post(f"{job_url}/account/code", data=reg)
        check("5. without a configured sender: explicit error, no code usable, verification not bypassed",
              r.status_code == 503 and "not configured" in r.get_json()["message"], r.get_data(as_text=True))
        careers.deliver_code = fake_deliver
        r = cand.post(f"{job_url}/account/code", data=dict(reg, password="short"))
        check("5. a password shorter than 10 characters is refused", "at least 10 characters" in r.get_json()["message"])
        r = cand.post(f"{job_url}/account/code", data=reg).get_json()
        check("5. Receive Code sends a code to the normalized address",
              r["ok"] and outbox and outbox[-1][0] == "jordan@example.test", r)
        r = cand.post(f"{job_url}/account/code", data=reg).get_json()
        check("5. a new code cannot be requested again within a minute", not r["ok"] and "wait" in r["message"], r)
        wrong = "000000" if last_code("jordan@example.test") != "000000" else "111111"
        r = cand.post(f"{job_url}/account/confirm", data={"csrf_token": ct, "email": "jordan@example.test", "code": wrong}).get_json()
        check("5. a wrong code is refused with the attempts left", not r["ok"] and "4 attempts left" in r["message"], r)
        with selection_app.SessionFactory() as s:
            stored = s.scalars(select(ws.CandidateEmailCode)).all()
            acc = s.scalars(select(ws.CandidateAccount)).one()
        check("5. neither the code nor the password is stored in clear",
              all(last_code("jordan@example.test") not in row.code_hmac for row in stored)
              and "synthetic-pass-1" not in acc.password_hash and acc.email_verified_at is None)
        r = cand.post(f"{job_url}/account/confirm", data={"csrf_token": ct, "email": "jordan@example.test",
                                                          "code": last_code("jordan@example.test")}).get_json()
        check("5. Confirm with the right code verifies the email and opens the application",
              r["ok"] and r["redirect"] == job_url, r)
        page = text(cand.get(job_url))
        check("5. the verified candidate now sees the résumé form", 'name="cv"' in page and "Applying as" in page)

        other = app.test_client()
        ot = token(text(other.get(job_url)))
        other.post(f"{job_url}/account/code", data={"csrf_token": ot, "full_name": "Casey Sample",
                                                    "email": "casey@example.test", "password": "synthetic-pass-2"})
        with selection_app.SessionFactory() as s:
            row = s.scalars(select(ws.CandidateEmailCode).order_by(ws.CandidateEmailCode.id.desc())).first()
            row.expires_at = ws.utcnow() - timedelta(minutes=1)
            s.commit()
        r = other.post(f"{job_url}/account/confirm", data={"csrf_token": ot, "email": "casey@example.test",
                                                           "code": last_code("casey@example.test")}).get_json()
        check("5. an expired code is refused with a clear message", not r["ok"] and "expired" in r["message"], r)
        with selection_app.SessionFactory() as s:
            row = s.scalars(select(ws.CandidateEmailCode).order_by(ws.CandidateEmailCode.id.desc())).first()
            row.created_at = ws.utcnow() - timedelta(minutes=2)  # past the cooldown
            s.commit()
        other.post(f"{job_url}/account/code", data={"csrf_token": ot, "full_name": "Casey Sample",
                                                    "email": "casey@example.test", "password": "synthetic-pass-2"})
        for _ in range(5):
            r = other.post(f"{job_url}/account/confirm", data={"csrf_token": ot, "email": "casey@example.test",
                                                               "code": "999999" if last_code("casey@example.test") != "999999" else "888888"}).get_json()
        check("5. after 5 wrong attempts the code is invalidated", "Too many wrong attempts" in r["message"], r)

        # --- Text message channel (same identity system) ---------------------
        sms = app.test_client()
        page = text(sms.get(job_url))
        st = token(page)
        sms_reg = {"csrf_token": st, "full_name": "Taylor Text", "email": "taylor@example.test",
                   "password": "synthetic-pass-3", "phone": "(407) 555-0188", "channel": "SMS"}
        r = sms.post(f"{job_url}/account/code", data=sms_reg)
        check("SMS: without a registered sender number Text Message is explicitly unavailable",
              r.status_code == 503 and "not available yet" in r.get_json()["message"]
              and "(not available yet)" in page)
        os.environ["RFONE_SMS_ORIGINATION_IDENTITY"] = "+18005550100"
        texts: list[tuple[str, str]] = []
        careers.deliver_sms_code = lambda *, to_number, code: texts.append((to_number, code))
        r = sms.post(f"{job_url}/account/code", data=dict(sms_reg, phone="12345")).get_json()
        check("SMS: an invalid US number is refused", not r["ok"] and "valid US mobile number" in r["message"], r)
        r = sms.post(f"{job_url}/account/code", data=dict(sms_reg, phone="")).get_json()
        check("SMS: Text Message needs a mobile number", not r["ok"] and "mobile number" in r["message"], r)
        r = sms.post(f"{job_url}/account/code", data=sms_reg).get_json()
        check("SMS: the code goes to the E.164 number, shown masked",
              r["ok"] and texts and texts[-1][0] == "+14075550188" and "(***) ***-0188" in r["message"], r)
        r = sms.post(f"{job_url}/account/confirm", data={"csrf_token": st, "email": "taylor@example.test",
                                                         "code": texts[-1][1]}).get_json()
        with selection_app.SessionFactory() as s:
            taylor = s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "taylor@example.test")).one()
        check("SMS: confirming verifies the phone, one identity, the candidate may apply",
              r["ok"] and taylor.phone_verified_at is not None and taylor.email_verified_at is None
              and 'name="cv"' in text(sms.get(job_url)))
        other_phone = app.test_client()
        ot2 = token(text(other_phone.get(job_url)))
        for i in range(6):
            with selection_app.SessionFactory() as s:  # skip the per-identity cooldown, keep the per-number count
                for row in s.scalars(select(ws.CandidateEmailCode)).all():
                    row.created_at = row.created_at - timedelta(seconds=61) if row.target == "+14075550188" else row.created_at
                s.commit()
            r = other_phone.post(f"{job_url}/account/code", data={"csrf_token": ot2, "full_name": f"Flood {i}",
                                 "email": f"flood{i}@example.test", "password": "synthetic-pass-4",
                                 "phone": "(407) 555-0188", "channel": "SMS"}).get_json()
        check("SMS: one number cannot be flooded through several registrations",
              not r["ok"] and "sent to this address or number" in r["message"], r)
        os.environ.pop("RFONE_SMS_ORIGINATION_IDENTITY", None)

        # --- A candidate never reaches an internal page ----------------------
        check("security: a signed-in candidate is sent to RF-One's login for internal pages",
              cand.get("/selection/").status_code == 302 and cand.get(f"/selection/posizioni/{pid}").status_code == 302
              and cand.get("/selection/candidates").status_code == 302)

        # --- 6. Résumé and online interview -----------------------------------
        page = text(cand.get(job_url))
        r = cand.post(job_url, data={"csrf_token": token(page), "phone": "(407) 555-0101", "consent": "1",
                                     "cv": (BytesIO(CV_STRONG.encode()), "jordan.txt")},
                      content_type="multipart/form-data")
        apply_url = r.headers.get("Location", "")
        check("6. the résumé is imported and the online interview starts", "/selection/my-application/" in apply_url, apply_url)
        page = text(cand.get(apply_url))
        check("6. the interview asks the approved standard questions", "Question 1 of 2" in page and "weekends" in page)
        os.environ["RFONE_PUBLIC_BASE_URL"] = "https://rfone.romesflavours.com"
        r = cand.post(apply_url, data={"csrf_token": token(page), "index": "0", "answer": "Yes, every weekend.",
                                       "input_mode": "TEXT", "action": "later"})
        check("6. save and finish later", "Your answers are saved" in text(r))
        check("6. resume link uses the official HTTPS host", "https://rfone.romesflavours.com" + job_url in text(r))
        os.environ.pop("RFONE_PUBLIC_BASE_URL", None)
        check("security: another candidate cannot open this application",
              other.get(apply_url).status_code in (302, 404))
        cand.post(f"{job_url}/sign-out", data={"csrf_token": token(text(cand.get(job_url)))})
        r = cand.get(apply_url)
        check("6. after signing out the application needs signing in again",
              r.status_code == 302 and job_url in r.headers["Location"])
        st = token(text(cand.get(job_url)))
        r = cand.post(f"{job_url}/sign-in", data={"csrf_token": st, "email": "jordan@example.test", "password": "wrong-password"},
                      follow_redirects=True)
        check("6. a wrong password is refused", "Email or password is not correct" in text(r))
        r = cand.post(f"{job_url}/sign-in", data={"csrf_token": st, "email": "JORDAN@example.test",
                                                  "password": "synthetic-pass-1"}, follow_redirects=True)
        check("6. sign-in with email and password, no second registration",
              "You have an application in progress" in text(r))
        page = text(cand.get(apply_url))
        check("6. the interview resumes at question 2", "Question 2 of 2" in page)
        cand.post(apply_url, data={"csrf_token": token(page), "index": "1", "answer": "I can start next Monday.",
                                   "input_mode": "VOICE", "action": "next"})
        page = text(cand.get(apply_url))
        page = text(cand.post(apply_url, data={"csrf_token": token(page), "action": "submit"}, follow_redirects=True))
        check("6. application sent", "your application is complete" in page)

        # --- 7. The manager sees the application ------------------------------
        page = text(mgr.get(f"/selection/posizioni/{pid}?tab=candidature"))
        check("7. the manager sees the application in Candidature", "Jordan Example" in page and "Application complete" in page)
        mt = token(page)
        page = text(mgr.get(f"/selection/posizioni/{pid}?tab=valutazione"))
        pc_id = int(re.search(r'name="pc_id" value="(\d+)"', page).group(1))
        check("8. evaluation proposes the candidate for interview",
              "Jordan Example" in page.split("Needs clarification <span")[0])
        cpage = text(mgr.get(f"/selection/posizioni/{pid}/candidati/{pc_id}"))
        check("7. the candidate page shows the verified identity and the answers",
              "verified identity" in cpage and "I can start next Monday." in cpage
              and '<a href="/selection/posizioni/%d/evaluation">Evaluation</a>' % pid in cpage)

        check("English manager pages and status labels", all(label in cpage for label in
              ("Candidate interview", "Communications", "Original résumé", "verified identity", "Application complete"))
              and "Valutazione" not in cpage and "Configurazione" not in cpage)
        check("English process tabs", all(f">{label}</a>" in page for label in
              ("Selection", "Applications", "Evaluation", "Interviews", "Decisions")) and "Position" not in page.split("<h1>", 1)[1][:40])

        # --- 8. Decision -------------------------------------------------------
        r = mgr.post(f"/selection/posizioni/{pid}/decisioni", data={"csrf_token": mt, "pc_id": str(pc_id), "decision": "HIRED"},
                     follow_redirects=True)
        page = text(mgr.get(f"/selection/posizioni/{pid}?tab=decisioni"))
        check("8. decision recorded with history", "1 / 1" in page and "Jordan Example: Send to Training" in page)

        config_url = f'/selection/posizioni/{pid}/configuration'
        check('configuration: legacy global page redirects to position list',
              owner.get('/selection/configurazione').status_code == 302
              and owner.get('/selection/configurazione').location == '/selection/')
        check('configuration: global profile updates are retired',
              owner.post('/selection/profilo-aziendale', data={'csrf_token': t, 'text': 'must not change'}).status_code == 410)
        config_supervisor = internal('sup')
        check('configuration: supervisor cannot save settings',
              config_supervisor.post(config_url, data={'csrf_token': token(text(config_supervisor.get('/selection/'))), 'profile': 'not allowed'}).status_code == 403)

        # --- Approved mail, Aruba outbox, retries and appointment confirmation --
        import hashlib, hmac, json, time
        from workspace import mail_delivery
        os.environ['RFONE_SELECTION_ARUBA_KEY'] = 'mail-synthetic-key-' + 'x' * 64
        def machine(path, fields):
            body = json.dumps(fields).encode()
            stamp = str(int(time.time()))
            sig = hmac.new(os.environ['RFONE_SELECTION_ARUBA_KEY'].encode(), stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
            return app.test_client().post('/selection/candidate/bridge/mail/' + path,
                data=body, content_type='application/json', headers={'X-RFOne-Time': stamp, 'X-RFOne-Signature': sig})
        base_pc = f'/selection/posizioni/{pid}/candidati/{pc_id}'
        mgr.post(base_pc + '/messaggi', data={'csrf_token': mt, 'kind': 'STUDY'})
        with selection_app.SessionFactory() as s:
            msg = s.scalars(select(ws.Message).where(ws.Message.position_candidate_id == pc_id).order_by(ws.Message.id.desc())).first()
            mid = msg.id
            check('mail: study invitation uses the existing menu link', '/training/menu' in msg.body)
            check('mail: drafts are never queued', not mail_delivery.rows_for(s, pc_id))
        message_url = f'/selection/posizioni/{pid}/messaggi/{mid}'
        mgr.post(message_url, data={'csrf_token': mt, 'action': 'send', 'body': 'x' * 16001})
        with selection_app.SessionFactory() as s:
            check('mail: oversized text stays editable and is not approved or queued',
                s.get(ws.Message, mid).status == 'DRAFT' and not mail_delivery.rows_for(s, pc_id))
        mgr.post(message_url, data={'csrf_token': mt, 'action': 'send'})
        mgr.post(message_url, data={'csrf_token': mt, 'action': 'send'})
        with selection_app.SessionFactory() as s:
            deliveries = mail_delivery.rows_for(s, pc_id)
            check('mail: approving twice queues exactly one email to the verified candidate',
                len(deliveries) == 1 and deliveries[0].recipient == 'jordan@example.test')
        check('mail: unsigned transport call refused', app.test_client().post('/selection/candidate/bridge/mail/claim', json={}).status_code == 403)
        item = machine('claim', {}).get_json()['item']
        check('mail: a leased email cannot be claimed twice', machine('claim', {}).get_json()['item'] is None)
        check('mail: wrong lease refused', machine('ack', {'id': item['id'], 'lease': 'wrong', 'outcome': 'sent'}).status_code == 403)
        check('mail: sent cannot be acknowledged before sending starts', machine('ack', dict(item, outcome='sent')).status_code == 409)
        check('mail: sender can start and confirm acceptance', machine('ack', dict(item, outcome='started')).status_code == 200 and
            machine('ack', dict(item, outcome='sent')).status_code == 200)
        check('mail: repeating the sent receipt is idempotent', machine('ack', dict(item, outcome='sent')).status_code == 200)
        check('mail: manager sees the transport outcome', 'Accepted by mail server' in text(mgr.get(base_pc)))
        with selection_app.SessionFactory() as s:
            pc = s.get(ws.PositionCandidate, pc_id)
            extra = mail_delivery.enqueue(s, pc=pc, source_key='synthetic:retry', subject='Synthetic test', body='Not sent')
            retry_id = extra.id
            s.commit()
        retry_item = machine('claim', {}).get_json()['item']
        machine('ack', dict(retry_item, outcome='failed', error='Synthetic connection failure'))
        check('mail: temporary failure respects backoff', machine('claim', {}).get_json()['item'] is None)
        with selection_app.SessionFactory() as s:
            row = s.get(mail_delivery.EmailOutbox, retry_id)
            row.next_attempt_at = ws.utcnow() - timedelta(seconds=1)
            s.commit()
        retry_item = machine('claim', {}).get_json()['item']
        machine('ack', dict(retry_item, outcome='started'))
        with selection_app.SessionFactory() as s:
            row = s.get(mail_delivery.EmailOutbox, retry_id)
            row.lease_expires_at = ws.utcnow() - timedelta(seconds=1)
            s.commit()
        check('mail: an ambiguous delivery is not automatically repeated', machine('claim', {}).get_json()['item'] is None)
        retry_url = base_pc + f'/email/{retry_id}/riprova'
        mgr.post(retry_url, data={'csrf_token': mt})
        with selection_app.SessionFactory() as s:
            check('mail: ambiguous retry requires an explicit manager decision', s.get(mail_delivery.EmailOutbox, retry_id).status == 'UNKNOWN')
        mgr.post(retry_url, data={'csrf_token': mt, 'confirm_retry': '1'})
        with selection_app.SessionFactory() as s:
            check('mail: the manager can requeue a checked delivery', s.get(mail_delivery.EmailOutbox, retry_id).status == 'QUEUED')
            # Keep this synthetic retry out of the appointment assertions.
            s.get(mail_delivery.EmailOutbox, retry_id).status = 'FAILED'
            s.commit()
        future = (ws.utcnow() + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M')
        mgr.post(base_pc + '/colloquio', data={'csrf_token': mt, 'kind': 'PHONE', 'duration': '30',
            'place': 'Synthetic phone', 'mode': 'offer', 'slot': future})
        with selection_app.SessionFactory() as s:
            offer = s.scalars(select(ws.SlotOffer).where(ws.SlotOffer.position_candidate_id == pc_id).order_by(ws.SlotOffer.id.desc())).first()
            offer_url = '/selection/interview/' + offer.token
            pick = offer.slots[0].isoformat(timespec='minutes')
        guest = app.test_client()
        csrf = token(text(guest.get(offer_url)))
        guest.post(offer_url, data={'csrf_token': csrf, 'slot': pick})
        guest.post(offer_url, data={'csrf_token': csrf, 'slot': pick})
        with selection_app.SessionFactory() as s:
            confirms = [r for r in mail_delivery.rows_for(s, pc_id) if r.source_key.startswith('appointment:')]
            check('mail: choosing an appointment queues one confirmation even after refresh', len(confirms) == 1)
        os.environ.pop('RFONE_SELECTION_ARUBA_KEY', None)

        # --- Same identity, second position ------------------------------------
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "title": "Food Runner", "role_code": "FOOD_RUNNER", "location": "Mount Dora",
            "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(accounts["owner"][0]),
            "description": "Runner"}, follow_redirects=True)
        pid2 = int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))
        owner.post(f"/selection/posizioni/{pid2}/requisiti/aggiungi", data={
            "csrf_token": t, "name": "Food running", "description": "runner food runner", "criticality": "PREFERRED",
            "category": "Experience", "trainability": "TRAINABLE"})
        owner.post(f"/selection/posizioni/{pid2}/dettagli", data={"csrf_token": t, "headcount": "1",
                                                                 "job_ad_en": "Food runner wanted.", "questions": "When could you start?"})
        owner.post(f"/selection/posizioni/{pid2}/approva", data={"csrf_token": t})
        with selection_app.SessionFactory() as s:
            job2 = f"/selection/jobs/{s.get(ws.Position, pid2).public_token}"
        page = text(cand.get(job2))
        check("the same signed-in candidate applies to a second position without registering again",
              'name="cv"' in page and "Receive Code" not in page)
        r = cand.post(job2, data={"csrf_token": token(page), "consent": "1", "cv": (BytesIO(CV_OTHER.encode()), "jordan2.txt")},
                      content_type="multipart/form-data")
        with selection_app.SessionFactory() as s:
            identities = s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "jordan@example.test")).all()
            pcs = s.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.candidate_account_id == identities[0].id)).all()
        check("one identity, two applications, each tied to its position",
              len(identities) == 1 and sorted(pc.position_id for pc in pcs) == [pid, pid2])
        r = cand.post(f"{job2}/account/code", data=dict(reg, csrf_token=token(text(cand.get(job2))))).get_json()
        check("registering an already verified email again is refused: sign in instead",
              not r["ok"] and r["already_registered"] and "sign in" in r["message"], r)

        # --- Historical Selection kept, outside the navigation -----------------
        from workspace import position_settings
        first_config = {'csrf_token': t, 'profile': 'FIRST POSITION: evening wine service only',
                        'position_drafting': '1', 'cv_questions': '1'}
        second_config = {'csrf_token': t, 'profile': 'SECOND POSITION: daytime food running only',
                         'message_drafting': '1', 'cv_evaluation': '1'}
        owner.post(f'/selection/posizioni/{pid}/configuration', data=first_config)
        owner.post(f'/selection/posizioni/{pid2}/configuration', data=second_config)
        with selection_app.SessionFactory() as db:
            p1, p2 = db.get(ws.Position, pid), db.get(ws.Position, pid2)
            c1, c2 = position_settings.get(p1), position_settings.get(p2)
            check('configuration: profiles and four feature preferences are independent',
                  c1['profile'] == first_config['profile'] and c2['profile'] == second_config['profile']
                  and c1['position_drafting'] and not c2['position_drafting']
                  and not c1['message_drafting'] and c2['message_drafting']
                  and c1['cv_questions'] and not c2['cv_questions']
                  and not c1['cv_evaluation'] and c2['cv_evaluation'])
            position_settings.bind(p1)
            check('configuration: a position cannot enable unauthorized AI processing',
                  not ai_adapter.current_policy().ai_enabled and not ai_adapter.current_policy().cv_ai_authorized)
            ai_adapter.reset_policy()
        first_page = text(owner.get(f'/selection/posizioni/{pid}?tab=configuration', follow_redirects=True))
        second_page = text(owner.get(f'/selection/posizioni/{pid2}?tab=configuration', follow_redirects=True))
        check('configuration: each position renders only its own context',
              first_config['profile'] in first_page and second_config['profile'] not in first_page
              and second_config['profile'] in second_page and first_config['profile'] not in second_page)
        check('configuration: another manager cannot change the position settings',
              mgr2.post(f'/selection/posizioni/{pid}/configuration', data={'csrf_token': token(text(mgr2.get('/selection/'))), 'profile': 'not allowed'}).status_code == 404)
        check('configuration: public candidates cannot change settings',
              cand.post(f'/selection/posizioni/{pid}/configuration', data={'csrf_token': token(text(cand.get(job_url))), 'profile': 'not allowed'}).status_code in (302, 400))

        r = owner.get("/selection/candidates")
        # SELECTION_OLD_ENTRY_001: entered from Home as "Selection Old", with its original menu.
        check("historical Selection pages still work, as Selection Old with their original menu",
              r.status_code == 200 and 'class="nav-tabs"' in text(r)
              and 'href="/selection/requirements"' in text(r) and 'Selection Old</a>' in text(r))

        # --- AI path with a FAKE transport (no network) -------------------------
        position_prompts = []
        def fake_ai(prompt):
            position_prompts.append(prompt)
            if "open a position" in prompt:
                return {"requirements": [{"name": "Esperienza ai tavoli", "description": "", "category": "Experience",
                                          "criticality": "MUST_HAVE", "trainability": "PARTIALLY_TRAINABLE",
                                          "cv_keywords": ["server"], "why": "from the description"}],
                        "headcount": 1, "job_ad_en": "We are hiring. [Pay: to be completed]", "open_questions": ["Pay?"]}
            raise AIProviderUnavailable("fake: not used")
        check("English AI prompts for position drafts and evaluations",
              "written in ENGLISH" in ai_adapter._POSITION_PROMPT and "in ITALIAN" not in ai_adapter._POSITION_PROMPT
              and "Write explanations and questions in ENGLISH" in ai_adapter._EVALUATION_PROMPT)
        ai_adapter._REAL_GENERATE_JSON = fake_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=False)
        r = owner.post("/selection/posizioni/nuova", data={
            "csrf_token": t, "title": "Server 2", "role_code": "SERVER", "location": "Mount Dora",
            "timezone": "America/New_York", "manager_account_id": str(accounts["owner"][0]), "description": "A server"},
            follow_redirects=True)
        new_pid = int(re.search(r"/selection/posizioni/(\d+)/job", r.request.path).group(1))
        with selection_app.SessionFactory() as db:
            check('AI activation: unconfigured positions stay disabled even when the installation is enabled',
                  not any(position_settings.get(db.get(ws.Position, new_pid))[key] for key, _, _ in position_settings.FEATURES))
        owner.post(f'/selection/posizioni/{new_pid}/configuration', data={'csrf_token': t, 'position_drafting': '1'})
        r = owner.post(f'/selection/posizioni/{new_pid}/ai-bozza', data={'csrf_token': t}, follow_redirects=True)
        check("AI drafts the position through Selection's AI client, shown for approval",
              "AI draft" in text(r) and "Pay?" in text(r))
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        with selection_app.SessionFactory() as db:
            policy1 = position_settings.bind(db.get(ws.Position, pid))
            policy2 = position_settings.bind(db.get(ws.Position, pid2))
            check('configuration: question and evaluation gates are independent per position',
                  policy1.allows('cv_questions') and not policy1.allows('cv_evaluation')
                  and not policy2.allows('cv_questions') and policy2.allows('cv_evaluation'))
            check('configuration: message and position drafting gates are independent',
                  policy1.allows('position_drafting') and not policy1.allows('message_drafting')
                  and not policy2.allows('position_drafting') and policy2.allows('message_drafting'))
            ai_adapter.reset_policy()
        position_prompts.clear()
        owner.post(f'/selection/posizioni/{pid}/ai-bozza' , data={'csrf_token': t})
        check('configuration: AI drafting consumes only the selected position context',
              len(position_prompts) == 1 and first_config['profile'] in position_prompts[0]
              and second_config['profile'] not in position_prompts[0])
        position_prompts.clear()
        owner.post(f'/selection/posizioni/{pid2}/ai-bozza', data={'csrf_token': t})
        check('configuration: disabling position drafts prevents calls without affecting other positions',
              not position_prompts)
        check('configuration: request policy does not leak into other requests',
              ai_adapter.current_policy() is ai_adapter.POLICY)
        if os.environ.get('RFONE_SELECTION_PREVIEW') == '1' and not failures:
            # Loopback-only visual review, with synthetic records and identity.
            from flask import request, session as preview_session, send_file
            os.environ['RFONE_WEB_BASE_URL'] = 'http://127.0.0.1:5098'
            app.config['SESSION_COOKIE_SECURE'] = False
            def preview_identity():
                if request.remote_addr != '127.0.0.1':
                    return 'Local preview only', 403
                preview_session[shared_session.SESSION_ACCOUNT_KEY], preview_session[shared_session.SESSION_VERSION_KEY] = accounts['owner']
                if request.path == '/shared-brand/logos/rf-one.png':
                    return send_file(r'C:\Users\servi\OneDrive\AI-RF-ONE\RF One\03 Software\Shared UI\brand\logos\rf-one.png')
            app.before_request_funcs.setdefault(None, []).insert(0, preview_identity)
            print('SYNTHETIC PREVIEW READY http://127.0.0.1:5098/selection/', flush=True)
            app.run(host='127.0.0.1', port=5098, debug=False, use_reloader=False)
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
