#!/usr/bin/env python
"""SELECTION_POSITION_PROFILES_001 — position-specific CV screening, recruiter
priority and the AI interview invitation, on a throwaway SQLite database.
ALL DATA IS SYNTHETIC. The AI is a FAKE transport (no network) and no email
leaves the process: invitations stop in the outbox table.

Path: Server position with the profile -> two résumés screened and ranked
(stability computed from dates, quotes verified, commute in the order) ->
priority overrides the order -> AI Interview Requested queues exactly one
email (a second click sends nothing) -> the candidate's link runs the
interview -> AI Interview Completed with the transcript on the candidate page.
Also: the stability rules, a quote not in the CV is discarded, a role without
a profile keeps the existing screening only.

    python test_position_profiles_http.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from datetime import date
from io import BytesIO

TMP = tempfile.mkdtemp(prefix="selection_profiles_test_")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ["RFONE_SELECTION_UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["RFONE_SELECTION_REQUIRE_RFONE_LOGIN"] = "1"
os.environ["RFONE_WEB_BASE_URL"] = "https://rfone.example.test"
os.environ["RFONE_FLASK_SECRET_KEY"] = "selection-profiles-test-secret"
for name in ("RFONE_PUBLIC_BASE_URL", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_EMAIL_FROM_ADDRESS",
             "RFONE_SMTP_HOST", "RFONE_SMTP_USERNAME", "RFONE_SMTP_PASSWORD",
             "RFONE_SELECTION_AI", "RFONE_SELECTION_AI_CV"):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from sqlalchemy import select  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable  # noqa: E402
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client  # noqa: E402
from workspace import ai_adapter, ai_interview, mail_delivery, position_profiles, profile_screening  # noqa: E402

CV_LOCAL = """Jordan Example
jordan@example.test  (407) 555-0101
Lives in Eustis, FL

EXPERIENCE
Server, Trattoria Esempio, Mount Dora, FL | Mar 2021 - Present
- Table service for 40 covers, recommended wine pairings and trained new servers
Food Runner, Bistro Prova, Orlando, FL | Jan 2019 - Feb 2021
- Ran food to tables
"""
CV_FAR = """Casey Sample
casey@example.test
Based in Tampa, FL

EXPERIENCE
Server, Diner Demo, Tampa, FL | Jun 2024 - Sep 2024
Server, Cafe Demo, Tampa, FL | Jan 2024 - Apr 2024
Cashier, Store Demo, Tampa, FL | Jun 2023 - Nov 2023
"""

failures: list[str] = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok or not detail else f"  [{detail}]"))
    if not ok:
        failures.append(label)


def text(r) -> str:
    return r.get_data(as_text=True)


def token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1)


def fake_screening(prompt: str) -> dict:
    if "Jordan" in prompt or "Trattoria Esempio" in prompt:
        return {"timeline": [
            {"employer": "Trattoria Esempio", "title": "Server", "start": "2021-03", "end": "present",
             "environment": "Italian full-service, upscale casual, fine dining", "relevant": True, "promotion": False},
            {"employer": "Bistro Prova", "title": "Food Runner", "start": "2019-01", "end": "2021-02",
             "environment": "Traditional full-service", "relevant": True, "promotion": False}],
            "dimensions": {"table_service": {"level": 4, "quotes": ["Table service for 40 covers"], "explanation": "x"},
                           "guest_selling": {"level": 3, "quotes": ["recommended wine pairings"], "explanation": "x"},
                           "trusted": {"level": 2, "quotes": ["trained new servers"], "explanation": "x"},
                           "learning": {"level": 2, "quotes": ["a sentence that is not in the CV"], "explanation": "x"},
                           "versatility": {"level": 2, "quotes": ["Food Runner"], "explanation": "x"},
                           "recency": {"level": 4, "quotes": ["Mar 2021 - Present"], "explanation": "x"}},
            "positive_evidence": [{"text": "Trains new servers", "quote": "trained new servers"}],
            "risk_flags": [], "unknowns": ["Desired weekly hours"],
            "home_location": {"place": "Eustis, FL", "quote": "Lives in Eustis, FL"}, "commute_minutes": 15,
            "stated_hours": None, "stated_availability": None,
            "adaptability": {"status": "NOT_ESTABLISHED", "quote": ""}, "questions": ["What hours are you looking for?"]}
    return {"timeline": [
        {"employer": "Diner Demo", "title": "Server", "start": "2024-06", "end": "2024-09",
         "environment": "Diner, breakfast chain", "relevant": True},
        {"employer": "Cafe Demo", "title": "Server", "start": "2024-01", "end": "2024-04",
         "environment": "Diner, breakfast chain", "relevant": True},
        {"employer": "Store Demo", "title": "Cashier", "start": "2023-06", "end": "2023-11",
         "environment": "Retail, general customer service", "relevant": False}],
        "dimensions": {"table_service": {"level": 2, "quotes": ["Server, Diner Demo"], "explanation": "x"}},
        "positive_evidence": [], "risk_flags": [{"flag": "Mostly diner service", "fact": "Diner roles only",
                                                 "quote": "Server, Diner Demo", "question": "Tell me about full-service work."}],
        "unknowns": [], "home_location": {"place": "Tampa, FL", "quote": "Based in Tampa, FL"}, "commute_minutes": 100,
        "adaptability": {"status": "NOT_ESTABLISHED"}, "questions": []}


interview_prompts: list[str] = []


def fake_ai(prompt: str) -> dict:
    if "You read ONE job applicant's résumé" in prompt:
        return fake_screening(prompt)
    if "You are the interviewer for Rome's Flavours" in prompt:
        interview_prompts.append(prompt)
        if "CLOSE NOW" in prompt:
            return {"reply": "Thank you, the hiring team will be in touch.",
                    "findings": [{"step_id": "cv2", "status": "CLEAR", "quote": "about 30 hours", "note": "ok"}]}
        if "Candidate: That is all of it." in prompt:
            ids = re.findall(r"^- (\w+): ", prompt.split("Steps to cover")[1].split("Already covered")[0], re.M)
            return {"reply": "And what else?", "findings": [{"step_id": i, "status": "CLEAR", "quote": "That is all of it",
                                                               "note": "ok"} for i in ids]}
        if "Conversation so far:\n(not started)" in prompt:
            return {"reply": "Hi Jordan! Which evenings and weekends can you work?", "findings": []}
        return {"reply": "Thanks. How long would your drive be?",
                "findings": [{"step_id": "availability", "status": "CLEAR", "quote": "every weekend", "note": "ok"},
                             {"step_id": "commute", "status": "CLEAR", "quote": "words I never said", "note": "bad"}]}
    raise AIProviderUnavailable("fake: not used")


try:
    # --- Unit: stability rules from dates -------------------------------------
    today = date(2026, 10, 31)
    s = profile_screening.stability([{"start": "2026-01", "end": "2026-03"}, {"start": "2026-04", "end": "2026-06"},
                                     {"start": "2026-07", "end": "present"}], today)
    check("stability: three consecutive jobs under 6 months is a high-priority flag",
          any(f["code"] == "THREE_SHORT" and f["severity"] == "high" for f in s["flags"]) and s["level"] == 1, s)
    s = profile_screening.stability([{"start": "2020-01", "end": "present", "relevant": True}], today)
    check("stability: 3+ years at one relevant employer is positive evidence and the top level",
          s["level"] == 4 and s["positives"][0]["code"] == "LONG_TENURE", s)
    s = profile_screening.stability([{"start": None, "end": None}], today)
    check("stability: no usable dates means unknown, not zero", s["level"] is None and not s["known"])
    s = profile_screening.stability([{"start": "2022-04", "end": "present"}, {"start": "2021-01", "end": "2022-03"},
                                     {"start": None, "end": None}], today)
    check("stability: only the jobs really missing dates are counted as undated",
          s["jobs_dated"] == 2 and s["jobs_undated"] == 1, s)
    check("commute: a listed town uses the restaurant's drive table, not the AI's guess",
          position_profiles.known_drive("Mount Dora", "Leesburg, FL") == 25
          and position_profiles.known_drive("Mount Dora", "Atlantis") is None
          and position_profiles.known_drive(None, "Leesburg") is None)
    prompts, real_transport = [], profile_screening.ai_adapter._transport

    def broken_once(prompt, purpose):
        prompts.append(prompt)
        if len(prompts) == 1:
            raise profile_screening.AIProviderUnavailable("AWS Bedrock returned an unparsable response: x")
        return fake_screening(prompt)
    profile_screening.ai_adapter._transport = broken_once
    try:
        retried = profile_screening.screen(position_profiles.SERVER, location="Mount Dora",
                                           cv_text="Server, Olive Grove, 2019 - present")
    finally:
        profile_screening.ai_adapter._transport = real_transport
    check("screening: a reply that is not valid JSON is asked once more, with a note",
          len(prompts) == 2 and "not valid JSON" in prompts[1] and retried["fit"], len(prompts))
    check("privacy: the screening's never-use list differs from the existing one only by where the person lives",
          profile_screening.PROTECTED_EXCEPT_RESIDENCE != ai_adapter._PROTECTED
          and "address" not in profile_screening.PROTECTED_EXCEPT_RESIDENCE)
    odd = profile_screening.assemble(position_profiles.SERVER, {
        "timeline": "not a list", "dimensions": {"table_service": {"level": 3, "quotes": 5}},
        "stated_hours": {"hours": -3, "quote": "Server"}, "home_location": {"place": 7, "quote": "Server"},
        "commute_minutes": 10, "questions": "abc", "unknowns": None, "risk_flags": "x"}, cv_text="Server", location="Mount Dora")
    check("screening: an odd AI reply is handled, never a crash",
          odd["questions"] == [] and odd["stated_hours"] is None and odd["score"] == 0)
    check("profiles: Server and Line Cook weights add up to 100",
          all(sum(d["weight"] for d in p["dimensions"]) == 100 for p in position_profiles.PROFILES.values()))
    check("profiles: commute bands follow the 45-minute rule",
          position_profiles.commute_band(15)[0] == "FAVORABLE" and position_profiles.commute_band(44)[0] == "CONFIRM"
          and position_profiles.commute_band(45)[0] == "CUTOFF" and position_profiles.commute_band(None) is None)

    with isolated_ai_client():
        app = selection_app.app
        with selection_app.SessionFactory() as db:
            acc = account_svc.create_account(db, username="owner", display_name="Synthetic Owner",
                                             password="synthetic-password-1", is_admin=True)
            account_svc.set_domain_access(db, account_id=acc.id, domain_code="SELECTION", enabled=True, role_code=None)
            db.commit()
            owner_id = (acc.id, acc.session_version)
        owner = app.test_client()
        with owner.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = owner_id
        t = token(text(owner.get("/selection/")))

        ai_adapter._REAL_GENERATE_JSON = fake_ai
        ai_adapter.install_guard(ai_enabled=True, cv_ai_authorized=True)

        def open_position(role, title):
            r = owner.post("/selection/posizioni/nuova", data={
                "csrf_token": t, "title": title, "role_code": role, "location": "Mount Dora",
                "timezone": "America/New_York", "headcount": "1", "manager_account_id": str(owner_id[0]),
                "description": "Synthetic position."}, follow_redirects=True)
            pid = int(re.search(r"/selection/posizioni/(\d+)/requisiti/aggiungi", text(r)).group(1))
            owner.post(f"/selection/posizioni/{pid}/requisiti/aggiungi", data={
                "csrf_token": t, "name": "Restaurant experience", "description": "server restaurant",
                "criticality": "MUST_HAVE", "category": "Experience", "trainability": "PARTIALLY_TRAINABLE"})
            owner.post(f"/selection/posizioni/{pid}/dettagli", data={
                "csrf_token": t, "headcount": "1", "job_ad_en": "Synthetic ad.", "questions": "When could you start?"})
            owner.post(f"/selection/posizioni/{pid}/approva", data={"csrf_token": t})
            owner.post(f"/selection/posizioni/{pid}/configuration", data={"csrf_token": t, "cv_evaluation": "1"})
            return pid

        pid = open_position("SERVER", "Server")
        for name, cv in (("jordan.txt", CV_LOCAL), ("casey.txt", CV_FAR)):
            owner.post(f"/selection/posizioni/{pid}/cv", data={"csrf_token": t, "cv": (BytesIO(cv.encode()), name)},
                       content_type="multipart/form-data")

        with selection_app.SessionFactory() as db:
            pcs = {}
            for pc in db.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.position_id == pid)).all():
                prop = db.scalars(select(ws.Proposal).where(ws.Proposal.position_candidate_id == pc.id,
                                                            ws.Proposal.source == "PROFILE")).first()
                pcs["jordan" if "Jordan" in (pc.declared_name or "") or (prop and "Eustis" in prop.payload_json) else "casey"] = (pc.id, prop)
        jordan_id, jordan = pcs["jordan"]
        casey_id, casey = pcs["casey"]
        check("screening: each résumé gets a Server profile result stored with its version",
              jordan is not None and casey is not None and jordan.payload["version"] == "SERVER v1.0")
        jp, cp = jordan.payload, casey.payload
        check("screening: a quote not found in the résumé is discarded and its level becomes not shown",
              next(d for d in jp["dimensions"] if d["id"] == "learning")["level"] == 0 and jp["dropped_quotes"] == 1)
        check("screening: stability is computed from the dates, not by the AI",
              cp["stability"]["level"] == 1 and any(f.get("severity") == "flag" for f in cp["risk_flags"]))
        check("screening: a local candidate gets commute points; an estimated 45+ minutes is a point to confirm, not a verdict",
              jp["commute"]["band"] == "FAVORABLE" and jp["ranking_score"] == jp["score"] + 5
              and cp["fit"] != "CUTOFF" and cp["cutoffs"] and "not verified" in cp["cutoffs"][0]["status"]
              and cp["ranking_score"] == cp["score"] - 15)
        check("screening: unknown hours are listed as unknown, never scored",
              "Desired weekly hours." in jp["unknowns"] and jp["stated_hours"] is None)

        page = text(owner.get(f"/selection/posizioni/{pid}?tab=valutazione"))
        check("ranking: the evaluation tab shows the ranked list with Jordan before Casey",
              "CV ranking · Server profile" in page and page.index(f'id="cand-{jordan_id}"') < page.index(f'id="cand-{casey_id}"'))
        owner.post(f"/selection/posizioni/{pid}/candidati/{casey_id}/priorita", data={"csrf_token": t, "priority": "HIGH"})
        page = text(owner.get(f"/selection/posizioni/{pid}?tab=valutazione"))
        check("ranking: the recruiter's High priority overrides the proposed order",
              page.index(f'id="cand-{casey_id}"') < page.index(f'id="cand-{jordan_id}"'))
        check("ranking: an unknown priority value is refused",
              owner.post(f"/selection/posizioni/{pid}/candidati/{casey_id}/priorita",
                         data={"csrf_token": t, "priority": "URGENT"}).status_code == 400)

        cand_page = text(owner.get(f"/selection/posizioni/{pid}/candidati/{jordan_id}"))
        check("candidate page: From the CV shows flags, evidence, commute, unknowns and the questions",
              "From the CV · Server" in cand_page and "Lives in Eustis, FL" in cand_page and "Unknown (missing information" in cand_page)

        url = f"/selection/posizioni/{pid}/candidati/{jordan_id}/ai-interview"
        check("AI interview: without confirmation nothing is created",
              owner.post(url, data={"csrf_token": t}).status_code == 302)
        with selection_app.SessionFactory() as db:
            check("AI interview: still nothing after an unconfirmed request", ai_interview.for_pc(db, jordan_id) is None)
        owner.post(url, data={"csrf_token": t, "confirmed": "1"})
        owner.post(url, data={"csrf_token": t, "confirmed": "1"})
        with selection_app.SessionFactory() as db:
            iv = ai_interview.for_pc(db, jordan_id)
            rows = mail_delivery.rows_for(db, jordan_id)
            check("AI interview: one confirmed request queues exactly one email, a second click sends nothing",
                  iv is not None and len(rows) == 1 and rows[0].source_key == f"ai-interview:{iv.id}"
                  and rows[0].status == "QUEUED" and rows[0].recipient == "jordan@example.test")
            link = f"/selection/ai-interview/{iv.token}"
            check("AI interview: the email carries the personal link",
                  link in rows[0].body, rows[0].body)
            check("AI interview: steps come from the screening (availability, then résumé questions, then the role)",
                  [s["id"] for s in iv.steps][:2] == ["availability", "cv1"] and any(s["id"].startswith("role") for s in iv.steps),
                  [s["id"] for s in iv.steps])

        cand = app.test_client()
        before = len(interview_prompts)
        page = text(cand.get(link))
        with selection_app.SessionFactory() as db:
            check("AI interview: opening the link (or a mail scanner) calls no AI and starts nothing",
                  len(interview_prompts) == before and "Start the interview" in page
                  and ai_interview.for_pc(db, jordan_id).status == ai_interview.REQUESTED)
        ct = token(page)
        page = text(cand.post(link, data={"csrf_token": ct, "action": "start"}, follow_redirects=True))
        check("AI interview: Start opens the interview with the first question",
              "Which evenings and weekends can you work?" in page and "would rather talk to a person" in page)
        cand.post(link, data={"csrf_token": ct, "message": "I can work every weekend."})
        with selection_app.SessionFactory() as db:
            iv = ai_interview.for_pc(db, jordan_id)
            check("AI interview: only the candidate's own words are kept as quotes",
                  iv.findings.get("availability", {}).get("quote") == "every weekend" and "commute" not in iv.findings
                  and iv.status == ai_interview.IN_PROGRESS)
        cand.post(link, data={"csrf_token": ct, "message": "That is all of it."})
        with selection_app.SessionFactory() as db:
            iv = ai_interview.for_pc(db, jordan_id)
            check("AI interview: it closes on the answer that covers the last step and records AI Interview Completed",
                  iv.status == ai_interview.COMPLETED and iv.completed_at is not None
                  and iv.transcript[-1]["text"] == ai_interview.CLOSING_REPLY, iv.status)
        check("AI interview: the finished link shows the thank-you page only", "Thank you" in text(cand.get(link)))
        cand_page = text(owner.get(f"/selection/posizioni/{pid}/candidati/{jordan_id}"))
        list_page = text(owner.get(f"/selection/posizioni/{pid}?tab=valutazione"))
        check("AI interview: status and full transcript on the candidate page, status in the list",
              "AI Interview Completed" in cand_page and "I can work every weekend." in cand_page
              and "AI Interview Completed" in list_page)
        check("AI interview: a wrong link is not found", cand.get("/selection/ai-interview/not-a-token").status_code == 404)
        owner.post(f"/selection/posizioni/{pid}/candidati/{casey_id}/ai-interview", data={"csrf_token": t, "confirmed": "1"})
        with selection_app.SessionFactory() as db:
            casey_link = f"/selection/ai-interview/{ai_interview.for_pc(db, casey_id).token}"
            db.get(ws.Position, pid).status = ws.CLOSED
            db.commit()
        check("AI interview: once the position is closed the link is no longer open",
              "no longer open" in text(cand.get(casey_link)))

        other = open_position("BARTENDER", "Bartender")
        owner.post(f"/selection/posizioni/{other}/cv", data={"csrf_token": t, "cv": (BytesIO(CV_LOCAL.encode()), "j2.txt")},
                   content_type="multipart/form-data")
        with selection_app.SessionFactory() as db:
            other_pc = db.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.position_id == other)).first()
        owner.post(f"/selection/posizioni/{other}/candidati/{other_pc.id}/ai-interview", data={"csrf_token": t, "confirmed": "1"})
        with selection_app.SessionFactory() as db:
            check("AI interview: refused for a role without a profile, no email",
                  ai_interview.for_pc(db, other_pc.id) is None and not mail_delivery.rows_for(db, other_pc.id))
            check("a role without a profile keeps the existing screening only",
                  not db.scalars(select(ws.Proposal).join(ws.PositionCandidate,
                      ws.PositionCandidate.id == ws.Proposal.position_candidate_id).where(
                      ws.PositionCandidate.position_id == other, ws.Proposal.source == "PROFILE")).first())
finally:
    selection_app._engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'ALL PASSED' if not failures else str(len(failures)) + ' FAILED'}")
sys.exit(1 if failures else 0)
