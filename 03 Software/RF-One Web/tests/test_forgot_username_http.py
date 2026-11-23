"""Forgot your username? Throwaway SQLite, no email really sent.

    python tests/test_forgot_username_http.py
"""
from __future__ import annotations
import os, re, sys, tempfile
from datetime import datetime, timezone
BASE = os.path.dirname(os.path.abspath(__file__)); APP = os.path.normpath(os.path.join(BASE, ".."))
sys.path.insert(0, APP)
fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{path.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "fu-test"
os.environ.pop("RFONE_PUBLIC_BASE_URL", None)
sys.path.insert(0, os.path.normpath(os.path.join(APP, "..", "RF-One Data Store")))
sent = []
from rfone_data_store.technical import account_email
account_email.send_email = lambda **k: sent.append(k)   # before app.py binds it: nothing is really sent
import app as web_app
import db as web_db
from rfone_data_store import models as m, rfone_account_service as accounts
import forgot_username_routes as fu
m.Base.metadata.create_all(web_db._engine)
web_app.app.config.update(TESTING=True)
fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"  [{detail}]"))
    if not ok:
        fails.append(label)


with web_db.SessionFactory() as db:
    a = accounts.create_account(db, username="shelbites", display_name="Shelbi Test", password="synthetic-pass-1", is_admin=False)
    a.email = "new.hire@example.test"; a.email_verified_at = datetime.now(timezone.utc)
    b = accounts.create_account(db, username="unverified1", display_name="No Verify", password="synthetic-pass-1", is_admin=False)
    b.email = "unverified@example.test"
    db.commit()
c = web_app.app.test_client()
check("login page links to Forgot your username?", "/forgot-username" in c.get("/login").get_data(as_text=True))
check("forgot password page links to it too", "/forgot-username" in c.get("/forgot-password").get_data(as_text=True))
tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/forgot-username").get_data(as_text=True)).group(1)


def ask(email):
    return c.post("/forgot-username", data={"csrf_token": tok, "email": email}, follow_redirects=True).get_data(as_text=True)


gen = fu.GENERIC.replace("'", "&#39;")
n = len(sent); out = ask("New.Hire@Example.test ")
check("verified email: one email with the username and the sign-in link",
      len(sent) == n + 1 and sent[-1]["to_address"] == "new.hire@example.test" and "shelbites" in sent[-1]["text_body"]
      and "http://localhost/login" in sent[-1]["text_body"] and sent[-1]["text_body"].startswith("Hi Shelbi,"), sent[-1:])
check("the generic answer is shown", gen in out, out[:300])
n = len(sent); out = ask("nobody@example.test")
check("unknown email: nothing sent, same answer", len(sent) == n and gen in out)
n = len(sent); ask("unverified@example.test")
check("unverified email: nothing sent", len(sent) == n)
n = len(sent)
for _ in range(4):
    ask("new.hire@example.test")
check("at most 3 emails per address per hour", len(sent) - n == 2, len(sent) - n)
n = len(sent); r = c.post("/forgot-username", data={"email": "someone@example.test"})
check("without the CSRF token nothing is sent", len(sent) == n and r.status_code in (302, 400, 403), r.status_code)
print("ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
