#!/usr/bin/env python
"""Applications tab, CV list — successive uploads, NEW of the page session, Delete before the evaluation.
ALL DATA IS SYNTHETIC. Throwaway SQLite database and document folder (deleted at the end), FAKE AI (no
network), no email. The session NEW marks are checked in headless Microsoft Edge on the rendered page.

Covered: successive uploads keep earlier CVs and the duplicate checks; NEW column; Delete at the right end,
with the file name in the confirmation; deletion of records and file; shared document, shared application and
shared identity kept; blocked when queued, analyzed or with later data (with the reason); permissions, CSRF,
another Job's CV; Delete and Analyze at the same moment (functions and HTTP) leave no orphan record, no
missing file and no analysis of a deleted CV.

    python test_cv_delete_http.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="selection_cv_delete_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-cv-delete-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from sqlalchemy import func, select, text as sql  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, cv_delete, sp_queue, sp_routes  # noqa: E402

EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if os.path.exists(p)), None)
failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


def cv(i: int, email: str | None = None, extra: str = "") -> str:
    years = 1 + i % 5
    return (f"Synth{i} Sample{i}\n{email or f'synth{i}@example.test'}\n\nEXPERIENCE\n"
            f"Server, Trattoria Esempio {i}, Mount Dora, FL | Jan {2025 - years} - Present\n"
            f"- Full table service for {10 + i} covers\n{extra}")


analyzed_names: list[str] = []
lock = threading.Lock()


def fake_ai(prompt: str) -> dict:
    if "You do not decide and you do not rank" in prompt:
        name = re.search(r"<<<(\w+ Sample\d+)", prompt).group(1)
        with lock:
            analyzed_names.append(name)
        date_text = re.search(r"\| (Jan \d{4} - Present)", prompt).group(1)
        return {"full_name": name, "jobs": [{"employer": "Trattoria Esempio", "title": "Server",
                                            "date_text": date_text, "environment": "Italian full-service",
                                            "relevant": True}],
                "requirements": {"table_service": {"level": 3, "quotes": ["Full table service"]}},
                "competences": [{"name": "table service", "level": "executed", "quote": "Full table service"}],
                "unknowns": []}
    from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
    raise AIProviderUnavailable("fake: not used by the SP path")


def upload(client, t, pid, items):
    files = [(BytesIO(body.encode()), name) for name, body in items]
    return client.post(f"/selection/posizioni/{pid}/sp/upload", data={"csrf_token": t, "cv": files},
                       content_type="multipart/form-data", follow_redirects=True)


def delete(client, t, pid, pc_id):
    return client.post(f"/selection/posizioni/{pid}/sp/cv/{pc_id}/delete", data={"csrf_token": t},
                       follow_redirects=True)


def pcs_of(pid) -> dict[str, int]:
    """file name -> PositionCandidate id, for the Job."""
    with selection_app.SessionFactory() as db:
        out = {}
        for pc in db.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.position_id == pid)).all():
            cand = db.get(m.Candidate, pc.candidate_id)
            raw = db.get(m.RawResume, cand.raw_resume_id)
            out[raw.original_filename] = pc.id
        return out


def graph(pc_id) -> dict:
    """The records behind one Job candidate."""
    with selection_app.SessionFactory() as db:
        pc = db.get(ws.PositionCandidate, pc_id)
        app_ = db.get(m.Application, pc.application_id)
        cand = db.get(m.Candidate, pc.candidate_id)
        raw = db.get(m.RawResume, cand.raw_resume_id)
        return {"pc": pc.id, "application": app_.id, "candidate": cand.id, "raw": raw.id, "person": app_.person_id,
                "path": raw.storage_path}


def exists(model, row_id) -> bool:
    with selection_app.SessionFactory() as db:
        return db.get(model, row_id) is not None


def rows(page: str) -> list[str]:
    table = re.search(r'<table[^>]*id="cv-list".*?</table>', page, re.S)
    return re.findall(r"<tr data-pc=.*?</tr>", table.group(0), re.S) if table else []


def edge_new_cells(page: str, preset: list[int] | None, pid: int) -> list[str] | None:
    """Rendered in headless Edge: the file names whose NEW cell shows NEW, with `preset` already in the tab's
    session storage (earlier uploads of the same page session)."""
    if not EDGE:
        return None
    pre = ("<script>sessionStorage.setItem('selection-sp-new-cvs-%d', '%s');</script>" % (pid, json.dumps(preset))
           if preset is not None else "<script>sessionStorage.clear();</script>")
    html = "<!doctype html><html><head><meta charset='utf-8'>" + pre + "</head><body>" + \
        re.search(r'<table[^>]*id="cv-list".*?</script>', page, re.S).group(0) + "</body></html>"
    path = Path(TMP) / f"edge_{time.time_ns()}.html"
    path.write_text(html, encoding="utf-8")
    profile = Path(TMP) / f"edge_profile_{time.time_ns()}"
    out = subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                          "--dump-dom", path.as_uri()], capture_output=True, encoding="utf-8", errors="replace",
                         timeout=60).stdout or ""
    marked = []
    for row in re.findall(r"<tr data-pc=.*?</tr>", out, re.S):
        if re.search(r'<td class="cv-new"[^>]*><span class="badge gB">NEW</span>', row):
            marked.append(re.findall(r"<td>([^<]+)</td>", row)[0])
    return marked


def new_job(owner, t, owner_id, title, role="SERVER") -> int:
    r = owner.post("/selection/posizioni/nuova", data={
        "csrf_token": t, "title": title, "role_code": role, "location": "Mount Dora",
        "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(owner_id),
        "description": "Synthetic position."}, follow_redirects=True)
    pid = int(re.search(r"/selection/posizioni/(\d+)/", text(r)).group(1))
    owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
        "csrf_token": t, "name": "Restaurant table service", "description": "server restaurant",
        "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
    owner.post(f"/selection/posizioni/{pid}/dettagli", data={
        "csrf_token": t, "headcount": "1", "job_ad_en": "Synthetic ad.", "questions": "When could you start?"})
    owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
    owner.post(f"/selection/posizioni/{pid}/configuration", data={"csrf_token": t, "cv_evaluation": "1"})
    return pid


real_kick = sp_queue.kick
try:
    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as db:
            ids = {}
            for username, admin, domain in (("owner", True, "SELECTION"), ("other", False, "SELECTION"),
                                            ("plain", False, "TIPS")):
                acc = account_svc.create_account(db, username=username, display_name=f"Synthetic {username.title()}",
                                                 password="synthetic-password-1", is_admin=admin)
                account_svc.set_domain_access(db, account_id=acc.id, domain_code=domain, enabled=True, role_code=None)
                ids[username] = (acc.id, acc.session_version)
            db.commit()

        def client(username):
            c = app.test_client()
            if username:
                with c.session_transaction() as sess:
                    sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = ids[username]
            return c

        owner = client("owner")
        t = re.search(r'name="csrf_token" value="([^"]+)"', text(owner.get("/selection/posizioni/nuova"))).group(1)
        ai_adapter._REAL_GENERATE_JSON = fake_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
        sp_queue.GENERATE = None
        docs = sp_routes._cfg.documents

        job1 = new_job(owner, t, ids["owner"][0], "Server delete test")   # requirements not confirmed: no analysis

        # 1. Successive uploads, duplicates, NEW of the page session
        page = text(upload(owner, t, job1, [("cv0.txt", cv(0)), ("cv1.txt", cv(1)), ("cv2.txt", cv(2))]))
        r1 = rows(page)
        check("upload 1: 3 CVs listed, each with NEW in its own first column",
              len(r1) == 3 and all(re.search(r'^<tr data-pc="\d+"><td class="cv-new"[^>]*><span class="badge gB">NEW',
                                             r) for r in r1), r1[:1])
        check("row layout: NEW | file name | upload / status | Delete at the right end",
              all(re.search(r'<td class="cv-new".*?</td>\s*<td>cv\d\.txt</td>.*upload #1.*Waiting for Analyze'
                            r'.*<td style="text-align:right">.*>Delete</button></form></td></tr>$', r, re.S)
                  for r in r1))
        page_first = page
        r = upload(owner, t, job1, [("cv3.txt", cv(3)), ("cv4.txt", cv(4)), ("cv0-again.txt", cv(0))])
        body = text(r)
        r2 = rows(body)
        check("upload 2 keeps the earlier CVs: 2 new imported, the identical CV ignored as exact duplicate, 5 listed",
              "Upload 2: 3 CV(s) received · 2 new imported · 1 exact duplicate(s) ignored" in body and len(r2) == 5,
              re.findall(r"Upload 2:[^<]+", body))
        server_new = [re.findall(r"<td>([^<]+)</td>", x)[0] for x in r2 if 'badge gB">NEW' in x]
        empty_new = [x for x in r2 if re.search(r'<td class="cv-new"[^>]*></td>', x)]
        check("server render: NEW on the 2 CVs just added; the cell of earlier CVs empty, so names stay aligned",
              sorted(server_new) == ["cv3.txt", "cv4.txt"] and len(empty_new) == 3, server_new)
        first_ids = sorted(pcs_of(job1)[n] for n in ("cv0.txt", "cv1.txt", "cv2.txt"))
        marked = edge_new_cells(body, first_ids, job1)
        check("Edge, same page session: NEW on all 5 CVs added across the two uploads",
              marked is not None and sorted(marked) == ["cv0.txt", "cv1.txt", "cv2.txt", "cv3.txt", "cv4.txt"], marked)
        marked = edge_new_cells(body, None, job1)
        check("Edge, a new tab (new page session): NEW only where the page itself just added CVs",
              marked is not None and sorted(marked) == ["cv3.txt", "cv4.txt"], marked)
        marked = edge_new_cells(text(owner.get(f"/selection/posizioni/{job1}/sp")), first_ids, job1)
        check("Edge, reload in the same session: the earlier NEW marks stay",
              marked is not None and sorted(marked) == ["cv0.txt", "cv1.txt", "cv2.txt"], marked)

        # 2. Delete before the evaluation: record and file removed coherently
        names = pcs_of(job1)
        check("Delete asks a confirmation naming the CV",
              'data-msg="Delete the CV “cv1.txt”? It is removed from this Job and cannot be recovered."' in page_first
              and "return confirm(this.dataset.msg)" in page_first)
        g = graph(names["cv1.txt"])
        r = delete(owner, t, job1, names["cv1.txt"])
        body = text(r)
        with selection_app.SessionFactory() as db:
            sp = sp_routes.state(db.get(ws.Position, job1))
            in_uploads = any(names["cv1.txt"] in u["imported"] for u in sp["uploads"])
            events = [e.kind for e in db.scalars(select(ws.Event).where(ws.Event.position_id == job1)).all()]
            pc_events = db.scalar(select(func.count()).select_from(ws.Event).where(
                ws.Event.position_candidate_id == names["cv1.txt"]))
        check("deleted: the message names the CV, the row is gone, the other 4 stay",
              "CV “cv1.txt” deleted." in body and len(rows(body)) == 4 and "cv1.txt</td>" not in body)
        check("deleted: Job link, application, résumé snapshot, document record and the identity it created removed",
              not any(exists(mdl, g[k]) for mdl, k in ((ws.PositionCandidate, "pc"), (m.Application, "application"),
                                                       (m.Candidate, "candidate"), (m.RawResume, "raw"),
                                                       (m.CandidatePerson, "person"))))
        check("deleted: the stored file removed", not os.path.exists(g["path"]), g["path"])
        check("deleted: no reference left in the upload history; its own event removed; the deletion is logged",
              not in_uploads and pc_events == 0 and "CV_DELETED" in events)
        check("deleted: the page is told to drop it from the session NEW marks",
              f'data-removed="[{names["cv1.txt"]}]"' in body)
        r = upload(owner, t, job1, [("cv1.txt", cv(1))])
        check("after deletion the same CV can be uploaded again (imported as new, not a duplicate)",
              "1 new imported · 0 exact duplicate(s)" in text(r), re.findall(r"Upload 3:[^<]+", text(r)))

        # 3. Security: CSRF, permissions, another Job's CV
        target = pcs_of(job1)["cv2.txt"]
        owner.post(f"/selection/posizioni/{job1}/sp/cv/{target}/delete", data={})
        owner.post(f"/selection/posizioni/{job1}/sp/cv/{target}/delete", data={"csrf_token": "forged"})
        check("CSRF: without or with a wrong token nothing is deleted", exists(ws.PositionCandidate, target))
        other, plain, anonymous = client("other"), client("plain"), app.test_client()
        ot = re.search(r'name="csrf_token" value="([^"]+)"', text(other.get("/selection/posizioni/nuova")) or "")
        codes = [other.post(f"/selection/posizioni/{job1}/sp/cv/{target}/delete",
                            data={"csrf_token": ot.group(1) if ot else ""}).status_code,
                 plain.post(f"/selection/posizioni/{job1}/sp/cv/{target}/delete").status_code,
                 anonymous.post(f"/selection/posizioni/{job1}/sp/cv/{target}/delete").status_code]
        check("permissions: another manager, an account without Selection and a visitor cannot delete",
              exists(ws.PositionCandidate, target) and all(c in (302, 401, 403, 404) for c in codes), codes)
        job3 = new_job(owner, t, ids["owner"][0], "Server second Job")
        r = delete(owner, t, job3, target)
        check("another Job's CV cannot be deleted through this Job",
              exists(ws.PositionCandidate, target) and "no longer in the list" in text(r))

        # 4. Shared document, shared application, shared identity
        job2 = new_job(owner, t, ids["owner"][0], "Line cook test", role="LINE_COOK")
        upload(owner, t, job2, [("cv2-for-cook.txt", cv(2))])          # same file, another role
        g2, g2_cook = graph(target), graph(pcs_of(job2)["cv2.txt"])
        r = delete(owner, t, job1, target)
        check("shared document: deleted from this Job, the document and its file kept for the other application",
              "CV “cv2.txt” deleted." in text(r) and not exists(ws.PositionCandidate, g2["pc"])
              and not exists(m.Application, g2["application"]) and exists(m.RawResume, g2["raw"])
              and os.path.exists(g2["path"]) and exists(ws.PositionCandidate, g2_cook["pc"])
              and docs.exists(g2_cook["path"]))
        upload(owner, t, job3, [("cv3-again.txt", cv(3))])               # same file, same role: same application
        g3, g3_other = graph(pcs_of(job1)["cv3.txt"]), graph(pcs_of(job3)["cv3.txt"])
        delete(owner, t, job1, g3["pc"])
        check("shared application (same CV in another Job): only this Job's link removed, application, document "
              "and file kept", g3["application"] == g3_other["application"] and not exists(ws.PositionCandidate, g3["pc"])
              and exists(m.Application, g3["application"]) and exists(m.RawResume, g3["raw"])
              and os.path.exists(g3["path"]) and exists(ws.PositionCandidate, g3_other["pc"]))
        delete(owner, t, job3, g3_other["pc"])
        check("the last Job using it deletes it: application, document and file removed",
              not exists(m.Application, g3["application"]) and not exists(m.RawResume, g3["raw"])
              and not os.path.exists(g3["path"]))
        upload(owner, t, job1, [("cv5.txt", cv(5, email="same.person@example.test")),
                                ("cv6.txt", cv(6, email="same.person@example.test", extra="- Wine list\n"))])
        g5, g6 = graph(pcs_of(job1)["cv5.txt"]), graph(pcs_of(job1)["cv6.txt"])
        delete(owner, t, job1, g6["pc"])
        check("shared identity (same email): the other CV's person kept, the other CV intact",
              g5["person"] == g6["person"] and exists(m.CandidatePerson, g5["person"])
              and exists(ws.PositionCandidate, g5["pc"]) and not exists(m.Application, g6["application"]))

        # 5. Blocked: later data, queued, analyzed (with the reason)
        names = pcs_of(job1)
        with selection_app.SessionFactory() as db:
            db.add(ws.Decision(position_candidate_id=names["cv4.txt"], decision=ws.D_ON_HOLD,
                               actor_account_id=ids["owner"][0], actor_name="Synthetic Owner"))
            ws.log_event(db, position_id=job1, position_candidate_id=names["cv0.txt"], kind="NOTE",
                         detail="Synthetic note", actor_id=ids["owner"][0], actor_name="Synthetic Owner")
            db.commit()
        page = text(owner.get(f"/selection/posizioni/{job1}/sp"))
        r = delete(owner, t, job1, names["cv4.txt"])
        check("later data: a decision blocks the deletion, with the reason",
              exists(ws.PositionCandidate, names["cv4.txt"])
              and "CV “cv4.txt” not deleted: a decision is recorded." in text(r)
              and 'data-msg="“cv4.txt” cannot be deleted: a decision is recorded."' in page)
        delete(owner, t, job1, names["cv0.txt"])
        check("later data: later history events block the deletion", exists(ws.PositionCandidate, names["cv0.txt"]))

        sp_queue.kick = lambda *a, **kw: None        # jobs stay QUEUED
        owner.post(f"/selection/posizioni/{job1}/sp/requirements", data={"csrf_token": t, "action": "approve"})
        owner.post(f"/selection/posizioni/{job1}/sp/analyze", data={"csrf_token": t})
        r = delete(owner, t, job1, names["cv5.txt"])
        check("queued for the AI analysis: blocked, with the reason",
              exists(ws.PositionCandidate, names["cv5.txt"]) and "it is queued for the AI analysis" in text(r))
        upload(owner, t, job1, [("cv7.txt", cv(7))])
        r = delete(owner, t, job1, pcs_of(job1)["cv7.txt"])
        check("a CV uploaded once requirements are confirmed is queued at once, so it is blocked too",
              "it is queued for the AI analysis" in text(r))
        sp_queue.kick = real_kick
        sp_queue.kick(force=True)
        for _ in range(300):
            if not owner.get(f"/selection/posizioni/{job1}/sp/status").get_json().get("ANALYZING"):
                break
            time.sleep(0.1)
        r = delete(owner, t, job1, names["cv5.txt"])
        check("analyzed: blocked, with the reason", exists(ws.PositionCandidate, names["cv5.txt"])
              and "it has already been analyzed" in text(r))

        # 6. Delete and Analyze at the same moment
        sp_queue.kick = lambda *a, **kw: None
        job4 = new_job(owner, t, ids["owner"][0], "Server race test")
        upload(owner, t, job4, [(f"race{i}.txt", cv(20 + i)) for i in range(24)])
        race = sorted(pcs_of(job4).values())
        outcomes, bad = {"DELETED": 0, "BLOCKED": 0}, []
        for n, pc_id in enumerate(race):
            g = graph(pc_id)
            barrier, result = threading.Barrier(2), {}
            # Alternate who starts first (and none), so both outcomes really happen.
            delay_delete, delay_enqueue = (0.03, 0) if n % 3 == 0 else (0, 0.03) if n % 3 == 1 else (0, 0)

            def do_delete():
                with selection_app.SessionFactory() as db:
                    barrier.wait()
                    time.sleep(delay_delete)
                    result["delete"] = cv_delete.delete_cv(
                        db, documents=docs, position_id=job4, pc_id=pc_id, actor_id=ids["owner"][0],
                        actor_name="Synthetic Owner", load_state=sp_routes.state, save_state=sp_routes.save_state)

            def do_enqueue():
                with selection_app.SessionFactory() as db:
                    barrier.wait()
                    time.sleep(delay_enqueue)
                    result["queued"] = sp_queue.enqueue(db, [pc_id], 1)

            threads = [threading.Thread(target=do_delete), threading.Thread(target=do_enqueue)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            status = result["delete"]["status"]
            outcomes[status] = outcomes.get(status, 0) + 1
            with selection_app.SessionFactory() as db:
                jobs = db.scalar(select(func.count()).select_from(ws.Proposal).where(
                    ws.Proposal.position_candidate_id == pc_id))
            ok = ((status == "DELETED" and result["queued"] == 0 and jobs == 0 and not exists(ws.PositionCandidate, pc_id)
                   and not exists(m.RawResume, g["raw"]) and not os.path.exists(g["path"]))
                  or (status == "BLOCKED" and result["queued"] == 1 and jobs == 1
                      and exists(ws.PositionCandidate, pc_id) and os.path.exists(g["path"])))
            if not ok:
                bad.append((pc_id, status, result.get("queued"), jobs))
        check(f"race Delete/Analyze x{len(race)} (functions): always either deleted and never queued, or queued and "
              f"never deleted; file and records consistent  {outcomes}",
              not bad and outcomes["DELETED"] and outcomes["BLOCKED"], bad)

        # The narrowest window: Analyze has already chosen the CV (read done) when the Delete commits.
        upload(owner, t, job4, [("window.txt", cv(50))])
        victim = pcs_of(job4)["window.txt"]
        real_lock = sp_queue._write_lock

        def delete_in_window():
            with selection_app.SessionFactory() as other_db:
                result["window"] = cv_delete.delete_cv(
                    other_db, documents=docs, position_id=job4, pc_id=victim, actor_id=ids["owner"][0],
                    actor_name="Synthetic Owner", load_state=sp_routes.state, save_state=sp_routes.save_state)

        class LockWithWindow:
            """The writer lock; the first entry (Analyze's, after its read) lets a whole Delete run first."""
            hook = staticmethod(delete_in_window)

            def __enter__(self):
                hook, LockWithWindow.hook = LockWithWindow.hook, None
                if hook:
                    th = threading.Thread(target=hook)
                    th.start()
                    th.join()
                return real_lock.__enter__()

            def __exit__(self, *exc):
                return real_lock.__exit__(*exc)

        sp_queue._write_lock, result = LockWithWindow(), {}
        try:
            with selection_app.SessionFactory() as db:
                queued = sp_queue.enqueue(db, [victim], 1)
        finally:
            sp_queue._write_lock = real_lock
        check("Delete committed after Analyze chose the CV: deleted, no job created, no error",
              result["window"]["status"] == "DELETED" and queued == 0 and not exists(ws.PositionCandidate, victim),
              (result.get("window", {}).get("status"), queued))

        sp_queue.kick = real_kick
        analyzed_names.clear()
        http_bad, http_out = [], []
        for n in range(4):
            pid = new_job(owner, t, ids["owner"][0], f"Server HTTP race {n}")
            upload(owner, t, pid, [(f"h{n}-{i}.txt", cv(60 + n * 3 + i)) for i in range(3)])
            owner.post(f"/selection/posizioni/{pid}/sp/requirements", data={"csrf_token": t, "action": "approve"})
            victim = sorted(pcs_of(pid).values())[n % 3]
            gv = graph(victim)
            name = re.search(r"Synth\d+ Sample\d+", cv(60 + n * 3 + (n % 3))).group(0)
            c_delete, barrier = client("owner"), threading.Barrier(2)
            dt = re.search(r'name="csrf_token" value="([^"]+)"', text(c_delete.get(f"/selection/posizioni/{pid}/sp"))).group(1)
            res = {}

            def http_delete():
                barrier.wait()
                time.sleep(0.15 if n % 2 else 0)          # odd rounds: Analyze starts first
                res["d"] = c_delete.post(f"/selection/posizioni/{pid}/sp/cv/{victim}/delete", data={"csrf_token": dt}).status_code

            def http_analyze():
                barrier.wait()
                res["a"] = owner.post(f"/selection/posizioni/{pid}/sp/analyze", data={"csrf_token": t}).status_code

            threads = [threading.Thread(target=http_delete), threading.Thread(target=http_analyze)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            for _ in range(300):
                if not owner.get(f"/selection/posizioni/{pid}/sp/status").get_json().get("ANALYZING"):
                    break
                time.sleep(0.1)
            deleted = not exists(ws.PositionCandidate, victim)
            http_out.append("deleted" if deleted else "analyzed")
            if res != {"d": 302, "a": 302} or (deleted and (name in analyzed_names or os.path.exists(gv["path"])
                                                            or exists(m.RawResume, gv["raw"]))) \
                    or (not deleted and (name not in analyzed_names or not os.path.exists(gv["path"]))):
                http_bad.append((n, res, deleted, name in analyzed_names))
        check(f"race Delete/Analyze over HTTP with the real queue workers: a deleted CV is never analyzed, an "
              f"analyzed CV is never deleted  {http_out}",
              not http_bad and "deleted" in http_out and "analyzed" in http_out, http_bad)

        # 7. Integrity of the whole database and of the document folder
        with selection_app.SessionFactory() as db:
            fk = db.execute(sql("PRAGMA foreign_key_check")).all()
            orphans = db.scalar(sql("SELECT count(*) FROM selection_workspace_events e WHERE e.position_candidate_id "
                                    "IS NOT NULL AND e.position_candidate_id NOT IN "
                                    "(SELECT id FROM selection_workspace_position_candidates)"))
            stale_upload_refs = []
            pc_ids = set(db.scalars(select(ws.PositionCandidate.id)).all())
            for pos in db.scalars(select(ws.Position)).all():
                for u in sp_routes.state(pos).get("uploads", []):
                    stale_upload_refs += [i for i in u["imported"] if i not in pc_ids]
            missing = [r.storage_path for r in db.scalars(select(m.RawResume)).all()
                       if r.storage_path and not os.path.exists(r.storage_path)]
        check("integrity: no foreign-key violation, no orphan event, no stale upload reference, no missing file",
              not fk and not orphans and not stale_upload_refs and not missing,
              (fk[:3], orphans, stale_upload_refs[:3], missing[:3]))
finally:
    sp_queue.kick = real_kick
    time.sleep(0.5)
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
