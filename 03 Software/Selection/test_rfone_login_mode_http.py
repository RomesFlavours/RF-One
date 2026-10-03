#!/usr/bin/env python
"""SELECTION_AWS_PUBLISH_001 — Selection as deployed: behind RF-One's login,
under /selection/, with résumés in a private S3 bucket.

Runs the real Flask app with RFONE_SELECTION_REQUIRE_RFONE_LOGIN=1 on a
throwaway SQLite database and an in-memory stand-in for S3 (no AWS call).
ALL DATA IS SYNTHETIC.

  1. without an RF-One session: redirected to RF-One's login, back to the
     page asked for; a revoked session counts as none;
  2. an account without the SELECTION Domain: 403; with it: 200;
  3. the acting identity is the account's own (one per account); choosing
     or registering an identity by hand is switched off;
  4. pages and links work under /selection/;
  5. an upload is stored in S3 only (nothing in uploads/), the original is
     served through the app; a duplicate or a failed import leaves no
     orphan document.
"""

from __future__ import annotations

import os
import sys
import tempfile
from io import BytesIO

_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="selection_login_mode_test_")
os.close(_FD)
os.remove(_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-login-mode-test-secret"
os.environ.pop("RFONE_PUBLIC_BASE_URL", None)

import app as selection_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import document_store  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402

BUCKET = "synthetic-selection-documents"
RESUME = """Alex Synthetic
alex.synthetic@example.test

EXPERIENCE
Team Leader
Trattoria Esempio, Hamilton, ON
Mar 2022 - Present
- Coordinated a team of 6 servers per shift
"""


class FakeS3:
    """Just the four calls the document store makes."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        assert bucket == BUCKET and ExtraArgs == {"ServerSideEncryption": "AES256"}
        with open(path, "rb") as handle:
            self.objects[key] = handle.read()

    def delete_object(self, Bucket, Key, VersionId=None):
        assert VersionId == "v1", "a discarded document must be deleted version by version"
        self.objects.pop(Key, None)

    def list_object_versions(self, Bucket, Prefix):
        return {"Versions": [{"Key": k, "VersionId": "v1"} for k in self.objects if k.startswith(Prefix)]}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)

    def get_object(self, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key])}


def main() -> int:
    results: list[tuple[str, bool]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, bool(condition)))
        print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not condition else ""))

    fake_s3 = FakeS3()
    selection_app.DOCUMENTS = document_store.S3DocumentStore(BUCKET, client=fake_s3)
    uploads_before = set(os.listdir(selection_app.UPLOAD_DIR))
    try:
        with isolated_ai_client():
            with selection_app.SessionFactory() as s:
                allowed = account_svc.create_account(s, username="sel-allowed", display_name="Synthetic Allowed",
                                                     password="Synthetic-pass-1")
                other = account_svc.create_account(s, username="sel-other", display_name="Synthetic Other",
                                                   password="Synthetic-pass-2")
                plain = account_svc.create_account(s, username="sel-plain", display_name="Synthetic Plain",
                                                   password="Synthetic-pass-3")
                for acc in (allowed, other):
                    account_svc.set_domain_access(s, account_id=acc.id, domain_code="SELECTION", enabled=True,
                                                  role_code=None)
                account_svc.set_domain_access(s, account_id=plain.id, domain_code="TIPS", enabled=True,
                                              role_code=None)
                s.commit()
                ids = {a.username: (a.id, a.session_version) for a in (allowed, other, plain)}

            def client_for(username: str | None, version_offset: int = 0):
                client = selection_app.app.test_client()
                if username:
                    account_id, version = ids[username]
                    with client.session_transaction() as sess:
                        sess[shared_session.SESSION_ACCOUNT_KEY] = account_id
                        sess[shared_session.SESSION_VERSION_KEY] = version + version_offset
                return client

            # --- 1. no session / revoked session -> RF-One login --------------
            anon = client_for(None).get("/selection/applications?role=SERVER")
            check("1. no RF-One session: redirected to RF-One's login, coming back to the page asked for",
                  anon.status_code == 302
                  and anon.headers["Location"] == "https://rfone.example.test/login?next=%2Fselection%2Fapplications%3Frole%3DSERVER",
                  anon.headers.get("Location", ""))
            revoked = client_for("sel-allowed", version_offset=1).get("/selection/")
            check("1. a revoked session (password changed) counts as no session", revoked.status_code == 302)
            anon_doc = client_for(None).get("/selection/candidate/1/original-cv")
            anon_upload = client_for(None).post("/selection/api/upload", data={"target_role": "SERVER"})
            check("1. documents and uploads are refused without a session too",
                  anon_doc.status_code == 302 and anon_upload.status_code == 302)

            # --- 2. SELECTION Domain required --------------------------------
            check("2. an account without the SELECTION Domain gets 403",
                  client_for("sel-plain").get("/selection/").status_code == 403)
            allowed_client = client_for("sel-allowed")
            home = allowed_client.get("/selection/")
            check("2. an account with the SELECTION Domain opens Selection", home.status_code == 200)
            html = home.get_data(as_text=True)

            # --- 4. served under /selection/ -------------------------------------
            check("4. links carry the /selection prefix and lead back to RF-One",
                  'href="/selection/applications"' in html and 'href="https://rfone.example.test/">RF-One</a>' in html)

            # --- 5. documents in S3 only ---------------------------------------
            up = allowed_client.post("/selection/api/upload", data={
                "target_role": "FOH_SUPERVISOR", "resume_file": (BytesIO(RESUME.encode()), "alex.txt")},
                content_type="multipart/form-data").get_json()
            with selection_app.SessionFactory() as s:
                raw = s.query(m.RawResume).one()
            check("5. the upload is imported and its document is stored in the private bucket",
                  up["status"] == "COMPLETED" and raw.storage_path.startswith(f"s3://{BUCKET}/selection/resumes/")
                  and len(fake_s3.objects) == 1, f"{up} {raw.storage_path}")
            check("5. nothing is written to the service's own uploads/ folder",
                  set(os.listdir(selection_app.UPLOAD_DIR)) == uploads_before)
            original = allowed_client.get(f"/selection/candidate/{up['candidate_id']}/original-cv")
            check("5. the original CV is served through the app, behind the login",
                  original.status_code == 200 and original.data == RESUME.encode()
                  and original.mimetype == "text/plain")
            dup = allowed_client.post("/selection/api/upload", data={
                "target_role": "FOH_SUPERVISOR", "resume_file": (BytesIO(RESUME.encode()), "alex_again.txt")},
                content_type="multipart/form-data").get_json()
            check("5. a duplicate upload leaves no second document in the bucket",
                  dup["status"] == "DUPLICATE" and len(fake_s3.objects) == 1)
            failed = allowed_client.post("/selection/api/upload", data={
                "target_role": "SERVER", "resume_file": (BytesIO(b""), "empty.txt")},
                content_type="multipart/form-data").get_json()
            check("5. a failed import leaves no document in the bucket",
                  failed["status"] == "FAILED" and len(fake_s3.objects) == 1)
            check("5. a stored path outside the app's own prefix is never served",
                  selection_app.DOCUMENTS.read(f"s3://{BUCKET}/other/secret.pdf") is None
                  and selection_app.DOCUMENTS.read("s3://another-bucket/selection/resumes/x") is None)
            # --- 3. identity is the account's (checked on the decision page) ----
            decision = allowed_client.get(f"/selection/applications/{up['application_id']}/decision").get_data(as_text=True)
            check("3. the page acts as the logged-in account, with no way to switch",
                  "Acting as <strong>Synthetic Allowed</strong>" in decision and "not you?" not in decision
                  and "(switch)" not in decision and "Acting Identity</a>" not in html)
            check("3. choosing or registering an identity by hand is switched off",
                  allowed_client.get("/selection/identity/switch").status_code == 404
                  and allowed_client.post("/selection/identity/register", data={"display_name": "X"}).status_code == 404)
            client_for("sel-other").get(f"/selection/applications/{up['application_id']}/decision")
            with selection_app.SessionFactory() as s:
                rows = s.query(m.ActingIdentity).filter_by(authentication_provider="rfone-account").all()
                by_subject = {r.external_subject_id: r.display_name for r in rows}
            check("3. one acting identity per RF-One account, tied to its id",
                  by_subject == {str(ids["sel-allowed"][0]): "Synthetic Allowed",
                                 str(ids["sel-other"][0]): "Synthetic Other"}, f"{by_subject}")
    finally:
        selection_app._engine.dispose()
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(_DB_PATH + suffix):
                try:
                    os.remove(_DB_PATH + suffix)
                except OSError:
                    pass

    passed = sum(1 for _, ok in results if ok)
    failed_count = len(results) - passed
    print(f"\n{passed} passed, {failed_count} failed.")
    print("ALL CHECKS PASSED" if failed_count == 0 else "SOME CHECKS FAILED")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
