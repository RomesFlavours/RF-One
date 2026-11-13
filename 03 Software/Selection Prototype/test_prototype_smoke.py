"""End-to-end smoke test of the prototype's five functions, on a throwaway
data folder and SYNTHETIC résumés only. No AI provider can be reached: the
provider name is invalid for this process, on top of the prototype's guard;
the AI section uses a fake transport.

    python test_prototype_smoke.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selproto_smoke_")
os.environ["RFONE_SELECTION_PROTOTYPE_DATA"] = TMP
os.environ["RFONE_AI_PROVIDER"] = "DISABLED_IN_SMOKE_TEST"

import app as proto  # noqa: E402
from sqlalchemy import select  # noqa: E402

CV_STRONG = """Jordan Example
jordan@example.test  (407) 555-0101

EXPERIENCE
Server, Trattoria Esempio, Orlando, FL | Mar 2021 - Present
- Table service for 40 covers, upselling wine
Food Runner, Bistro Prova, Orlando, FL | Jan 2019 - Feb 2021
- Ran food to tables

CERTIFICATIONS
Food Handler Certificate
"""
CV_WEAK = """Casey Sample
casey@example.test

EXPERIENCE
Cashier, Store Demo, Tampa, FL | Jun 2020 - Present
- Cash register
"""
failures = []


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def token(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def text(r) -> str:
    return r.get_data(as_text=True)


def local_input(days: int, hour: int) -> str:
    return (datetime.now() + timedelta(days=days)).replace(hour=hour, minute=0).strftime("%Y-%m-%dT%H:%M")


try:
    c = proto.app.test_client()
    t = token(text(c.get("/", follow_redirects=True)))
    c.post("/primo-accesso", data={"csrf_token": t, "display_name": "Owner Test", "username": "owner",
                                   "password": "synthetic-pass-1", "password2": "synthetic-pass-1"})
    t = token(text(c.get("/accesso")))
    r = c.post("/accesso", data={"csrf_token": t, "username": "owner", "password": "synthetic-pass-1"},
               follow_redirects=True)
    check("login with RF-One account model", "+ Nuova posizione" in text(r))
    t = token(text(r))

    # 1. CREATE POSITION (AI off)
    r = c.post("/posizioni/nuova", data={"csrf_token": t, "title": "Server", "role_code": "SERVER",
                                         "location": "Mount Dora", "timezone": "America/New_York", "headcount": "2",
                                         "manager_account_id": "1", "description": "Cerchiamo 2 server."},
               follow_redirects=True)
    pid = int(re.search(r"/posizioni/(\d+)/requisiti/aggiungi", text(r)).group(1))
    check("position created with standard questions from Selection", "Are you available to work weekends?" in text(r))
    c.post(f"/posizioni/{pid}/requisiti/aggiungi", data={
        "csrf_token": t, "name": "Server experience", "description": "server waiter table service",
        "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
    r = c.post(f"/posizioni/{pid}/approva", data={"csrf_token": t}, follow_redirects=True)
    check("approval refused without job ad", "Non ancora approvabile" in text(r))
    c.post(f"/posizioni/{pid}/dettagli", data={
        "csrf_token": t, "headcount": "2", "job_ad_en": "Join our team in Mount Dora as a Server.",
        "questions": "Are you available to work weekends?\nWhen could you start?"})
    r = c.post(f"/posizioni/{pid}/approva", data={"csrf_token": t}, follow_redirects=True)
    check("position approved and open", "Pagina di candidatura" in text(r) and "Aperta" in text(r))
    with proto.SessionFactory() as db:
        public_token = db.get(proto.ps.Position, pid).public_token

    # 2. RECEIVE: public page, CV + interview, pause and resume
    anon = proto.app.test_client()
    page = text(anon.get(f"/jobs/{public_token}"))
    check("public job page with JobPosting data", "Join our team" in page and '"JobPosting"' in page)
    r = anon.post(f"/jobs/{public_token}", data={
        "csrf_token": token(page), "name": "Jordan Example", "email": "jordan@example.test", "consent": "1",
        "cv": (BytesIO(CV_STRONG.encode()), "jordan.txt")}, content_type="multipart/form-data")
    resume_url = r.headers["Location"]
    page = text(anon.get(resume_url))
    check("interview starts with approved standard question", "Question 1 of 2" in page and "weekends" in page)
    r = anon.post(resume_url, data={"csrf_token": token(page), "index": "0", "answer": "Yes, every weekend.",
                                    "input_mode": "TEXT", "action": "later"})
    check("save and finish later", "personal link" in text(r))
    page = text(proto.app.test_client().get(resume_url))  # resumed from another browser
    check("resume continues at question 2", "Question 2 of 2" in page)
    anon2 = proto.app.test_client()
    page = text(anon2.get(resume_url))
    anon2.post(resume_url, data={"csrf_token": token(page), "index": "1", "answer": "I can start next Monday.",
                                 "input_mode": "VOICE", "action": "next"})
    page = text(anon2.get(resume_url))
    check("review page before sending", "Send my application" in page)
    page = text(anon2.post(resume_url, data={"csrf_token": token(page), "action": "submit"}, follow_redirects=True))
    check("application submitted", "your application is complete" in page)

    data = {"csrf_token": t, "cv": [(BytesIO(CV_WEAK.encode()), "casey.txt"), (BytesIO(CV_STRONG.encode()), "copy.txt")]}
    r = c.post(f"/posizioni/{pid}/cv", data=data, content_type="multipart/form-data", follow_redirects=True)
    check("manual multi-upload with duplicate detection", "casey.txt: importato" in text(r) and "copy.txt: già presente" in text(r))

    # 3. EVALUATE
    html = text(c.get(f"/posizioni/{pid}?tab=valutazione"))
    check("strong CV proposed for interview", "Jordan Example" in html.split("Da approfondire <span")[0])
    check("weak CV in 'essentials not shown'", "Casey Sample" in html.split("Requisiti essenziali non dimostrati <span")[1])
    ids = re.findall(r'name="pc_id" value="(\d+)"', html)
    r = c.get(f"/posizioni/{pid}/confronto?" + "&".join(f"pc_id={i}" for i in ids))
    check("comparison side by side with answers", "Confronto candidati" in text(r) and "I can start next Monday." in text(r))
    pc_jordan = int(re.search(r'value="(\d+):INTERVIEW"', html).group(1))
    r = c.post(f"/posizioni/{pid}/decisioni", data={"csrf_token": t, "quick": f"{pc_jordan}:INTERVIEW"}, follow_redirects=True)
    check("quick decision 'to interview'", "Decisione registrata" in text(r))

    # 4. INTERVIEWS: direct booking and slot offer
    r = c.post(f"/posizioni/{pid}/candidati/{pc_jordan}/colloquio", data={
        "csrf_token": t, "kind": "PHONE", "duration": "30", "place": "(407) 555-0000", "mode": "book",
        "starts_at": local_input(2, 10)}, follow_redirects=True)
    check("appointment booked + invite drafted", "Colloquio registrato" in text(r) and "Invito al colloquio" in text(r))
    r = c.post(f"/posizioni/{pid}/candidati/{pc_jordan}/colloquio", data={
        "csrf_token": t, "kind": "IN_PERSON", "duration": "45", "place": "Restaurant", "mode": "offer",
        "slot": [local_input(3, 15), local_input(4, 16)]}, follow_redirects=True)
    slot_link = re.search(r'href="(http://localhost/interview/[^"]+)"', text(r)).group(1).replace("http://localhost", "")
    check("slot offer link + message with the link", "Proposta di orari" in text(r) and slot_link in text(r))
    page = text(anon.get(slot_link))
    slot = re.search(r'name="slot" value="([^"]+)"', page).group(1)
    r = anon.post(slot_link, data={"csrf_token": token(page), "slot": slot})
    check("candidate picks a slot", "Your interview is booked" in text(r))
    r = c.get(f"/posizioni/{pid}?tab=colloqui")
    check("internal calendar shows both interviews", text(r).count("Jordan Example") >= 2 and "scelto dal candidato" in text(r))

    # 5. DECIDE: approved message, final outcome, history, manual close
    cand = text(c.get(f"/posizioni/{pid}/candidati/{pc_jordan}"))
    mid = re.search(r"/posizioni/\d+/messaggi/(\d+)", cand).group(1)
    r = c.post(f"/posizioni/{pid}/messaggi/{mid}", data={"csrf_token": t, "action": "approve",
                                                          "body": "Hi Jordan, see you soon. Owner Test"}, follow_redirects=True)
    check("message approved by the manager", "approvato" in text(r) and "Copia testo" in text(r))
    r = c.post(f"/posizioni/{pid}/decisioni", data={"csrf_token": t, "pc_id": str(pc_jordan), "decision": "NOT_SELECTED"},
               follow_redirects=True)
    check("'not selected' needs a reason", "indicare il motivo" in text(r))
    c.post(f"/posizioni/{pid}/decisioni", data={"csrf_token": t, "pc_id": str(pc_jordan), "decision": "HIRED"})
    r = c.get(f"/posizioni/{pid}?tab=decisioni")
    check("outcome and history recorded", "1 / 2" in text(r) and "Jordan Example: Assunto" in text(r))
    r = c.post(f"/posizioni/{pid}/stato", data={"csrf_token": t, "action": "close"}, follow_redirects=True)
    check("position closed manually; public page closed",
          "Chiusa" in text(r) and "not accepting" in text(anon.get(f"/jobs/{public_token}")))

    # AI path with a FAKE transport (no network): position draft; evaluation quoting an answer.
    def fake_ai(prompt):
        if "open a position" in prompt:
            return {"requirements": [{"name": "Esperienza ai tavoli", "description": "", "category": "Experience",
                                      "criticality": "MUST_HAVE", "trainability": "PARTIALLY_TRAINABLE",
                                      "cv_keywords": ["server"], "why": "dalla descrizione"}],
                    "headcount": 2, "job_ad_en": "We are hiring. [Pay: to be completed]", "open_questions": ["Paga?"]}
        if "APPROVED" in prompt:
            ids = [int(x) for x in re.findall(r"id=(\d+)", prompt)]
            return {"requirements": [{"id": ids[0], "status": "EVIDENCED",
                                      "quotes": ["Yes, every weekend.", "Invented sentence"], "explanation": "ok"}],
                    "interview_questions": []}
        raise proto.AIProviderUnavailable("fake: not used")
    proto.ai_adapter._REAL_GENERATE_JSON = fake_ai
    proto.ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)
    r = c.post("/posizioni/nuova", data={"csrf_token": t, "title": "Server 2", "role_code": "SERVER", "location": "Mount Dora",
                                         "timezone": "America/New_York", "manager_account_id": "1",
                                         "description": "Due server"}, follow_redirects=True)
    check("AI position draft shown for approval", "Proposta AI" in text(r) and "Paga?" in text(r))
    c.post(f"/posizioni/{pid}/stato", data={"csrf_token": t, "action": "reopen"})
    c.post(f"/posizioni/{pid}/rianalizza", data={"csrf_token": t})
    cand = text(c.get(f"/posizioni/{pid}/candidati/{pc_jordan}"))
    check("AI evaluation quotes an answer, invented quote dropped",
          "Yes, every weekend." in cand and "risposta" in cand and "Invented sentence" not in cand)
finally:
    proto._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
