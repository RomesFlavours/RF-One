#!/usr/bin/env python
"""SELECTION_ARUBA_IDENTITY_001 — candidate identification on the careers
page hosted on Aruba, end to end. ALL DATA IS SYNTHETIC.

The real PHP pages (`aruba-careers/upload/`) run in PHP's built-in server and
send their codes over implicit TLS, with certificate verification, to a fake
SMTP server inside this process (nothing leaves the PC). Selection runs as
deployed (RF-One login, /selection/) on a throwaway SQLite database.

Path: job posting -> careers page (First Name, Last Name, Email, Receive
Code) -> emailed 5-digit code -> Welcome, <First Name>! -> Confirm -> signed
single-use token posted to Selection -> résumé and interview saved
(In Progress) -> the candidate comes back, verifies again and resumes the
same application -> Completed. Also: wrong/expired/exhausted codes, Cancel,
repeated requests, no code or personal data in URLs or logs, forged,
replayed, expired or misaddressed tokens, access limited to the token's
position, no password identity.

    python test_aruba_identity_http.py          (PHP from PATH or RFONE_TEST_PHP)
"""

from __future__ import annotations

import base64
import html as html_lib
import json
import os
import re
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
UPLOAD = HERE / "aruba-careers" / "upload"
SECRET = "synthetic-handoff-secret-" + "x" * 24
TMP = Path(tempfile.mkdtemp(prefix="selection_aruba_identity_test_"))
SELECTION_HANDOFF = "http://selection.test/selection/careers/verified-identity"
IDENTITY_URL = "https://careers.example.test/index.php"

os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{(TMP / 'rfone.db').as_posix()}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-aruba-identity-test-secret"
os.environ["RFONE_SELECTION_CANDIDATE_IDENTITY_URL"] = IDENTITY_URL
os.environ["RFONE_SELECTION_IDENTITY_HANDOFF_SECRET"] = SECRET
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import identity_handoff_service as handoff  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

CV = """Jordan Example
jordan@example.test  (407) 555-0101

EXPERIENCE
Server, Trattoria Esempio, Orlando, FL | Mar 2021 - Present
- Table service for 40 covers, upselling wine
"""
SMTP_USER, SMTP_PASSWORD = "rfone@romesflavours.com", "synthetic-mailbox-password"
failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{str(detail)[:300]}]"))
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------------------
# Fake SMTP server with implicit TLS (like smtps.aruba.it:465)
# ---------------------------------------------------------------------------

class Mailbox:
    messages: list[dict] = []
    logins: list[tuple[str, str]] = []
    accept_password = SMTP_PASSWORD


class SmtpHandler(socketserver.StreamRequestHandler):
    def send(self, line: str):
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        self.send("220 fake-smtps ready")
        state, user, mail_from, rcpt = None, None, None, []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode().rstrip("\r\n")
            if state == "user":
                user, state = base64.b64decode(line).decode(), "password"
                self.send("334 UGFzc3dvcmQ6")
            elif state == "password":
                password, state = base64.b64decode(line).decode(), None
                Mailbox.logins.append((user, password))
                self.send("235 ok" if (user, password) == (SMTP_USER, Mailbox.accept_password) else "535 auth failed")
            elif line.upper().startswith("EHLO"):
                self.send("250-fake-smtps")
                self.send("250 AUTH LOGIN PLAIN")
            elif line.upper() == "AUTH LOGIN":
                state = "user"
                self.send("334 VXNlcm5hbWU6")
            elif line.upper().startswith("MAIL FROM:"):
                mail_from, rcpt = line[10:].strip("<>"), []
                self.send("250 ok")
            elif line.upper().startswith("RCPT TO:"):
                rcpt.append(line[8:].strip("<>"))
                self.send("250 ok")
            elif line.upper() == "DATA":
                self.send("354 go")
                data = b""
                while not data.endswith(b"\r\n.\r\n"):
                    chunk = self.rfile.readline()
                    if not chunk:
                        return
                    data += chunk
                Mailbox.messages.append({"from": mail_from, "to": rcpt, "data": data.decode()})
                self.send("250 queued")
            elif line.upper() == "QUIT":
                self.send("221 bye")
                return
            else:
                self.send("502 unknown")


class TlsServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, handler, context):
        super().__init__(addr, handler)
        self.context = context

    def get_request(self):
        sock, addr = super().get_request()
        return self.context.wrap_socket(sock, server_side=True), addr


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_php() -> str | None:
    return os.environ.get("RFONE_TEST_PHP") or shutil.which("php")


def mail_code(to: str) -> str:
    message = next(m for m in reversed(Mailbox.messages) if m["to"] == [to])
    return re.search(r"Your verification code is: (\d+)", message["data"]).group(1)


HANDOFF_URL = "/selection/careers/verified-identity"


def deliver(client, token: str, query: str = ""):
    """What the browser does: the careers page posts the token (step 1, from
    another site), Selection's own page posts it again (step 2)."""
    first = client.post(HANDOFF_URL + query, data={"identity_token": token} if token is not None else {})
    found = re.search(r'name="identity_token" value="([^"]*)"', first.get_data(as_text=True))
    again = html_lib.unescape(found.group(1)) if found else ""
    return first, client.post(HANDOFF_URL, data={"identity_token": again, "step": "continue"})


def csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


# ---------------------------------------------------------------------------

php = find_php()
php_proc = smtp = None
try:
    if php is None:
        raise SystemExit("PHP not found: set RFONE_TEST_PHP to php.exe (the careers page is PHP).")
    # --- Test environment: certificate, fake SMTPS, PHP server ---------------
    cert, key = TMP / "cert.pem", TMP / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                   check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    smtp_port = free_port()
    smtp = TlsServer(("127.0.0.1", smtp_port), SmtpHandler, context)
    threading.Thread(target=smtp.serve_forever, daemon=True).start()

    # The FTP root of Aruba Hosting Windows: the careers folder next to Aruba's protected mdb-database folder.
    ftp_root = TMP / "aruba"
    docroot = ftp_root / "careers"
    shutil.copytree(UPLOAD, docroot)
    (ftp_root / "mdb-database").mkdir()
    data_dir = ftp_root / "mdb-database" / "rfone-careers"
    config = (UPLOAD / "private" / "config.sample.php").read_text(encoding="utf-8")
    config = (config.replace("'handoff_secret' => 'CHANGE-ME'", f"'handoff_secret' => '{SECRET}'")
              .replace("'password' => '',", f"'password' => '{SMTP_PASSWORD}',")
              .replace("'host' => 'smtps.aruba.it'", "'host' => 'localhost'")
              .replace("'port' => 465", f"'port' => {smtp_port}")
              .replace("'cafile' => null", f"'cafile' => '{cert.as_posix()}'")
              .replace("'require_https' => true", "'require_https' => false")
              .replace("'diagnostics_key' => ''", "'diagnostics_key' => 'synthetic-diagnostics-key'")
              .replace("https://rfone.romesflavours.com/selection/careers/verified-identity", SELECTION_HANDOFF))
    (docroot / "private" / "config.php").write_text(config, encoding="utf-8")
    php_dir = Path(php).parent
    ini = TMP / "php.ini"
    ini.write_text(f'extension_dir="{(php_dir / "ext").as_posix()}"\nextension=openssl\n'
                   f'error_reporting=E_ALL\ndisplay_errors=0\nlog_errors=1\n'
                   f'error_log="{(TMP / "php-errors.log").as_posix()}"\n', encoding="utf-8")
    php_port = free_port()
    php_proc = subprocess.Popen([php, "-c", str(ini), "-S", f"127.0.0.1:{php_port}", "-t", str(ftp_root)],
                                stdout=subprocess.DEVNULL, stderr=open(TMP / "php-server.log", "wb"))
    site = f"http://127.0.0.1:{php_port}/careers/"
    base = site + "index.php"
    for _ in range(50):
        try:
            requests.get(base, timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(0.1)
    version = subprocess.run([php, "-c", str(ini), "-r", "echo PHP_VERSION;"], capture_output=True, text=True).stdout
    print(f"(PHP {version}, fake SMTPS on port {smtp_port})")

    with isolated_ai_client():
        app = selection_app.app
        # --- Selection: an RF-One owner opens and approves two positions ------
        with selection_app.SessionFactory() as s:
            acc = account_svc.create_account(s, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(s, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            owner_ids = (acc.id, acc.session_version)
            s.commit()
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_ids
        t = re.search(r'name="csrf_token" value="([^"]+)"', owner.get("/selection/").get_data(as_text=True)).group(1)

        def open_position(title):
            r = owner.post("/selection/posizioni/nuova", data={
                "csrf_token": t, "title": title, "role_code": "SERVER", "location": "Mount Dora",
                "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(owner_ids[0]),
                "description": "Server"}, follow_redirects=True)
            pid = int(re.search(r"/selection/posizioni/(\d+)/requisiti/aggiungi", r.get_data(as_text=True)).group(1))
            owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
                "csrf_token": t, "name": "Server experience", "description": "server table service",
                "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
            owner.post(f"/selection/posizioni/{pid}/dettagli", data={
                "csrf_token": t, "headcount": "1", "job_ad_en": f"Join our team as a {title}.",
                "questions": "Are you available to work weekends?\nWhen could you start?"})
            owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
            with selection_app.SessionFactory() as s:
                return pid, s.get(ws.Position, pid).public_token

        pid, pos = open_position("Server")
        pid2, pos2 = open_position("Food Runner")

        # --- Selection's job page sends candidates to the careers page --------
        cand = app.test_client()
        page = cand.get(f"/selection/jobs/{pos}").get_data(as_text=True)
        check("job page: 'Verify your email to apply' links to the careers page with only the position token",
              f'href="{IDENTITY_URL}?position={pos}"' in page and "Verify your email to apply" in page)
        check("job page: no password registration or sign-in form any more",
              'type="password"' not in page and "Create account" not in page)
        probe = app.test_client()
        with probe.session_transaction() as sess:
            sess[shared_session.SESSION_CSRF_KEY] = "synthetic-csrf"
        r = probe.post(f"/selection/jobs/{pos}/account/code", data={
            "csrf_token": "synthetic-csrf", "full_name": "X", "email": "x@example.test", "password": "synthetic-pass-1"})
        check("Selection's own password registration is switched off", r.status_code == 409, r.status_code)

        # --- 1. Careers page: identification ----------------------------------
        browser = requests.Session()
        r = browser.get(base)
        cookie = r.headers.get("Set-Cookie", "")
        check("1. without a position the page asks to start from the job posting",
              "Please open this page from the job posting" in r.text)
        r = browser.get(base, params={"position": pos})
        html = r.text
        check("1. page in English with First Name, Last Name, Email and Receive Code",
              all(x in html for x in ("First Name", "Last Name", "Email", "Receive Code", 'lang="en"')))
        check("1. RF-One look: same header, palette and stylesheet",
              'class="site-header"' in html and "brand-wordmark" in html and "assets/careers.css" in html
              and "#55642f" in requests.get(site + "assets/careers.css").text)
        check("1. session cookie HttpOnly and SameSite=Lax", "HttpOnly" in cookie and "SameSite=Lax" in cookie, cookie)
        csp = r.headers.get("Content-Security-Policy", "")
        check("1. strict headers: CSP (forms only to itself and Selection), no-store, noindex",
              "form-action 'self' http://selection.test" in csp and "no-store" in r.headers.get("Cache-Control", "")
              and "noindex" in r.headers.get("X-Robots-Tag", ""), csp)
        token_ = csrf(html)
        r = browser.post(base, data={"csrf": token_, "action": "request_code", "first_name": "Jordan",
                                     "last_name": "Example", "email": "not-an-email"})
        check("1. an invalid email is refused, nothing is sent",
              "valid email" in r.text and not Mailbox.messages)
        r = browser.post(base, data={"action": "request_code", "first_name": "Jordan", "last_name": "Example",
                                     "email": "jordan@example.test"})
        check("1. a request without the form token is refused", "session expired" in r.text and not Mailbox.messages)
        t0 = time.time()
        r = browser.post(base, data={"csrf": csrf(browser.get(base).text), "action": "request_code",
                                     "first_name": " Jordan ", "last_name": "Example", "email": "Jordan@Example.TEST"})
        urls = [h.url for h in r.history] + [r.url] + [h.headers.get("Location", "") for h in r.history]
        check("2. Receive Code shows the second page without asking the details again",
              "Welcome, Jordan!" in r.text and "Verification Code" in r.text and "Confirm" in r.text
              and "Cancel" in r.text and 'name="first_name"' not in r.text, r.text[:400])
        check("no personal data or code in any URL (only the position token)",
              all("jordan" not in u.lower() and "example" not in u.lower() for u in urls), urls)
        msg = Mailbox.messages[-1] if Mailbox.messages else {}
        check("2. the code is emailed through authenticated SMTP over verified TLS, from rfone@romesflavours.com",
              Mailbox.logins[-1:] == [(SMTP_USER, SMTP_PASSWORD)] and msg.get("from") == SMTP_USER
              and msg.get("to") == ["jordan@example.test"] and "Hi Jordan," in msg.get("data", ""), msg)
        code1 = mail_code("jordan@example.test")
        check("2. the code has 5 digits", re.fullmatch(r"\d{5}", code1) is not None, code1)
        r = browser.post(base, data={"csrf": csrf(r.text), "action": "resend"})
        check("limits: a new code cannot be requested again within a minute", "Please wait" in r.text, r.text[:300])
        wrong = "00000" if code1 != "00000" else "11111"
        r = browser.post(base, data={"csrf": csrf(r.text), "action": "confirm", "code": wrong})
        check("2. a wrong code is refused with the attempts left", "4 attempts left" in r.text)

        logs = "".join(p.read_text() for p in (data_dir / "logs").glob("*.log"))
        sessions = "".join(p.read_text(errors="ignore") for p in (data_dir / "sessions").glob("sess_*"))
        check("no code in clear in logs or in the session; no email or name in the logs",
              code1 not in logs and code1 not in sessions and "jordan" not in logs.lower() and "code_sent" in logs, logs)

        r = browser.post(base, data={"csrf": csrf(r.text), "action": "confirm", "code": code1})
        form = re.search(r'<form id="handoff" method="post" action="([^"]+)">\s*'
                         r'<input type="hidden" name="identity_token" value="([^"]+)">', r.text)
        check("3. the right code: a form posts the token to Selection (body, not URL)",
              form is not None and form.group(1) == SELECTION_HANDOFF and "?" not in form.group(1), r.text[:500])
        identity_token = form.group(2) if form else ""
        claims = handoff.read_claims(identity_token, SECRET) if form else {}
        check("3. the token is signed for Selection and carries name, surname, email and position",
              claims.get("fn") == "Jordan" and claims.get("ln") == "Example" and claims.get("em") == "jordan@example.test"
              and claims.get("pos") == pos and claims.get("aud") == "rfone-selection"
              and claims["exp"] - claims["iat"] == 300, claims)
        r = browser.get(base, params={"position": pos})
        check("3. after confirming, the careers page starts over (the code cannot be used twice)",
              "Receive Code" in r.text and "Welcome" not in r.text)

        # --- Cancel, exhausted and expired codes, limits ------------------------
        other = requests.Session()
        html = other.get(base, params={"position": pos}).text
        r = other.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": "Casey",
                                   "last_name": "Sample", "email": "casey@example.test"})
        r = other.post(base, data={"csrf": csrf(r.text), "action": "cancel"})
        check("Cancel ends the procedure and returns to an empty form",
              "Verification cancelled" in r.text and "Receive Code" in r.text and 'value="Casey"' not in r.text)

        five = requests.Session()
        html = five.get(base, params={"position": pos}).text
        r = five.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": "Riley",
                                  "last_name": "Test", "email": "riley@example.test"})
        right = mail_code("riley@example.test")
        bad = "00000" if right != "00000" else "11111"
        for _ in range(5):
            r = five.post(base, data={"csrf": csrf(r.text), "action": "confirm", "code": bad})
        check("at most 5 attempts: the fifth wrong code invalidates it", "Too many wrong attempts" in r.text)
        check("an exhausted code no longer accepts even the right one",
              'name="code"' not in r.text and "Send a new code" in r.text)

        late = requests.Session()
        html = late.get(base, params={"position": pos}).text
        late.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": "Morgan",
                              "last_name": "Late", "email": "morgan@example.test"})
        late_code = mail_code("morgan@example.test")
        late_csrf = csrf(late.get(base).text)
        sess_file = data_dir / "sessions" / f"sess_{late.cookies.get('rfcareers')}"
        stored = sess_file.read_text()
        sess_file.write_text(re.sub(r's:7:"expires";i:\d+;', f's:7:"expires";i:{int(time.time()) - 1};', stored))
        r = late.post(base, data={"csrf": late_csrf, "action": "confirm", "code": late_code})
        check("the code expires after 10 minutes", "This code has expired" in r.text, r.text[:300])

        codes = {code1, right, late_code, mail_code("casey@example.test")}
        check("a different random code for every request", len(codes) == 4, codes)

        check("check.php is closed without its key", requests.get(site + "check.php").status_code == 404)
        diag = requests.get(site + "check.php", params={"key": "synthetic-diagnostics-key"}).text
        check("check.php reports PHP, extensions, data folder, sessions and a real SMTP login",
              "PHP version" in diag and "SMTP login" in diag and "login accepted, nothing sent" in diag
              and diag.count('class="ok">OK') >= 10, re.sub(r"<[^>]+>", " ", diag)[:600])
        diag_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", diag))
        check("check.php finds Aruba's mdb-database folder and keeps sessions, counters and logs there",
              "Data folder writable (sessions, counters, logs) OK" in diag_text and "rfone-careers" in diag_text
              and "PHP sessions in the data folder OK" in diag_text, diag_text[:900])
        # PHP's test server answers one request at a time and ignores web.config: check.php cannot reach
        # itself here, and must then say NO rather than claim the folder is closed. On IIS it gets 404.
        check("check.php never claims private/ is closed when it could not prove it",
              "Folder private/ closed to the web (web.config) NO" in diag_text, diag_text[:900])
        check("the probe file check.php looks for carries the exposure marker",
              "RF-ONE-PRIVATE-FOLDER-EXPOSED" in requests.get(site + "private/blocked.html").text)
        check("IIS package: web.config hides private/, no Apache .htaccess, nothing written inside careers/",
              "<add segment=\"private\" />" in (docroot / "web.config").read_text()
              and not list(docroot.rglob(".htaccess")) and not (docroot / "private" / "data").exists()
              and (data_dir / "limits").is_dir())

        # --- 4. Selection receives the identity ---------------------------------
        first, r = deliver(cand, identity_token)
        check("4. the post from Aruba changes no session: Selection re-posts the token from its own page",
              first.status_code == 200 and "Set-Cookie" not in first.headers
              and 'name="step" value="continue"' in first.get_data(as_text=True))
        check("4. Selection accepts the token and opens the position (303, no personal data in the URL)",
              r.status_code == 303 and r.headers["Location"].endswith(f"/selection/jobs/{pos}#apply")
              and "jordan" not in r.headers["Location"].lower(), (r.status_code, r.headers.get("Location")))
        page = cand.get(f"/selection/jobs/{pos}").get_data(as_text=True)
        check("4. Selection has the verified first name, last name and email",
              "Applying as <b>Jordan Example</b> (jordan@example.test)" in page and 'name="cv"' in page)
        _, r = deliver(app.test_client(), identity_token)
        check("security: the same token cannot be used twice", r.status_code == 400 and "already used" in r.get_data(as_text=True))

        def forged(**changes):
            now = int(time.time())
            base_claims = {"v": 1, "iss": "rfone-careers-aruba", "aud": "rfone-selection", "amr": "email-code",
                           "jti": os.urandom(16).hex(), "iat": now, "exp": now + 300, "pos": pos,
                           "fn": "Eve", "ln": "Forger", "em": "eve@example.test"}
            secret = changes.pop("secret", SECRET)
            base_claims.update(changes)
            return handoff.sign(base_claims, secret)

        def refused(tok):
            return deliver(app.test_client(), tok)[1].status_code == 400

        parts = identity_token.split(".")
        tampered_body = base64.urlsafe_b64encode(json.dumps(dict(claims, em="eve@example.test")).encode()).rstrip(b"=").decode()
        check("security: a token signed with another secret is refused", refused(forged(secret="another-secret-" + "y" * 30)))
        check("security: a token whose content was changed is refused", refused(f"{parts[0]}.{tampered_body}.{parts[2]}"))
        check("security: an expired token is refused", refused(forged(iat=int(time.time()) - 400, exp=int(time.time()) - 100)))
        check("security: a token for another recipient is refused", refused(forged(aud="rfone-web")))
        check("security: a token with a too-long validity is refused", refused(forged(exp=int(time.time()) + 3600)))
        check("security: a token for an unknown position is refused", refused(forged(pos="unknown-position-token")))
        check("security: Selection does not accept the token in the URL",
              refused("") and deliver(app.test_client(), None, f"?identity_token={forged()}")[1].status_code == 400)
        staff = app.test_client()
        with staff.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_ids
        _, r = deliver(staff, forged(fn="Pat", ln="Owner", em="pat@example.test"))
        check("an RF-One login already open in the same browser stays valid after a candidate verification",
              r.status_code == 303 and staff.get("/selection/").status_code == 200
              and 'name="cv"' in staff.get(f"/selection/jobs/{pos}").get_data(as_text=True))
        with selection_app.SessionFactory() as s:
            check("security: refused tokens create no identity",
                  s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "eve@example.test")).first() is None)
            # Pat only served the check above: removed so that the counts below are Jordan's alone.
            pat = s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "pat@example.test")).one()
            s.query(ws.CandidateIdentityHandoff).filter(ws.CandidateIdentityHandoff.candidate_account_id == pat.id).delete()
            s.delete(pat)
            s.commit()

        # --- 5-6. Application saved progressively -------------------------------
        page = cand.get(f"/selection/jobs/{pos}").get_data(as_text=True)
        ct = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        r = cand.post(f"/selection/jobs/{pos}", data={"csrf_token": ct, "consent": "1", "phone": "(407) 555-0101",
                                                      "cv": (BytesIO(CV.encode()), "jordan.txt")},
                      content_type="multipart/form-data")
        apply_url = r.headers.get("Location", "")
        check("5. the résumé is saved and the application starts", "/selection/my-application/" in apply_url, apply_url)
        page = cand.get(apply_url).get_data(as_text=True)
        check("5. the application is In Progress", "Status: <b>In Progress</b>" in page and "Question 1 of 2" in page)
        r = cand.post(apply_url, data={"csrf_token": ct, "index": "0", "answer": "Yes, every weekend.",
                                       "input_mode": "TEXT", "action": "later"})
        body = r.get_data(as_text=True)
        check("6. answers saved; to continue, verify the email again on the careers page",
              "Your answers are saved" in body and f"{IDENTITY_URL}?position={pos}" in body)
        with selection_app.SessionFactory() as s:
            account = s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "jordan@example.test")).one()
            pcs = s.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.candidate_account_id == account.id)).all()
            application = s.scalars(select(ws.CandidateApplication)).one()
            answers = s.scalars(select(ws.Answer)).all()
            handoffs = s.scalars(select(ws.CandidateIdentityHandoff)).all()
        check("no password: the identity has a verified email, first and last name, and no password",
              account.password_hash is None and account.email_verified_at is not None
              and (account.first_name, account.last_name, account.full_name) == ("Jordan", "Example", "Jordan Example"))
        check("one record: one application with status CV_RECEIVED (In Progress) and the saved answer",
              len(pcs) == 1 and application.status == ws.A_CV_RECEIVED and [a.answer_text for a in answers] == ["Yes, every weekend."])
        check("the used token is recorded by its id only", len(handoffs) == 1 and handoffs[0].token_id == claims["jti"])

        # --- Access only to the token's position --------------------------------
        page2 = cand.get(f"/selection/jobs/{pos2}").get_data(as_text=True)
        check("security: the same session does not open another position",
              'name="cv"' not in page2 and "Verify your email to apply" in page2)
        r = cand.post(f"/selection/jobs/{pos2}", data={"csrf_token": ct, "consent": "1",
                                                       "cv": (BytesIO(CV.encode()), "j2.txt")},
                      content_type="multipart/form-data", follow_redirects=True)
        with selection_app.SessionFactory() as s:
            n_pc2 = len(s.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.position_id == pid2)).all())
        check("security: nothing can be sent to another position", n_pc2 == 0 and "verify your email" in r.get_data(as_text=True))

        # --- 8. The candidate comes back later on another device ----------------
        time.sleep(max(0.0, 61 - (time.time() - t0)))  # the one-minute pause between two codes for one email
        back = requests.Session()
        html = back.get(base, params={"position": pos}).text
        r = back.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": "Jordan",
                                  "last_name": "Example", "email": "jordan@example.test"})
        r = back.post(base, data={"csrf": csrf(r.text), "action": "confirm", "code": mail_code("jordan@example.test")})
        token2 = re.search(r'name="identity_token" value="([^"]+)"', r.text).group(1)
        device2 = app.test_client()
        _, r = deliver(device2, token2)
        check("8. after a new email verification the candidate goes straight back to the same application",
              r.status_code == 303 and r.headers["Location"].endswith(apply_url.split("/selection")[-1]),
              r.headers.get("Location"))
        page = device2.get(apply_url).get_data(as_text=True)
        check("8. the interview resumes at question 2", "Question 2 of 2" in page)
        ct2 = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        device2.post(apply_url, data={"csrf_token": ct2, "index": "1", "answer": "I can start next Monday.",
                                      "input_mode": "TEXT", "action": "next"})
        page = device2.post(apply_url, data={"csrf_token": ct2, "action": "submit"}, follow_redirects=True).get_data(as_text=True)
        check("7. completed: the candidate sees Completed", "Status: <b>Completed</b>" in page and "application is complete" in page)
        with selection_app.SessionFactory() as s:
            accounts = s.scalars(select(ws.CandidateAccount).where(ws.CandidateAccount.email == "jordan@example.test")).all()
            pcs = s.scalars(select(ws.PositionCandidate)).all()
            application = s.scalars(select(ws.CandidateApplication)).one()
        check("no duplicates: one identity, one application, now SUBMITTED (Completed) with both answers",
              len(accounts) == 1 and len(pcs) == 1 and application.status == ws.A_SUBMITTED
              and application.submitted_at is not None)
        mpage = owner.get(f"/selection/posizioni/{pid}?tab=candidature").get_data(as_text=True)
        check("the manager sees the completed application in the existing workspace",
              "Jordan Example" in mpage and "Application complete" in mpage)

        # --- SMTP failure -------------------------------------------------------
        Mailbox.accept_password = "changed"
        fail = requests.Session()
        html = fail.get(base, params={"position": pos}).text
        r = fail.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": "Sam",
                                  "last_name": "Fail", "email": "sam@example.test"})
        check("a mailbox that refuses the login gives a clear error and no second page",
              "could not send the verification email" in r.text and "Welcome" not in r.text, r.text[:300])
        Mailbox.accept_password = SMTP_PASSWORD

        # Per network (last: it uses up the hour's codes of this network): at most 20 codes per hour (all test clients share 127.0.0.1).
        sent_before = len(Mailbox.messages)
        flood = requests.Session()
        refused_at = None
        for i in range(25):
            html = flood.get(base, params={"position": pos}).text
            r = flood.post(base, data={"csrf": csrf(html), "action": "request_code", "first_name": f"Flood{i}",
                                       "last_name": "Test", "email": f"flood{i}@example.test"})
            if "from this network" in r.text:
                refused_at = len(Mailbox.messages)
                break
            flood.post(base, data={"csrf": csrf(r.text), "action": "cancel"})
        # Every code request counts, also the one the mailbox refused above (Sam): 20 in all.
        check("limits: at most 20 codes per hour from one network", refused_at is not None and refused_at + 1 == 20,
              (sent_before, refused_at))

        errors_file = TMP / "php-errors.log"  # PHP's own error log: every warning, notice or deprecation
        server_log = errors_file.read_text(errors="ignore") if errors_file.exists() else ""
        check("PHP printed no warning, notice or deprecation",
              not re.search(r"(Warning|Notice|Deprecated|Fatal error)", server_log),
              [line for line in server_log.splitlines() if re.search("Warning|Notice|Deprecated|Fatal", line)][:5])
finally:
    if php_proc is not None:
        php_proc.terminate()
        php_proc.wait(timeout=10)
    if smtp is not None:
        smtp.shutdown()
        smtp.server_close()
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
