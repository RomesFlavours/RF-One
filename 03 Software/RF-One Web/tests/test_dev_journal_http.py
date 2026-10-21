#!/usr/bin/env python
"""HTTP-level checks for the Development Journal.

Mirrors this app's own test convention: throwaway SQLite database created
before `app.py` is imported, migrated explicitly, a throwaway document
folder, Werkzeug's Flask test client, `main()` returning an exit code.
Never touches AWS or any shared database.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_dev_journal_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
_DOC_DIR = tempfile.mkdtemp(prefix="rfoneweb_dev_journal_docs_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "dev-journal-test-secret"
os.environ["RFONE_DEV_JOURNAL_DOCUMENT_DIR"] = _DOC_DIR
os.environ.pop("RFONE_DEV_JOURNAL_DOCUMENT_BUCKET", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import dev_journal_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.dev_journal import document_store  # noqa: E402
from rfone_data_store.dev_journal import models as dj  # noqa: E402
from rfone_data_store.dev_journal import service as svc  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def login(client, username: str, password: str):
    resp = client.get("/login")
    csrf = extract_csrf(resp.data)
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
            account_service.create_account(s, username="admin1", display_name="Admin One",
                                           password="AdminPass123!", is_admin=True)
            dev = account_service.create_account(s, username="dev1", display_name="Pino Dev", password="DevPass123!")
            dev2 = account_service.create_account(s, username="dev2", display_name="Second Dev", password="Dev2Pass123!")
            plain = account_service.create_account(s, username="plain1", display_name="Plain One",
                                                   password="PlainPass123!")
            for account in (dev, dev2):
                account_service.set_domain_access(s, account_id=account.id, domain_code="DEV_JOURNAL",
                                                  enabled=True, role_code=None)
            s.commit()
            dev_id, dev2_id, plain_id = dev.id, dev2.id, plain.id

        # ---- Access ------------------------------------------------------
        p = web_app.app.test_client()
        login(p, "plain1", "PlainPass123!")
        check("without access, Home shows no Development Journal", b'href="/dev-journal"' not in p.get("/").data)
        for path in ("/dev-journal", "/dev-journal/new", "/dev-journal/1", "/dev-journal/1/documents/1",
                     "/dev-journal/1/entries/1/edit", "/dev-journal/1/entries/1/versions"):
            check(f"without access {path} is 403", p.get(path).status_code == 403)

        a = web_app.app.test_client()
        login(a, "admin1", "AdminPass123!")
        access_page = a.get(f"/admin/accounts/{plain_id}/access").data.decode()
        check("account access page offers the 'Development Journal access' checkbox",
              "Development Journal access" in access_page and 'name="enabled_DEV_JOURNAL"' in access_page
              and 'name="access_DEV_JOURNAL"' not in access_page)
        check("admin without the journal access is refused too", a.get("/dev-journal").status_code == 403)
        admin_csrf = extract_csrf(a.get(f"/admin/accounts/{plain_id}/access").data)
        resp = a.post(f"/admin/accounts/{plain_id}/access", data={"csrf_token": admin_csrf, "enabled_DEV_JOURNAL": "on"})
        check("the checkbox grants the access", resp.status_code == 302 and p.get("/dev-journal").status_code == 200)
        check("the access page shows it ticked afterwards",
              re.search(r'name="enabled_DEV_JOURNAL"\s+checked', a.get(f"/admin/accounts/{plain_id}/access").data.decode())
              is not None)
        a.post(f"/admin/accounts/{plain_id}/access", data={"csrf_token": admin_csrf})
        check("unticking removes it", p.get("/dev-journal").status_code == 403)

        c = web_app.app.test_client()
        login(c, "dev1", "DevPass123!")
        home = c.get("/").data.decode()
        check("with access, Home shows Development Journal under Services",
              'href="/dev-journal"' in home and "Services" in home and "Development Journal" in home)
        lst = c.get("/dev-journal").data.decode()
        check("list renders in English with 'New work'", "New work" in lst and "Development Journal" in lst)
        check("no Italian left on the list", not any(w in lst for w in ("Nuovo lavoro", "Diario", "Responsabile", "Filtra")))
        csrf = extract_csrf(c.get("/dev-journal/new").data)

        # ---- Create ------------------------------------------------------
        base = {"csrf_token": csrf, "title": "Bank — risposta alle domande del wizard", "domain_code": "BANK",
                "objective": "Il wizard non risponde.\nRisultato: risposte coerenti.", "responsible_account_id": str(dev_id),
                "phase": "STUDY", "status": "IN_PROGRESS", "next_step": "Leggere i log del wizard"}
        resp = c.post("/dev-journal/new", data={**base, "title": ""})
        check("a card without title is refused in English", resp.status_code == 400 and "Title is required" in resp.data.decode())
        resp = c.post("/dev-journal/new", data={**base, "responsible_account_id": str(plain_id)})
        check("a responsible without journal access is refused", resp.status_code == 400)
        resp = c.post("/dev-journal/new", data={**base, "domain_code": "NOPE"})
        check("an unknown domain is refused", resp.status_code == 400)
        resp = c.post("/dev-journal/new", data={**base, "csrf_token": "wrong"})
        check("create without CSRF is refused", resp.status_code == 400)
        resp = c.post("/dev-journal/new", data=base)
        check("a valid card is created", resp.status_code == 302, str(resp.status_code))
        work_id = int(resp.headers["Location"].rstrip("/").split("/")[-1])
        resp = c.post("/dev-journal/new", data={**base, "title": "System — logs", "domain_code": "SYSTEM",
                                                  "phase": "DEVELOPMENT", "next_step": ""})
        other_id = int(resp.headers["Location"].rstrip("/").split("/")[-1])

        with SessionFactory() as s:
            work = s.get(dj.DevJournalWork, work_id)
            check("author and timestamps are recorded automatically",
                  work.created_by_account_id == dev_id and work.created_at is not None and work.updated_at is not None)

        page = c.get(f"/dev-journal/{work_id}").data.decode()
        check("card shows the next step prominently", "Next step" in page and "Leggere i log del wizard" in page)
        check("user content is not translated", "Bank — risposta alle domande del wizard" in page)
        check("card breadcrumb RF-One > Development Journal > title",
              'href="/dev-journal">Development Journal</a>' in page)

        # ---- Filters -----------------------------------------------------
        body = c.get("/dev-journal?domain=SYSTEM").data.decode()
        check("filter by domain", "System — logs" in body and "risposta alle domande" not in body)
        body = c.get("/dev-journal?phase=STUDY&status=IN_PROGRESS&responsible=%d" % dev_id).data.decode()
        check("filter by phase/status/responsible", "risposta alle domande" in body and "System — logs" not in body)
        body = c.get("/dev-journal?status=BLOCKED").data.decode()
        check("filter with no match shows the empty message", "No work matches these filters" in body)
        body = c.get("/dev-journal").data.decode()
        check("list shows next step, or 'to be defined' when missing", "Leggere i log del wizard" in body and "to be defined" in body)

        # ---- Edit, history, reopen -----------------------------------------
        resp = c.post(f"/dev-journal/{work_id}/edit", data={**base, "phase": "DEVELOPMENT", "status": "COMPLETED",
                                                            "next_step": ""})
        check("edit saves", resp.status_code == 302)
        resp = c.post(f"/dev-journal/{work_id}/reopen", data={"csrf_token": csrf})
        check("reopen redirects", resp.status_code == 302)
        with SessionFactory() as s:
            work = s.get(dj.DevJournalWork, work_id)
            changes = [(ch.field, ch.old_value, ch.new_value) for ch in svc.list_changes(s, work_id)]
        check("reopen sets In progress", work.status == "IN_PROGRESS")
        check("phase and status changes are tracked",
              changes == [("PHASE", "STUDY", "DEVELOPMENT"), ("STATUS", "IN_PROGRESS", "COMPLETED"),
                          ("STATUS", "COMPLETED", "IN_PROGRESS")], str(changes))

        # ---- Entries -----------------------------------------------------
        entry_base = {"csrf_token": csrf, "phase": "DEVELOPMENT", "entry_type": "DECISION",
                      "body": "Decidiamo X.\n\n## Report Claude\n- punto 1\n<script>alert(1)</script>",
                      "ref_link": "https://github.com/RomesFlavours/RF-One/pull/1", "ref_branch": "feature/x",
                      "ref_commit": "abc1234", "ref_command": "claude -p 'fai X'"}
        resp = c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "body": "  "})
        check("an empty entry is refused, typed values are kept", resp.status_code == 400 and "feature/x" in resp.data.decode())
        resp = c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "ref_link": "javascript:alert(1)"})
        check("a non-http link is refused", resp.status_code == 400)
        resp = c.post(f"/dev-journal/{work_id}/entries", data={
            **entry_base, "files": [(io.BytesIO(b"note\n"), "note.txt"), (io.BytesIO(PNG), "screen.png")]},
            content_type="multipart/form-data")
        check("a decision with references and two files is saved", resp.status_code == 302, str(resp.status_code))
        resp = c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "entry_type": "ANALYSIS", "body": "Analisi."})
        check("an analysis is saved", resp.status_code == 302)

        resp = c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "entry_type": "RELEASE", "body": "Deploy."})
        check("a release without its fields is refused", resp.status_code == 400 and "Environment" in resp.data.decode())
        release = {**entry_base, "entry_type": "RELEASE", "body": "Deploy su test.", "release_environment": "TEST",
                   "release_aws_service": "App Runner rfone-web", "release_version": "abc1234",
                   "release_outcome": "FAILED", "release_post_deploy_check": "Health check rosso."}
        resp = c.post(f"/dev-journal/{work_id}/entries", data=release)
        check("a failed release is recorded", resp.status_code == 302)
        with SessionFactory() as s:
            work = s.get(dj.DevJournalWork, work_id)
            entries = svc.list_entries(s, work_id)
        check("a failed release does not complete the work", work.status == "IN_PROGRESS" and work.phase == "DEVELOPMENT")
        check("entries are chronological", [e.entry_type for e in entries] == ["DECISION", "ANALYSIS", "RELEASE"])
        c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "entry_type": "ACTIVITY", "body": "x",
                                                        "release_environment": "TEST"})
        with SessionFactory() as s:
            last = svc.list_entries(s, work_id)[-1]
        check("release fields are ignored on a non-release entry", last.entry_type == "ACTIVITY" and last.release_environment is None)

        page = c.get(f"/dev-journal/{work_id}").data.decode()
        check("decisions are visibly distinct", "dj-entry-DECISION" in page and "dj-type-DECISION" in page)
        check("a failed release is marked", "dj-release-failed" in page and "Failed" in page)
        check("pasted text is escaped, not executed", "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page)

        # ---- Correcting an entry and its versions -------------------------
        decision_id = entries[0].id
        edit_url = f"/dev-journal/{work_id}/entries/{decision_id}/edit"
        check("the author sees 'Correct' on their entry", f'href="{edit_url}"' in page)
        c2 = web_app.app.test_client()
        login(c2, "dev2", "Dev2Pass123!")
        check("another enabled user does not see 'Correct'", f'href="{edit_url}"' not in c2.get(f"/dev-journal/{work_id}").data.decode())
        check("another user cannot open the correction page", c2.get(edit_url).status_code == 403)
        csrf2 = extract_csrf(c2.get("/dev-journal/new").data)
        resp = c2.post(edit_url, data={**entry_base, "csrf_token": csrf2, "body": "hijack"})
        check("another user cannot correct it", resp.status_code == 403)
        check("the correction page opens prefilled for the author",
              c.get(edit_url).status_code == 200 and "Decidiamo X." in c.get(edit_url).data.decode())
        resp = c.post(edit_url, data={**entry_base, "body": "  "})
        check("an invalid correction is refused", resp.status_code == 400)
        resp = c.post(edit_url, data=entry_base)
        check("an unchanged correction keeps no version", resp.status_code == 302)
        resp = c.post(edit_url, data={**entry_base, "body": "Decidiamo Y (corretto).", "ref_commit": "def5678"})
        check("the author corrects the entry", resp.status_code == 302)
        resp = c.post(edit_url, data={**entry_base, "body": "Decidiamo Z.", "ref_commit": "def5678"})
        with SessionFactory() as s:
            entry = s.get(dj.DevJournalEntry, decision_id)
            versions = svc.list_entry_versions(s, decision_id)
        check("the entry now holds version 3", entry.version == 3 and entry.body == "Decidiamo Z."
              and entry.edited_by_account_id == dev_id and entry.edited_at is not None)
        check("both earlier versions are kept whole with author and date",
              [(v.version, v.body.split("\n")[0], v.ref_commit, v.written_by_account_id) for v in versions]
              == [(1, "Decidiamo X.", "abc1234", dev_id), (2, "Decidiamo Y (corretto).", "def5678", dev_id)]
              and all(v.written_at and v.superseded_at for v in versions), str([(v.version, v.body) for v in versions]))
        check("the entry keeps its author and creation time", entry.author_account_id == dev_id)
        page = c.get(f"/dev-journal/{work_id}").data.decode()
        entry_block = page.split(f'id="entry-{decision_id}"', 1)[1].split("</li>", 1)[0]
        check("the card shows the current text and a link to earlier versions",
              "Decidiamo Z." in entry_block and "Decidiamo X." not in entry_block
              and f"/dev-journal/{work_id}/entries/{decision_id}/versions" in entry_block)
        vpage = c2.get(f"/dev-journal/{work_id}/entries/{decision_id}/versions").data.decode()
        check("any enabled user can consult the earlier versions",
              "Version 3" in vpage and "Version 2" in vpage and "Version 1" in vpage
              and "Decidiamo X." in vpage and "Decidiamo Y (corretto)." in vpage and "current" in vpage)
        check("an entry of another card is not reachable",
              c.get(f"/dev-journal/{other_id}/entries/{decision_id}/versions").status_code == 404
              and c.get(f"/dev-journal/{other_id}/entries/{decision_id}/edit").status_code == 404)

        # ---- Documents ---------------------------------------------------
        resp = c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf, "files": [(io.BytesIO(PDF), "Spec v1.pdf")]},
                      content_type="multipart/form-data")
        check("a PDF is uploaded to the card", resp.status_code == 302)
        resp = c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf, "entry_id": str(decision_id),
                      "files": [(io.BytesIO(b"# Titolo\n"), "report.md")]}, content_type="multipart/form-data")
        check("a Markdown file is uploaded to one entry", resp.status_code == 302)
        for name, data, why in (("virus.exe", b"MZ", "a disallowed type"),
                                ("fake.pdf", b"not a pdf", "content not matching its extension"),
                                ("empty.txt", b"", "an empty file"),
                                ("evil.svg", b"<svg/>", "SVG")):
            before = len(os.listdir(_DOC_DIR))
            c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf, "files": [(io.BytesIO(data), name)]},
                   content_type="multipart/form-data")
            check(f"upload refuses {why}", len(os.listdir(_DOC_DIR)) == before)
        resp = c.post(f"/dev-journal/{work_id}/documents", data={"files": [(io.BytesIO(PDF), "x.pdf")]},
                      content_type="multipart/form-data")
        check("upload without CSRF is refused", resp.status_code == 400)
        resp = c.post(f"/dev-journal/{other_id}/documents", data={"csrf_token": csrf, "entry_id": str(decision_id),
                      "files": [(io.BytesIO(PDF), "x.pdf")]}, content_type="multipart/form-data")
        check("an entry of another card cannot receive the upload", resp.status_code == 404)
        c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf,
               "files": [(io.BytesIO(PDF), "../../etc/passwd.pdf")]}, content_type="multipart/form-data")

        with SessionFactory() as s:
            docs = svc.list_documents(s, work_id)
        names = [d.original_filename for d in docs]
        check("documents keep their original name; path parts are dropped",
              names == ["note.txt", "screen.png", "Spec v1.pdf", "report.md", "passwd.pdf"], str(names))
        check("storage never uses the person's file name", all(re.fullmatch(r"local:[0-9a-f]{32}", d.storage_path) for d in docs))
        check("files are in the persistent document folder", len(os.listdir(_DOC_DIR)) == 5)

        pdf_doc = next(d for d in docs if d.original_filename == "Spec v1.pdf")
        md_doc = next(d for d in docs if d.original_filename == "report.md")
        resp = c.get(f"/dev-journal/{work_id}/documents/{pdf_doc.id}")
        check("a PDF opens inline with its bytes", resp.status_code == 200 and resp.data == PDF
              and resp.headers["Content-Type"] == "application/pdf"
              and resp.headers["Content-Disposition"].startswith("inline"))
        resp = c.get(f"/dev-journal/{work_id}/documents/{pdf_doc.id}?download=1")
        check("download forces an attachment with the original name",
              resp.headers["Content-Disposition"].startswith("attachment") and "Spec%20v1.pdf" in resp.headers["Content-Disposition"])
        check("documents are private and not sniffed",
              resp.headers.get("X-Content-Type-Options") == "nosniff" and "no-store" in resp.headers.get("Cache-Control", ""))
        resp = c.get(f"/dev-journal/{work_id}/documents/{md_doc.id}")
        check("Markdown opens as plain text", resp.headers["Content-Type"].startswith("text/plain"))
        check("a document is not reachable through another card",
              c.get(f"/dev-journal/{other_id}/documents/{pdf_doc.id}").status_code == 404)
        check("a person without access cannot open a document",
              p.get(f"/dev-journal/{work_id}/documents/{pdf_doc.id}").status_code == 403)

        # ---- No storage configured: clear failure, nothing written --------
        os.environ.pop("RFONE_DEV_JOURNAL_DOCUMENT_DIR")
        try:
            try:
                document_store.from_environment()
                no_store = False
            except document_store.StorageNotConfiguredError:
                no_store = True
            check("without bucket or folder there is no store (no disk fallback)", no_store)
            with SessionFactory() as s:
                before_docs, before_entries = len(svc.list_documents(s, work_id)), len(svc.list_entries(s, work_id))
            resp = c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf, "files": [(io.BytesIO(PDF), "y.pdf")]},
                          content_type="multipart/form-data", follow_redirects=True)
            check("upload fails with a clear message", "Document storage is not configured" in resp.data.decode())
            resp = c.post(f"/dev-journal/{work_id}/entries", data={
                **entry_base, "entry_type": "ACTIVITY", "body": "con file",
                "files": [(io.BytesIO(PDF), "z.pdf")]}, content_type="multipart/form-data")
            check("an entry with files is refused as a whole", resp.status_code == 400
                  and "Document storage is not configured" in resp.data.decode())
            with SessionFactory() as s:
                check("nothing was recorded without storage",
                      len(svc.list_documents(s, work_id)) == before_docs and len(svc.list_entries(s, work_id)) == before_entries)
            resp = c.post(f"/dev-journal/{work_id}/entries", data={**entry_base, "entry_type": "ACTIVITY", "body": "senza file"})
            check("an entry without files still works without storage", resp.status_code == 302)
        finally:
            os.environ["RFONE_DEV_JOURNAL_DOCUMENT_DIR"] = _DOC_DIR

        # ---- S3 store (fake client) ---------------------------------------
        class FakeS3:
            def __init__(self):
                self.objects = {}

            def put_object(self, Bucket, Key, Body, ServerSideEncryption):
                assert ServerSideEncryption == "AES256"
                self.objects[(Bucket, Key)] = Body

            def get_object(self, Bucket, Key):
                return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

            def delete_object(self, Bucket, Key):
                self.objects.pop((Bucket, Key), None)

        fake = FakeS3()
        dev_journal_routes.store_factory = lambda: document_store.S3DocumentStore("private-bucket", client=fake)
        try:
            c.post(f"/dev-journal/{work_id}/documents", data={"csrf_token": csrf, "files": [(io.BytesIO(PDF), "s3.pdf")]},
                   content_type="multipart/form-data")
            with SessionFactory() as s:
                s3_doc = svc.list_documents(s, work_id)[-1]
            key = s3_doc.storage_path.split("private-bucket/", 1)[-1]
            check("on S3 the key is under dev-journal/documents/ with a random id",
                  re.fullmatch(r"s3://private-bucket/dev-journal/documents/[0-9a-f]{32}", s3_doc.storage_path) is not None)
            check("the S3 object holds the bytes", fake.objects.get(("private-bucket", key)) == PDF)
            check("the S3 document is downloaded through the app",
                  c.get(f"/dev-journal/{work_id}/documents/{s3_doc.id}").data == PDF)
        finally:
            dev_journal_routes.store_factory = document_store.from_environment

        # ---- Events for MyRF ---------------------------------------------
        with SessionFactory() as s:
            events = svc.list_events(s, work_id)
        types = [e.event_type for e in events]
        check("events: work created, phase/status changes, entries, release, corrections, documents",
              types.count("WORK_CREATED") == 1 and types.count("PHASE_CHANGED") == 1
              and types.count("STATUS_CHANGED") == 2 and types.count("ENTRY_ADDED") == 4
              and types.count("RELEASE_RECORDED") == 1 and types.count("ENTRY_EDITED") == 2
              and types.count("DOCUMENT_UPLOADED") == 6, str(types))
        check("every event names its card and author", all(e.work_id == work_id and e.actor_account_id == dev_id for e in events))
        check("a correction event links its entry and the version it replaced",
              all(e.entry_id == decision_id and e.entry_version_id for e in events if e.event_type == "ENTRY_EDITED"))
        check("events are not marked delivered (no delivery state exists)",
              not any("deliver" in col.name for col in dj.DevJournalEvent.__table__.columns))

        # ---- Revoked access -----------------------------------------------
        with SessionFactory() as s:
            account_service.set_domain_access(s, account_id=dev_id, domain_code="DEV_JOURNAL", enabled=False, role_code=None)
            s.commit()
        check("revoking access closes pages immediately", c.get(f"/dev-journal/{work_id}").status_code == 403)
        check("revoking access closes documents and corrections immediately",
              c.get(f"/dev-journal/{work_id}/documents/{pdf_doc.id}").status_code == 403
              and c.get(edit_url).status_code == 403)
        _ = dev2_id
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
        shutil.rmtree(_DOC_DIR, ignore_errors=True)

    print(f"{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
