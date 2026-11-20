#!/usr/bin/env python
"""HTTP-level checks for ADMIN_PERMISSIONS_001: several RF-One
administrators at once, the owner kept distinct, Domain administrators who
can really change their Domain's content (Development Journal entries
written by others, Organization changes), and ordinary users who keep
their limits.

Same convention as the other tests here: throwaway SQLite database created
before `app.py` is imported, migrated explicitly, Werkzeug's Flask test
client, `main()` returning an exit code. Never touches AWS or any shared
database.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_admin_permissions_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
_DOC_DIR = tempfile.mkdtemp(prefix="rfoneweb_admin_permissions_docs_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "admin-permissions-test-secret"
os.environ["RFONE_DEV_JOURNAL_DOCUMENT_DIR"] = _DOC_DIR
os.environ.pop("RFONE_DEV_JOURNAL_DOCUMENT_BUCKET", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.dev_journal import models as dj  # noqa: E402
from rfone_data_store.dev_journal import service as svc  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    csrf = extract_csrf(client.get("/login").data)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            owner = account_service.create_account(s, username="owner", display_name="Owner",
                                                   password="OwnerPass123!", is_admin=True)
            owner.is_owner = True
            shelbi = account_service.create_account(s, username="shelbi", display_name="Shelbi",
                                                    password="ShelbiPass123!")
            third = account_service.create_account(s, username="third", display_name="Third Admin",
                                                   password="ThirdPass123!")
            author = account_service.create_account(s, username="author", display_name="Entry Author",
                                                    password="AuthorPass123!")
            plain = account_service.create_account(s, username="plain", display_name="Plain User",
                                                   password="PlainPass123!")
            for acc in (owner, author, plain):
                account_service.set_domain_access(s, account_id=acc.id, domain_code="DEV_JOURNAL",
                                                  enabled=True, role_code=None)
            for acc in (owner, plain):
                account_service.set_domain_access(s, account_id=acc.id, domain_code="ORGANIZATION",
                                                  enabled=True, role_code=None)
            s.commit()
            owner_id, shelbi_id, third_id, author_id, plain_id = owner.id, shelbi.id, third.id, author.id, plain.id

        o = web_app.app.test_client()
        login(o, "owner", "OwnerPass123!")
        sh = web_app.app.test_client()
        login(sh, "shelbi", "ShelbiPass123!")
        pl = web_app.app.test_client()
        login(pl, "plain", "PlainPass123!")

        # ---- Several RF-One administrators ---------------------------------
        check("before: Shelbi cannot open Accounts", sh.get("/admin/accounts").status_code == 403)
        form = o.get(f"/admin/accounts/{shelbi_id}/edit").data.decode()
        check("the account form offers 'RF-One administrator'", 'name="is_admin"' in form)
        csrf = extract_csrf(form.encode())
        resp = o.post(f"/admin/accounts/{shelbi_id}/edit", data={
            "csrf_token": csrf, "display_name": "Shelbi", "status": "ACTIVE", "is_admin": "on"})
        check("the owner makes Shelbi an administrator", resp.status_code == 302, str(resp.status_code))
        check("after: Shelbi opens Accounts", sh.get("/admin/accounts").status_code == 200)
        sh_csrf = extract_csrf(sh.get(f"/admin/accounts/{third_id}/edit").data)
        resp = sh.post(f"/admin/accounts/{third_id}/edit", data={
            "csrf_token": sh_csrf, "display_name": "Third Admin", "status": "ACTIVE", "is_admin": "on"})
        check("Shelbi, now an administrator, makes a third administrator", resp.status_code == 302)
        with SessionFactory() as s:
            admins = sorted(a.username for a in account_service.list_admins(s))
        check("three administrators at the same time", admins == ["owner", "shelbi", "third"], str(admins))
        accounts_page = o.get("/admin/accounts").data.decode()
        check("Accounts shows the owner as 'Owner' and the others as administrators",
              "Owner" in accounts_page and accounts_page.count(">Yes<") == 2)

        # ---- Owner and self-protection ----------------------------------
        resp = sh.post(f"/admin/accounts/{owner_id}/edit", data={
            "csrf_token": sh_csrf, "display_name": "Owner", "status": "ACTIVE"})
        check("another administrator cannot remove the owner's role", resp.status_code == 400)
        resp = sh.post(f"/admin/accounts/{owner_id}/edit", data={
            "csrf_token": sh_csrf, "display_name": "Owner", "status": "INACTIVE", "is_admin": "on"})
        check("another administrator cannot deactivate the owner", resp.status_code == 400)
        resp = sh.post(f"/admin/accounts/{shelbi_id}/edit", data={
            "csrf_token": sh_csrf, "display_name": "Shelbi", "status": "ACTIVE"})
        check("an administrator cannot remove their own role", resp.status_code == 400)
        with SessionFactory() as s:
            o_row, sh_row = s.get(m.RFOneAccount, owner_id), s.get(m.RFOneAccount, shelbi_id)
            check("owner and Shelbi unchanged after the refused changes",
                  o_row.is_owner and o_row.is_admin and o_row.status == "ACTIVE" and sh_row.is_admin)
        owner_form = sh.get(f"/admin/accounts/{owner_id}/edit").data.decode()
        check("the owner's form explains the owner stays administrator", "owner of RF-One" in owner_form)
        resp = o.post(f"/admin/accounts/{third_id}/edit", data={
            "csrf_token": csrf, "display_name": "Third Admin", "status": "ACTIVE"})
        with SessionFactory() as s:
            check("an administrator can remove another administrator's role",
                  resp.status_code == 302 and not s.get(m.RFOneAccount, third_id).is_admin)
        with SessionFactory() as s:
            lone = account_service.create_account(s, username="lone", display_name="Lone", password="x" * 12)
            s.flush()
            for acc in s.scalars(select(m.RFOneAccount)).all():
                acc.is_owner = False
                acc.is_admin = acc.id == lone.id
            s.flush()
            try:
                account_service.update_account(s, lone, display_name="Lone", status="ACTIVE", is_admin=False)
                kept_one = False
            except account_service.AdminRuleError:
                kept_one = True
            s.rollback()
        check("the last active administrator cannot be removed", kept_one)

        # ---- Non-admin cannot manage accounts ---------------------------
        check("an ordinary user cannot open Accounts", pl.get("/admin/accounts").status_code == 403)
        pl_csrf = extract_csrf(pl.get("/dev-journal/new").data)
        resp = pl.post(f"/admin/accounts/{plain_id}/edit", data={
            "csrf_token": pl_csrf, "display_name": "Plain User", "status": "ACTIVE", "is_admin": "on"})
        with SessionFactory() as s:
            check("an ordinary user cannot make themselves administrator",
                  resp.status_code == 403 and not s.get(m.RFOneAccount, plain_id).is_admin)

        # ---- Domain administrator role ----------------------------------
        access_page = o.get(f"/admin/accounts/{shelbi_id}/access").data.decode()
        check("Domain Access offers 'Domain administrator'", "Domain administrator" in access_page)
        # Shelbi: Domain administrator of DEV_JOURNAL and ORGANIZATION (typed "Admin", as before).
        with SessionFactory() as s:
            account_service.set_domain_access(s, account_id=shelbi_id, domain_code="DEV_JOURNAL",
                                              enabled=True, role_code="Admin")
            account_service.set_domain_access(s, account_id=shelbi_id, domain_code="ORGANIZATION",
                                              enabled=True, role_code="ADMIN")
            # Shelbi is no longer an RF-One administrator for the Domain checks
            # below: only the Domain role must be enough.
            s.get(m.RFOneAccount, shelbi_id).is_admin = False
            s.commit()
            rows = {r.domain_code: r.role_code for r in account_service.list_domain_access_for_account(s, shelbi_id)}
            sh_acc, pl_acc = s.get(m.RFOneAccount, shelbi_id), s.get(m.RFOneAccount, plain_id)
            check("'Admin' / 'ADMIN' are stored as the one role code 'admin'",
                  rows == {"DEV_JOURNAL": "admin", "ORGANIZATION": "admin"}, str(rows))
            check("Shelbi is Domain administrator of DEV_JOURNAL and ORGANIZATION only",
                  shared_session.account_is_domain_admin(s, sh_acc, "DEV_JOURNAL")
                  and shared_session.account_is_domain_admin(s, sh_acc, "ORGANIZATION")
                  and not shared_session.account_is_domain_admin(s, sh_acc, "BANK"))
            check("an ordinary user is not Domain administrator",
                  not shared_session.account_is_domain_admin(s, pl_acc, "DEV_JOURNAL"))

        # ---- Development Journal: correcting someone else's entry -------
        au = web_app.app.test_client()
        login(au, "author", "AuthorPass123!")
        au_csrf = extract_csrf(au.get("/dev-journal/new").data)
        resp = au.post("/dev-journal/new", data={
            "csrf_token": au_csrf, "title": "Permissions", "domain_code": "SYSTEM", "objective": "Fix admins.",
            "responsible_account_id": str(author_id), "phase": "STUDY", "status": "IN_PROGRESS", "next_step": ""})
        work_id = int(resp.headers["Location"].rstrip("/").split("/")[-1])
        entry_data = {"csrf_token": au_csrf, "phase": "STUDY", "entry_type": "ANALYSIS", "body": "Original text."}
        au.post(f"/dev-journal/{work_id}/entries", data=entry_data)
        with SessionFactory() as s:
            entry_id = svc.list_entries(s, work_id)[0].id
        edit_url = f"/dev-journal/{work_id}/entries/{entry_id}/edit"

        check("the ordinary user does not see 'Correct' on someone else's entry",
              f'href="{edit_url}"' not in pl.get(f"/dev-journal/{work_id}").data.decode())
        check("the ordinary user cannot open the correction page", pl.get(edit_url).status_code == 403)
        resp = pl.post(edit_url, data={**entry_data, "csrf_token": pl_csrf, "body": "hijack"})
        check("the ordinary user cannot save a correction", resp.status_code == 403)

        check("the Domain administrator sees 'Correct' on someone else's entry",
              f'href="{edit_url}"' in sh.get(f"/dev-journal/{work_id}").data.decode())
        page = sh.get(edit_url)
        check("the Domain administrator opens the correction page, told whose entry it is",
              page.status_code == 200 and "written by Entry Author" in page.data.decode())
        sh_csrf = extract_csrf(page.data)
        resp = sh.post(edit_url, data={**entry_data, "csrf_token": sh_csrf, "body": "Corrected by Shelbi."})
        check("the Domain administrator saves the correction", resp.status_code == 302, str(resp.status_code))
        with SessionFactory() as s:
            entry = s.get(dj.DevJournalEntry, entry_id)
            versions = svc.list_entry_versions(s, entry_id)
        check("the entry holds the new text, recorded as edited by Shelbi, author unchanged",
              entry.body == "Corrected by Shelbi." and entry.version == 2
              and entry.edited_by_account_id == shelbi_id and entry.author_account_id == author_id)
        check("the author's original version is kept with the author's name",
              [(v.version, v.body, v.written_by_account_id) for v in versions] == [(1, "Original text.", author_id)])
        card = pl.get(f"/dev-journal/{work_id}").data.decode()
        check("the card says who corrected it", "by Shelbi" in card)
        check("the author can still correct their own entry", au.get(edit_url).status_code == 200)

        # ---- Organization: Domain administrator may change it ------------
        check("the ordinary Organization user cannot open 'New position'",
              pl.get("/admin/org/positions/new").status_code == 403)
        resp = pl.post("/admin/org/positions/new", data={"csrf_token": pl_csrf, "name": "Hijack"})
        check("the ordinary Organization user cannot create a position", resp.status_code == 403)
        check("the Organization Domain administrator opens 'New position'",
              sh.get("/admin/org/positions/new").status_code == 200)
        resp = sh.post("/admin/org/positions/new", data={"csrf_token": sh_csrf, "name": "Store Manager"})
        with SessionFactory() as s:
            names = [p.name for p in s.scalars(select(m.Position)).all()]
        check("the Organization Domain administrator creates a position",
              resp.status_code == 302 and names == ["Store Manager"], f"{resp.status_code} {names}")
        check("being Domain administrator never opens another Domain", sh.get("/dev-journal").status_code == 200
              and sh.get("/bank").status_code in (403, 404))

        # ---- Training: the Domain administrator has the Trainer rights -----
        import training_integration as ti
        check("Training maps the Domain administrator role to 'trainer'",
              ti.effective_training_role("Admin") == "trainer" and ti.effective_training_role("student") == "student"
              and ti.effective_training_role("other") is None)
        with SessionFactory() as s:
            tadm = account_service.create_account(s, username="trainadm", display_name="Training Admin",
                                                  password="TrainAdm12345!", email="trainadm@example.com")
            account_service.set_domain_access(s, account_id=tadm.id, domain_code="TRAINING", enabled=True,
                                              role_code="Admin")
            s.commit()
            unlinked = ti.check_training_authorization(s, tadm)
            check("an unlinked Training Domain administrator is not given a Training identity",
                  unlinked.training_account is None and "identità Training collegata" in (unlinked.error or "")
                  and s.scalars(select(m.TrainingAccount)).first() is None, str(unlinked.error))
            ti.create_and_link_training_identity(s, rfone_account_id=tadm.id, role_code="admin")
            s.commit()
            linked = ti.check_training_authorization(s, tadm)
            check("a linked Training Domain administrator enters Training as trainer",
                  linked.training_account is not None and linked.training_account.role == "trainer",
                  str(linked.error))
        ta = web_app.app.test_client()
        login(ta, "trainadm", "TrainAdm12345!")
        check("the Training Domain administrator opens the trainer-only page",
              ta.get("/training-trainer/students/new").status_code == 200)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
        shutil.rmtree(_DOC_DIR, ignore_errors=True)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
