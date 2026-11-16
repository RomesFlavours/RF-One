#!/usr/bin/env python
"""Successive CV uploads in one Job — duplicates, one Applications board, AI readings never repeated.
ALL DATA IS SYNTHETIC. Throwaway SQLite database, FAKE AI (no network, calls counted), no email.

Updated 2026-11-15 (A7). The original path (PO verification list, 1 Nov 2026) is kept on the approved flow:
12 CVs uploaded -> 8 more -> 20 candidates -> an identical CV is not imported again -> a same-email CV is
imported and flagged as a possible duplicate -> one board holds every candidate -> AI readings are never
repeated. The retired CV Selection SP engine (SP ranking page, automatic SP reading at upload, SP queue,
SP requirement versions, manual ranking moves) is no longer part of Selection: its former address opens
Applications, uploads are upload-only and the CVs are read by "Applica Filtri e Regole" with the PDL rules.
Local Italian UI labels.

    python test_sp_integration_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import json
import tempfile
import threading
import time
from unittest.mock import patch
from datetime import timedelta
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_sp_integration_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-sp-integration-test-secret"
os.environ["RFONE_UI_LANGUAGE"] = "it"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, sp_queue, routes, conversational_rules as conversation  # noqa: E402
from workspace.role_catalog import JobRole  # noqa: E402
from workspace.pdl_rule_store import PDLRule  # noqa: E402
from rfone_data_store.selection import requirements_service as req  # noqa: E402

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


FIRST = ["Ava", "Ben", "Cleo", "Dan", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jade", "Kai", "Lia",
         "Max", "Nia", "Oto", "Pia", "Quin", "Rae", "Sol", "Tess"]


def cv(i: int, email: str | None = None) -> str:
    name = f"{FIRST[i]} Sample{i}"
    years = 1 + i % 5
    return (f"{name}\n{email or FIRST[i].lower() + str(i) + '@example.test'}\n\nEXPERIENCE\n"
            f"Server, Trattoria Esempio {i}, Mount Dora, FL | Jan {2025 - years} - Present\n"
            f"- Full table service for {10 + i} covers\n")


calls = {"reader": 0, "cv_ai": 0}
lock = threading.Lock()


def fake_cv_ai(prompt: str) -> dict:
    """Any AI résumé reading at upload time (must not happen: uploads are upload-only)."""
    with lock:
        calls["cv_ai"] += 1
    from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
    raise AIProviderUnavailable("fake: uploads must not call the AI")


def fake_reader(prompt: str) -> dict:
    """The PDL-rule reader of Applica Filtri e Regole (deterministic, quotes taken from the CV)."""
    marker = '{"task": "cv_observations"'
    if marker in prompt:
        data = json.loads(prompt[prompt.index(marker):]);quote = data["CV"].splitlines()[0]
        return {"sections": [{"key": k, "bullets": [{"text": "Osservazione sintetica " + k, "quotes": [quote], "uncertain": False}]}
                             for k in ("profile", "strengths", "limits", "clarifications", "conclusion")]}
    with lock:
        calls["reader"] += 1
    data = json.loads(prompt[prompt.index('{"PDL":'):]);first = data["CV"].splitlines()[0]
    return {"priority": "UNCLEAR", "reason": "Valutazione sintetica.",
            "rules": [{"id": r["id"], "outcome": "IN_LINEA", "reason": "Servizio ai tavoli nel CV.", "quotes": [first]}
                      for r in data["rules"]]}


def upload(client, t, pid, items):
    files = [(BytesIO(body.encode()), name) for name, body in items]
    return client.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "modal": "1", "cv": files},
                       content_type="multipart/form-data", follow_redirects=True)


def apply_rules(client, t, pid):
    """Explicit Apply; wait for the background reader by joining it (no concurrent SQLite requests)."""
    assert client.post(f"/selection/posizioni/{pid}/applica-regole-pdl", data={"csrf_token": t}).status_code == 302
    thread = conversation._jobs.get(pid)
    if thread:
        thread.join(60)
    return client.get(f"/selection/posizioni/{pid}/lettura-ai/stato").get_json()


def total(pid):
    with selection_app.SessionFactory() as db:
        return db.scalar(select(func.count()).select_from(ws.PositionCandidate).where(ws.PositionCandidate.position_id == pid))


try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as db:
            acc = account_svc.create_account(db, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(db, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            db.add(JobRole(code="SERVER", name="Server", name_key="server", active=True, version=1))
            rs = req.create_requirement_set(db, restaurant_id=routes._restaurant_id(db), name="Synthetic", target_role="SERVER")
            job = ws.Position(title="Server upload test", role_code="SERVER", location_label="Mount Dora",
                              timezone="America/New_York", status="OPEN", manager_account_id=acc.id,
                              created_by_account_id=acc.id, requirement_set_id=rs.id)
            db.add(job)
            db.add(PDLRule(role_code="SERVER", section="requirements", title="Servizio ai tavoli",
                           condition={"op": "natural_language", "need": "Servizio ai tavoli",
                                      "instruction": "IN_LINEA se il CV riporta servizio ai tavoli."},
                           weight=1, conversation=[], proposal_key="SERVER-req", created_by=acc.id))
            db.commit()
            pid, owner_id = job.id, (acc.id, acc.session_version)
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_id
        t = re.search(r'name="csrf_token" value="([^"]+)"', text(owner.get(f"/selection/posizioni/{pid}/sp/upload?modal=1"))).group(1)
        ai_adapter._REAL_GENERATE_JSON = fake_cv_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        sp_queue.GENERATE = None

        # 1. One upload entry per Job; the retired SP page opens Applications
        dash = text(owner.get("/selection/"))
        old_sp = owner.get(f"/selection/posizioni/{pid}/sp")
        check("one Upload Resume per Job row, opened as a modal; no file field on the Jobs list",
              re.search(rf'id="upload-{pid}"[^>]*href="/selection/posizioni/{pid}/sp/upload"', dash) is not None
              and 'type="file"' not in dash)
        check("the former SP page address opens Applications", old_sp.status_code == 302)

        with patch.object(conversation.rule_ai, "generate", side_effect=fake_reader):
            # 2-3. First upload: 12 CVs, upload-only
            body = text(upload(owner, t, pid, [(f"cv{i}.txt", cv(i)) for i in range(12)]))
            check("upload 1: 12 ricevuti · 12 nuovi · 0 duplicati",
                  "12 file ricevuti · 12 nuovi CV caricati · 0 duplicati ignorati" in body, re.findall(r"\d+ file ricevuti[^<]+", body))
            check("upload 1: no AI reading at upload", calls == {"reader": 0, "cv_ai": 0}, calls)

            # 4-5. Second upload: 8 more; total 20
            body = text(upload(owner, t, pid, [(f"cv{i}.txt", cv(i)) for i in range(12, 20)]))
            check("upload 2: 8 ricevuti · 8 nuovi", "8 file ricevuti · 8 nuovi CV caricati" in body)
            check("total: 20 candidates in the Job", total(pid) == 20, total(pid))

            # 6. Identical CV again: not imported
            body = text(upload(owner, t, pid, [("cv3-again.txt", cv(3))]))
            check("exact duplicate: the identical CV is ignored, total still 20",
                  "1 duplicati ignorati" in body and total(pid) == 20, total(pid))

            # Possible duplicate: same email, different CV -> imported and flagged, never merged
            body = text(upload(owner, t, pid, [("cv5-new-version.txt", cv(5).replace("Full table service", "Wine service")
                                                + "- Trained two new servers\n")]))
            check("possible duplicate: same email, different CV -> imported and flagged for the manager",
                  "1 nuovi CV caricati" in body and "possibile duplicato da verificare" in body and total(pid) == 21)
            check("uploads: still no AI reading", calls == {"reader": 0, "cv_ai": 0}, calls)

            # 7. One board with everyone
            board = text(owner.get(f"/selection/posizioni/{pid}?tab=candidature"))
            check("one Applications board holds every candidate (21)", len(re.findall(r'<tr id="candidate-\d+"', board)) == 21)

            # 8. Readings are never repeated
            status = apply_rules(owner, t, pid)
            check("Apply: 21 CVs read once each", status["state"] == "COMPLETED" and calls["reader"] == 21, (status, calls))
            status = apply_rules(owner, t, pid)
            check("Apply again with nothing changed: no new AI reading", status["state"] == "COMPLETED" and calls["reader"] == 21, (status, calls))
            upload(owner, t, pid, [("cv-new.txt", cv(0).replace("Ava Sample0", "Ava Sample20").replace("ava0@", "ava20@"))])
            status = apply_rules(owner, t, pid)
            check("after one new CV: only that CV is read", status["state"] == "COMPLETED" and calls["reader"] == 22 and total(pid) == 22, (status, calls))
            check("no AI résumé reading outside the PDL reader", calls["cv_ai"] == 0, calls)

        first_pc = int(re.findall(r'<tr id="candidate-(\d+)"', board)[0])
        check("original CV opens through Selection",
              owner.get(f"/selection/posizioni/{pid}/candidati/{first_pc}/cv-originale").status_code == 200)
        other = app.test_client()
        check("access: not signed in -> no Applications page",
              other.get(f"/selection/posizioni/{pid}?tab=candidature").status_code in (302, 401, 403))
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
