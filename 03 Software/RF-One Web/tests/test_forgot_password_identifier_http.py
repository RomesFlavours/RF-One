"""Forgot password: one box takes the username or the email. Throwaway SQLite, no email really sent.

    python tests/test_forgot_password_identifier_http.py
"""
from __future__ import annotations
import os, re, sys, tempfile
from datetime import datetime, timezone
BASE = os.path.dirname(os.path.abspath(__file__)); APP = os.path.normpath(os.path.join(BASE, ".."))
sys.path.insert(0, APP)
fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{path.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "fp-test"
os.environ.pop("RFONE_PUBLIC_BASE_URL", None)
sys.path.insert(0, os.path.normpath(os.path.join(APP, "..", "RF-One Data Store")))
sent = []
from rfone_data_store.technical import account_email
account_email.send_email = lambda **k: sent.append(k)
import app as web_app
import db as web_db
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_recovery_service as recovery
m.Base.metadata.create_all(web_db._engine)
web_app.app.config.update(TESTING=True)
fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"  [{detail}]"))
    if not ok:
        fails.append(label)


now = datetime.now(timezone.utc)
with web_db.SessionFactory() as db:
    for u, e, verified in (("hire1", "hire1@example.test", True), ("hire2", "hire2@example.test", True),
                           ("nover", "nover@example.test", False)):
        a = accounts.create_account(db, username=u, display_name=u.title(), password="synthetic-pass-1", is_admin=False)
        a.email = e; a.email_verified_at = now if verified else None
    db.commit()
    ids = {a.username: a.id for a in db.query(m.RFOneAccount)}


def ask(identifier):
    c = web_app.app.test_client()
    tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/forgot-password").get_data(as_text=True)).group(1)
    r = c.post("/forgot-password", data={"csrf_token": tok, "username": identifier}, follow_redirects=True)
    return c, r.get_data(as_text=True)


def has_code(username):
    with web_db.SessionFactory() as db:
        return recovery.get_pending_code(db, ids[username], recovery.PURPOSE_PASSWORD_RESET) is not None


page = web_app.app.test_client().get("/forgot-password").get_data(as_text=True)
check("one box labelled Username or email, no separate email box", "Username or email" in page and 'name="email"' not in page)
check("the page still links to Forgot your username?", "/forgot-username" in page)
_, out = ask("hire1")
check("by username: code emailed to that account's verified email", has_code("hire1") and sent and sent[-1]["to_address"] == "hire1@example.test")
c2, out2 = ask(" Hire2@Example.TEST ")
check("by email (any case, spaces): code for that account", has_code("hire2") and sent[-1]["to_address"] == "hire2@example.test")
with c2.session_transaction() as s:
    pending = [v for k, v in s.items() if "forgot" in k.lower()]
check("by email: step 2 is bound to that account's username", pending == ["hire2"], pending)
n = len(sent); _, out3 = ask("someone-else@example.test")
n = len(sent); _, out4 = ask("nover@example.test")
check("unverified email: no code", len(sent) == n and not has_code("nover"))
n = len(sent); _, out5 = ask("nobody@example.test")
check("unknown email: no code", len(sent) == n)
gen = web_app._FORGOT_PASSWORD_GENERIC_MESSAGE
check("same generic answer every time", all(gen in o for o in (out, out2, out3, out4, out5)))
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
