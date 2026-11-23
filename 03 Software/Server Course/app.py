"""RF-One Server Trainer (test): Selection and Training on one engine.

One engine, two directions (Pino, 29 October 2026): in Selection the AI takes
information in; in Training it gives information back.

Selection follows Pino's flow (30 October): CVs come in from Indeed or a
direct application; the AI reads each one against his six screening criteria
and puts them in order; the selector calls the first ones and sends each a
link; before the in-person interview the candidate talks with the engine,
which checks availability, reliability (what the CV raises) and skills. The
hiring team reads the answers and decides. Candidates are kept in S3 (or a
local folder on a PC); training progress stays in the trainee's browser.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for

import pdfs
import rf_training
import store
from content import course
from content.guides import EXTRA_TITLES
from content.modules import MODULE_BY_ID, MODULES, PILLS
from content.tests import PASS_ALL, PASS_MARK, TESTS
from content.screening import CRITERIA, chance, hard_stop, total
from prompts import (SCREEN_SYSTEM, selection_checks, selection_closing, selection_next, selection_system,
                     training_system)

BASE = Path(__file__).resolve().parent
MODEL_ID = os.environ.get("RFONE_TRAINER_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")
ACCESS_CODE = os.environ.get("RFONE_TRAINER_ACCESS_CODE", "")
# Training time: a gap with no activity longer than this counts only up to it
# (Pino's rule: 120 seconds normally, configurable to 60).
IDLE_SECONDS = 60 if os.environ.get("RFONE_TRAINER_IDLE_SECONDS") == "60" else 120
# The certificate is off for now (4 November 2026); the code stays for later.
CERTIFICATE = os.environ.get("RFONE_TRAINER_CERTIFICATE") == "1"
MAX_TURNS = 80
START = "[0 min]\n(The person has just opened the session. Begin.)"
CV_FORMATS = {".pdf": "pdf", ".docx": "docx", ".doc": "doc", ".txt": "txt", ".md": "md", ".html": "html"}
STAGES = ["New", "Called", "Interview link sent", "Interviewed", "In-person interview", "Practical test",
          "Hired", "Not moving on"]
PUBLIC = ("login", "health", "static", "interview_page", "interview_turn", "interview_finish", "trainee_link", "hire_link",
          "training_link_details", "rf_entry", "rfone_status")
# What a new hire's link opens: the training and nothing of the hiring side.
TRAINEE = ("training", "guide_pdf", "extra_pdf", "certificate_pdf", "api_modules", "api_turn", "api_track",
           "api_progress", "api_progress_put", "api_test_get", "api_test_post", "training_account")

app = Flask(__name__)
app.secret_key = os.environ.get("RFONE_TRAINER_SECRET_KEY") or secrets.token_urlsafe(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=5 * 1024 * 1024,
                  SESSION_COOKIE_SECURE=os.environ.get("RFONE_TRAINER_HTTPS", "1") == "1")

# The new hire's link. It comes from the secret key, so it stays the same
# across deploys and changes only if the key does.
TRAINEE_TOKEN = hmac.new(app.secret_key.encode(), b"trainee-link-v1", hashlib.sha256).hexdigest()[:24]

_bedrock = boto3.client("bedrock-runtime", region_name=REGION,
                        config=Config(read_timeout=90, retries={"max_attempts": 4, "mode": "adaptive"}))
# Second AI route for training chats: when the first route is at its limit, go
# straight to the second instead of waiting. CVs and interviews stay on the first.
SECOND_MODEL_ID = os.environ.get("RFONE_TRAINER_MODEL_ID_2",
                                 "global." + MODEL_ID[3:] if MODEL_ID.startswith("us.anthropic.") else "")
_bedrock_once = boto3.client("bedrock-runtime", region_name=REGION,
                             config=Config(read_timeout=90, retries={"total_max_attempts": 1, "mode": "standard"}))
_AI_BUSY = ("ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- training activity ----------
# Who opened the training and how far they got, so the team can see it.
# No names: an anonymous id per browser, the kind of device and the dates.

def _device() -> str:
    ua = request.headers.get("User-Agent", "")
    kind = next((k for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                                ("Macintosh", "Mac")) if k in ua), "Other")
    browser = next((n for k, n in (("Edg/", "Edge"), ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Firefox", "Firefox"),
                                   ("Safari", "Safari")) if k in ua), "")
    return f"{kind}, {browser}" if browser else kind


def _blank_activity(hid: str, rec: dict) -> dict:
    return {"id": hid, "source": "Own link", "device": "", "first": rec.get("created"),
            "courses": {}, "guides": 0, "certificate": None}


def _track(update) -> None:
    """Record training activity. Never lets a tracking problem stop the training."""
    try:
        hid = session.get("hire")
        if hid:
            def change(rec):
                act = rec.setdefault("activity", _blank_activity(hid, rec))
                act["last"], act["device"] = _now(), _device()
                update(act)
            store.update_hire(hid, change)
            return
        if not session.get("vid"):
            session["vid"] = secrets.token_hex(4)
        source = "Team login" if session.get("ok") else "New hire link"
        store.track(session["vid"], source, _device(), _now(), update)
    except Exception as exc:  # noqa: BLE001
        app.logger.warning("training activity not saved: %s", exc)


def _course(rec: dict, unit_id: str) -> dict:
    u = course.UNIT_BY_ID[unit_id]
    c = rec["courses"].setdefault(unit_id, {"n": u["number"], "title": u["title"], "modules_done": 0,
                                            "modules": len(u["pills"]), "test": None})
    c.update(n=u["number"], code=u["id"], title=u["title"], modules=len(u["pills"]))
    return c


# ---------- access ----------

@app.before_request
def _require_access():
    if request.endpoint in PUBLIC or not ACCESS_CODE:
        return None
    if session.get("ok"):
        return None
    if session.get("trainee"):
        if request.endpoint in TRAINEE:
            return None
        if request.path.startswith("/api/"):
            return jsonify(error="Not available."), 403
        return redirect(url_for("training"))
    if request.path.startswith("/api/"):
        return jsonify(error="Please sign in again."), 401
    return redirect(url_for("login"))


@app.route("/t/<token>")
def trainee_link(token):
    """The shared link (no name): it signs them in to the training only."""
    if not hmac.compare_digest(token, TRAINEE_TOKEN):
        abort(404)
    session.pop("hire", None)
    if not session.get("ok"):
        session["trainee"] = True
        session.permanent = True
    return redirect(url_for("training"))


@app.route("/h/<hid>")
def hire_link(hid):
    """A named new hire's own link: it opens their training, with their progress."""
    if not store.get_hire(hid):
        abort(404)
    if not session.get("ok"):
        session["trainee"] = True
        session.permanent = True
    session["hire"] = hid
    return redirect(url_for("training"))


# ---------- RF-One Training (rf_training.py) ----------

@app.route("/training-account", methods=["POST"])
def training_account():
    """A named hire asks for their RF-One Training account with their own email."""
    hid = session.get("hire")
    if not hid or not store.get_hire(hid):
        abort(404)
    ok, message = rf_training.request_invite(hid, request.form.get("email", ""))
    session["rt_msg"] = {"ok": ok, "text": message}
    return redirect(url_for("training") + "#rf-training")


@app.route("/api/training-link/<code>")
def training_link_details(code):
    """Training's call back for an invitation this course asked for."""
    details = rf_training.invite_details(code)
    if not details:
        return jsonify(error="Not found."), 404
    return jsonify(details)


@app.route("/rf")
def rf_entry():
    """Opened from RF-One Training: the signed-in person's own course, with their progress."""
    account = rf_training.verify(request.args.get("code", ""))
    if not account:
        return redirect(rf_training.TRAINING_URL + "/training")
    hid = rf_training.hire_for(account)
    session.pop("ok", None)
    session["trainee"] = True
    session.permanent = True
    session["hire"] = hid
    return redirect(url_for("training"))


@app.route("/api/rfone-status", methods=["POST"])
def rfone_status():
    """Training's Students page: where each of its trainees stands, for Confirm hire."""
    ids = rf_training.status_request(str((request.get_json(silent=True) or {}).get("code") or ""))
    if ids is None:
        return jsonify(error="Not allowed."), 403
    out = {}
    for acc, h in rf_training.hires_by_account(ids).items():
        s = _hire_summary(h)
        ready = s.get("ready") or {}
        out[str(acc)] = {"units_complete": s["units_complete"], "units_total": len(course.UNITS),
                         "checks_done": s["checks_done"], "checks_total": s["checks_total"],
                         "complete": _can_be_ready(s), "signed": bool(ready.get("value")) and _can_be_ready(s),
                         "signed_by": ready.get("by", "") if ready.get("value") else "",
                         "signed_date": ready.get("date", "") if ready.get("value") else ""}
    return jsonify(trainees=out)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if ACCESS_CODE and hmac.compare_digest(code, ACCESS_CODE):
            session["ok"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "That code isn't right."
    return render_template("login.html", error=error)


@app.route("/health")
def health():
    return "ok"


def _hire_location() -> str:
    """Winter Park or Mount Dora for a named hire on their own link; empty otherwise."""
    h = store.get_hire(session.get("hire") or "") if session.get("hire") else None
    return (h or {}).get("location") or ""


def _courses_for_training() -> list[dict]:
    """The units of the course file, as the training page needs them: with
    the test and the guides to download."""
    out = []
    where = _hire_location()
    for u in course.UNITS:
        # The management course has no guide: it would show the reference reasoning before they've reasoned.
        guides = [] if course.KIND == "management" else [{"title": f"Unit {u['id']} guide", "href": f"guides/{u['id']}.pdf"}]
        # The menu guide follows the hire's location (Mount Dora hires get the Mount Dora menu).
        guides += [{"title": pdfs.extra_title(k, where), "href": f"guides/extra/{k}.pdf"} for k in u.get("extra") or []]
        unit = {k: v for k, v in u.items() if k != "test"}
        out.append(dict(unit, guides=guides, test_count=u["draw"]))
    return out


def _page(trainee: bool, **extra):
    hire = None
    if session.get("hire"):
        h = store.get_hire(session["hire"])
        if h:
            hire = {"id": h["id"], "name": h["name"], "location": h["location"], "tester": bool(h.get("tester")),
                    "rf": rf_training.status(h)}
    return render_template("index.html", modules=_courses_for_training(), course=course.COURSE,
                           levels=course.COURSE["levels"], selection=MODULES, idle_seconds=IDLE_SECONDS,
                           trainee=trainee, hire=hire, kind=course.KIND, session_minutes=course.SESSION_MINUTES,
                           rt_msg=session.pop("rt_msg", None) if trainee else None, training_url=rf_training.TRAINING_URL,
                           **extra)


@app.route("/")
def index():
    session.pop("hire", None)
    return _page(False, criteria=CRITERIA, stages=STAGES, trainee_link=url_for("trainee_link", token=TRAINEE_TOKEN))


@app.route("/training")
def training():
    """The Server Training on its own, for a new hire."""
    _track(lambda rec: rec.__setitem__("visits", rec.get("visits", 0) + 1))
    return _page(True, criteria=[], stages=[])


def _pdf(data: bytes, filename: str, download: bool = False) -> Response:
    kind = "attachment" if download else "inline"
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f'{kind}; filename="{filename}"', "Cache-Control": "private, max-age=300"})


@app.route("/guides/<course_id>.pdf")
def guide_pdf(course_id):
    if course_id not in course.UNIT_BY_ID or course.KIND == "management":
        abort(404)
    _track(lambda rec: rec.__setitem__("guides", rec.get("guides", 0) + 1))
    title = re.sub(r"[^\w ]", "", course.UNIT_BY_ID[course_id]["title"])
    return _pdf(pdfs.unit_guide(course_id), f"Rome's Flavours Server Course - Unit {course_id} - {title}.pdf")


@app.route("/guides/extra/<key>.pdf")
def extra_pdf(key):
    if key not in EXTRA_TITLES:
        abort(404)
    where = _hire_location()
    return _pdf(pdfs.extra_guide(key, where), f"Rome's Flavours - {pdfs.extra_title(key, where)}.pdf")


@app.route("/certificate.pdf", methods=["POST"])
def certificate_pdf():
    """The certificate of completion. Progress is kept in the trainee's
    browser, so the page checks every course is complete before asking.
    Off for now (CERTIFICATE)."""
    if not CERTIFICATE:
        abort(404)
    data = request.get_json(force=True) or {}
    name = re.sub(r"\s+", " ", str(data.get("name") or "")).strip()[:60]
    if not name:
        return jsonify(error="Add the name to print on the certificate."), 400
    try:
        done = datetime.fromisoformat(str(data.get("date") or "")[:10]).date()
    except ValueError:
        done = datetime.now(timezone.utc).date()
    location = data.get("location") if data.get("location") in ("Winter Park", "Mount Dora") else ""
    safe = re.sub(r"[^\w ]", "", name) or "Server"
    _track(lambda rec: rec.__setitem__("certificate", {"date": _now(), "location": location}))
    return _pdf(pdfs.certificate(name, done, location), f"Rome's Flavours Academy certificate - {safe}.pdf", download=True)


@app.route("/api/track", methods=["POST"])
def api_track():
    """A test result or a session's counted time, from the trainee's browser
    (the tests are marked there, and the time is counted there)."""
    data = request.get_json(force=True) or {}
    mid = data.get("module_id")
    if data.get("kind") != "time" or mid not in course.UNIT_BY_ID:
        return jsonify(ok=False), 400
    if data["kind"] == "time":
        try:
            counted = max(0, min(int(data.get("counted") or 0), 3 * 3600))
            breaks = max(0, min(int(data.get("breaks") or 0), 12 * 3600))
        except (TypeError, ValueError):
            return jsonify(ok=False), 400
        def add_time(rec):
            c = _course(rec, mid)
            c["seconds"] = c.get("seconds", 0) + counted
            rec["seconds"] = rec.get("seconds", 0) + counted
            rec["break_seconds"] = rec.get("break_seconds", 0) + breaks
            # The browser sends the time in pieces during a session; only the
            # last piece (final, or an older page that sends no flag) is a session.
            if data.get("final", True):
                rec["sessions"] = rec.get("sessions", 0) + 1
            rec["idle_rule"] = IDLE_SECONDS
        _track(add_time)
        if session.get("hire"):
            def change(h):
                t = _progress(h).setdefault("time", {})
                t[mid] = t.get(mid, 0) + counted
            store.update_hire(session["hire"], change)
        return jsonify(ok=True)
    return jsonify(ok=False), 400


# ---------- a named hire's progress, kept on the server ----------

def _progress(h: dict) -> dict:
    p = h.setdefault("progress", {})
    for k in ("understood", "tests", "time", "sessions", "last_note", "prefs", "locks"):
        p.setdefault(k, {})
    p.setdefault("referrals", [])
    return p


@app.route("/api/progress")
def api_progress():
    h = store.get_hire(session.get("hire") or "")
    if not h:
        return jsonify(hire=None)
    return jsonify(hire={"id": h["id"], "name": h["name"], "location": h["location"]}, progress=_progress(h))


@app.route("/api/progress", methods=["PUT"])
def api_progress_put():
    """What the page itself owns: where they left off, sessions started, preferences.
    Modules, tests and time are written only by the server."""
    hid = session.get("hire")
    if not hid:
        return jsonify(ok=True)
    data = request.get_json(force=True) or {}
    def change(h):
        p = _progress(h)
        for uid, note in (data.get("last_note") or {}).items():
            if uid in course.UNIT_BY_ID:
                p["last_note"][uid] = str(note)[:600]
        for uid, n in (data.get("sessions") or {}).items():
            if uid in course.UNIT_BY_ID:
                try:
                    p["sessions"][uid] = max(int(p["sessions"].get(uid, 0)), min(int(n or 0), 500))
                except (TypeError, ValueError):
                    pass
        if isinstance(data.get("prefs"), dict):
            p["prefs"] = {"readAloud": bool(data["prefs"].get("readAloud"))}
    store.update_hire(hid, change)
    return jsonify(ok=True)


# ---------- the unit test: drawn and marked on the server ----------
# A random draw from the unit's bank, options shuffled; the answers never
# reach the page. After two failed tries in a row, the next try opens after a
# session with the Trainer on that unit.

def _locks() -> dict:
    hid = session.get("hire")
    if hid:
        h = store.get_hire(hid)
        return _progress(h)["locks"] if h else {}
    return session.get("locks") or {}


def _set_lock(uid: str, value: dict) -> None:
    hid = session.get("hire")
    if hid:
        store.update_hire(hid, lambda h: _progress(h)["locks"].__setitem__(uid, value))
    else:
        locks = dict(session.get("locks") or {})
        locks[uid] = value
        session["locks"] = locks


@app.route("/api/test/<uid>")
def api_test_get(uid):
    u = course.UNIT_BY_ID.get(uid)
    if not u:
        return jsonify(error="Unknown unit."), 404
    hid = session.get("hire")
    if hid and not session.get("ok"):
        h = store.get_hire(hid)
        done = set(_progress(h)["understood"]) if h else set()
        if not all(p["id"] in done for p in u["pills"]):
            return jsonify(error="Finish the unit's modules with the Trainer first.", needs_trainer=True), 409
    lock = _locks().get(uid) or {}
    if lock.get("fails", 0) >= 2 and not lock.get("trained"):
        return jsonify(error="Two tries in a row didn't pass. Do a short session with the Trainer on this unit, then try again.",
                       needs_trainer=True), 409
    draw = random.sample(u["test"], u["draw"])
    session["test"] = {"unit": uid, "ids": [q["id"] for q in draw]}
    return jsonify(unit=uid, pass_mark=u["pass_mark"], total=len(draw), safety=bool(u.get("safety_critical")),
                   questions=[{"id": q["id"], "q": q["q"], "options": random.sample(q["options"], len(q["options"]))}
                              for q in draw])


@app.route("/api/test/<uid>", methods=["POST"])
def api_test_post(uid):
    u = course.UNIT_BY_ID.get(uid)
    drawn = session.get("test") or {}
    if not u or drawn.get("unit") != uid:
        return jsonify(error="This test has expired. Start it again."), 409
    session.pop("test", None)
    answers = (request.get_json(force=True) or {}).get("answers") or {}
    missed = []
    for qid in drawn["ids"]:
        q = course.QUESTIONS[qid]
        if answers.get(qid) != q["options"][0]:
            missed.append({"q": q["q"], "why": q["why"]})
    total = len(drawn["ids"])
    score = total - len(missed)
    passed = score >= u["pass_mark"]
    lock = _locks().get(uid) or {}
    fails = 0 if passed else lock.get("fails", 0) + 1
    _set_lock(uid, {"fails": fails, "trained": False})
    now = _now()

    def record(t):
        prev = t or {}
        was = bool(prev.get("passed"))
        return {"score": score, "total": total, "passed": passed or was, "tries": prev.get("tries", 0) + 1,
                "date": now, "best": max(score, prev.get("best", 0)),
                "missed": [m["q"] for m in missed] if not passed else ([] if not was else prev.get("missed", [])),
                "passed_on": prev.get("passed_on") or (now if passed else None)}
    def upd(rec):
        c = _course(rec, uid)
        c["test"] = record(c.get("test"))
    _track(upd)
    if session.get("hire"):
        def change(h):
            tests = _progress(h)["tests"]
            tests[uid] = record(tests.get(uid))
        store.update_hire(session["hire"], change)
    return jsonify(score=score, total=total, passed=passed, pass_mark=u["pass_mark"], missed=missed,
                   needs_trainer=fails >= 2)


# ---------- the team: named hires, practical checks, readiness ----------

PRACTICAL = ("demonstrated", "repeat", "not_observed")


def _hire_summary(h: dict) -> dict:
    p = _progress(h)
    units = []
    for u in course.UNITS:
        mods = sum(1 for x in u["pills"] if x["id"] in p["understood"])
        t = p["tests"].get(u["id"]) or {}
        checks = (h.get("practical") or {}).get(u["id"]) or {}
        units.append({"id": u["id"], "title": u["title"], "modules": len(u["pills"]), "modules_done": mods,
                      "test": t, "seconds": p["time"].get(u["id"], 0),
                      "practical": [dict(x, **(checks.get(x["title"]) or {"status": "not_observed"}))
                                    for x in u.get("practical") or []],
                      "complete": mods == len(u["pills"]) and (bool(t.get("passed")) or not u["test"])})
    checks = [c for u in units for c in u["practical"]]
    act = h.get("activity") or {}
    adj = sum(a.get("seconds", 0) for a in h.get("time_adjustments") or [])
    return {"id": h["id"], "name": h["name"], "location": h["location"], "created": h.get("created"),
            "link": url_for("hire_link", hid=h["id"]), "last": act.get("last"), "device": act.get("device"),
            "units": units, "units_complete": sum(1 for u in units if u["complete"]),
            "checks_total": len(checks), "checks_done": sum(1 for c in checks if c["status"] == "demonstrated"),
            "checks_repeat": sum(1 for c in checks if c["status"] == "repeat"),
            "seconds": sum(p["time"].values()) + adj, "time_adjustments": h.get("time_adjustments") or [],
            "referrals": p["referrals"], "ready": h.get("ready"), "archived": h.get("archived", False),
            "reasoning": p.get("reasoning") or [], "work_notes": p.get("work_notes") or [],
            "tester": bool(h.get("tester"))}


def _can_be_ready(s: dict) -> bool:
    return s["units_complete"] == len(course.UNITS) and s["checks_done"] == s["checks_total"]


@app.route("/api/hires")
def hires_list():
    out = []
    for hid, row in store.hires_index().items():
        h = store.get_hire(hid)
        if h:
            h["archived"] = row.get("archived", False)
            out.append(_hire_summary(h))
    out.sort(key=lambda x: x.get("created") or "", reverse=True)
    return jsonify(hires=out, units=len(course.UNITS))


@app.route("/api/hires", methods=["POST"])
def hires_add():
    data = request.get_json(force=True) or {}
    name = re.sub(r"\s+", " ", str(data.get("name") or "")).strip()[:60]
    location = data.get("location") if data.get("location") in ("Winter Park", "Mount Dora") else ""
    if not name or not location:
        return jsonify(error="Add a name and a location."), 400
    hid = secrets.token_hex(10)
    store.add_hire({"id": hid, "name": name, "location": location, "created": _now()})
    return jsonify(id=hid, link=url_for("hire_link", hid=hid))


@app.route("/api/hires/<hid>", methods=["PATCH"])
def hires_update(hid):
    data = request.get_json(force=True) or {}
    err = {}
    if "archived" in data:
        store.set_hire_archived(hid, bool(data["archived"]))
    def change(h):
        if "practical" in data:
            x = data["practical"] or {}
            uid, title, status = x.get("unit"), x.get("title"), x.get("status")
            u = course.UNIT_BY_ID.get(uid)
            if not u or title not in [c["title"] for c in u.get("practical") or []] or status not in PRACTICAL:
                err["e"] = "Unknown check."
                return
            note = str(x.get("note") or "")[:300]
            if status == "repeat" and not note:
                err["e"] = "Name the error to repeat, in the note."
                return
            h.setdefault("practical", {}).setdefault(uid, {})[title] = {
                "status": status, "note": note, "by": str(x.get("by") or "")[:40], "date": _now()}
            if status != "demonstrated" and (h.get("ready") or {}).get("value"):
                h["ready"] = {"value": False, "by": "", "date": _now(), "note": "Cleared: a practical check changed."}
        if "tester" in data:
            # A team member testing the course: every unit is open, in any order.
            h["tester"] = bool(data["tester"])
        if "time_adjust" in data:
            x = data["time_adjust"] or {}
            try:
                minutes = int(x.get("minutes"))
            except (TypeError, ValueError):
                err["e"] = "Minutes must be a number."
                return
            reason = str(x.get("reason") or "").strip()[:200]
            if not reason or not -600 <= minutes <= 600 or minutes == 0:
                err["e"] = "Add the minutes (plus or minus) and a reason."
                return
            h.setdefault("time_adjustments", []).append({"seconds": minutes * 60, "reason": reason,
                                                         "by": str(x.get("by") or "")[:40], "date": _now()})
        if "ready" in data:
            x = data["ready"] or {}
            if x.get("value") and not _can_be_ready(_hire_summary(h)):
                err["e"] = "Every unit and every practical check must be complete first."
                return
            if x.get("value") and not str(x.get("by") or "").strip():
                err["e"] = "Say who signs it (the role, for example 'Lead on shift')."
                return
            h["ready"] = {"value": bool(x.get("value")), "by": str(x.get("by") or "")[:40], "date": _now(),
                          "note": str(x.get("note") or "")[:300]}
    rec = store.update_hire(hid, change)
    if rec is None:
        return jsonify(error="Not found."), 404
    if err:
        return jsonify(error=err["e"]), 400
    rec["archived"] = store.hires_index().get(hid, {}).get("archived", False)
    return jsonify(hire=_hire_summary(rec))


@app.route("/api/training-activity")
def training_activity():
    """For the team: every browser that has used the training, latest first."""
    rows = sorted(store.activity().values(), key=lambda r: r.get("last") or "", reverse=True)
    return jsonify(activity=rows)


@app.route("/api/modules")
def api_modules():
    return jsonify(modules=MODULES)


# ---------- candidates (hiring team) ----------

def _screen_tool():
    crit = {c["id"]: {"type": "object", "properties": {
        "level": {"type": "integer", "minimum": 0, "maximum": 4},
        "evidence": {"type": "string", "description": "The CV fact this level rests on, in a few words."}},
        "required": ["level", "evidence"]} for c in CRITERIA}
    return {"toolSpec": {"name": "screen_cv", "description": "The screening of this CV.", "inputSchema": {"json": {
        "type": "object",
        "properties": {
            "name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"},
            "cv_summary": {"type": "string", "description": "Work history as short lines: role, employer, city, from-to dates. Then education or certificates in one line, if relevant (food handler, alcohol server)."},
            "criteria": {"type": "object", "properties": crit, "required": [c["id"] for c in CRITERIA]},
            "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 3, "description": "Up to three facts from the CV that make this person more likely to succeed as a server here."},
            "red_flags": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
                "flag": {"type": "string", "description": "What the CV shows, with the job or dates."},
                "question": {"type": "string", "description": "One neutral question to ask about it."}},
                "required": ["flag", "question"]}},
            "fit_note": {"type": "string", "description": "One neutral sentence on how this CV fits the role."},
        },
        "required": ["name", "cv_summary", "criteria", "strengths", "red_flags", "fit_note"]}}}}


def _known(v) -> str:
    v = (v or "").strip()
    return "" if not v or "unknown" in v.lower() or v.startswith("<") or v.lower() in ("n/a", "none") else v


def _screen(data: bytes, fmt: str, filename: str) -> dict:
    doc = {"document": {"format": fmt, "name": "CV", "source": {"bytes": data}}}
    resp = _bedrock.converse(
        modelId=MODEL_ID, system=[{"text": SCREEN_SYSTEM}],
        messages=[{"role": "user", "content": [doc, {"text": f"The CV file is '{filename}'. Screen it."}]}],
        inferenceConfig={"maxTokens": 1500, "temperature": 0},
        toolConfig={"tools": [_screen_tool()], "toolChoice": {"tool": {"name": "screen_cv"}}})
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"].get("input") or {}
    raise ValueError("The AI didn't return a screening.")


@app.route("/api/candidates")
def candidates_list():
    rows = sorted(store.index().values(),
                  key=lambda r: (r.get("stage") == "Not moving on", bool(r.get("hard_stop")), -(r.get("total") or 0)))
    return jsonify(candidates=rows)


@app.route("/api/candidates", methods=["POST"])
def candidates_add():
    f = request.files.get("cv")
    if not f or not f.filename:
        return jsonify(error="Choose a CV file."), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in CV_FORMATS:
        return jsonify(error=f"{f.filename}: use PDF, Word or text."), 400
    data = f.read()
    try:
        s = _screen(data, CV_FORMATS[ext], f.filename)
    except Exception as exc:  # noqa: BLE001 - shown to the selector, who can retry
        return jsonify(error=f"{f.filename}: the AI couldn't read it ({exc.__class__.__name__})."), 502
    levels = {c["id"]: int(((s.get("criteria") or {}).get(c["id"]) or {}).get("level") or 0) for c in CRITERIA}
    cid = secrets.token_urlsafe(16)
    c = {
        "id": cid, "created": _now(), "file_name": f.filename,
        "source": request.form.get("source") or "Indeed", "location": request.form.get("location") or "Winter Park",
        "name": (s.get("name") or "").strip() or os.path.splitext(f.filename)[0],
        "email": _known(s.get("email")), "phone": _known(s.get("phone")), "stage": "New",
        "screen": {"criteria": s.get("criteria") or {}, "levels": levels, "total": total(levels),
                   "hard_stop": hard_stop(levels), "chance": chance(levels), "cv_summary": s.get("cv_summary") or "",
                   "strengths": s.get("strengths") or [], "red_flags": s.get("red_flags") or [],
                   "fit_note": s.get("fit_note") or ""},
        "interview": {}, "review": {},
    }
    store.put_cv(cid, data)
    store.save(c)
    return jsonify(candidate=c)


def _candidate_or_404(cid: str) -> dict:
    c = store.get(cid)
    if not c:
        abort(404)
    return c


@app.route("/api/candidates/<cid>")
def candidate_get(cid):
    c = _candidate_or_404(cid)
    c["checks_asked"] = selection_checks(c.get("screen"))
    return jsonify(candidate=c)


@app.route("/api/candidates/<cid>", methods=["PATCH"])
def candidate_update(cid):
    c = _candidate_or_404(cid)
    data = request.get_json(force=True) or {}
    if data.get("stage") in STAGES:
        c["stage"] = data["stage"]
    if isinstance(data.get("review"), dict):
        c["review"] = {k: v for k, v in data["review"].items() if k in PILLS and isinstance(v, dict)}
    if isinstance(data.get("order_note"), str):
        c["order_note"] = data["order_note"][:500]
    store.save(c)
    return jsonify(ok=True)


@app.route("/api/candidates/<cid>", methods=["DELETE"])
def candidate_delete(cid):
    _candidate_or_404(cid)
    store.delete(cid)
    return jsonify(ok=True)


@app.route("/candidates/<cid>/cv")
def candidate_cv(cid):
    c = _candidate_or_404(cid)
    data = store.get_cv(cid)
    if data is None:
        abort(404)
    safe = re.sub(r"[^\w.\- ]", "_", c.get("file_name") or "cv")
    return Response(data, mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


# ---------- the candidate's interview (public, by link) ----------

@app.route("/i/<cid>")
def interview_page(cid):
    c = store.get(cid)
    if not c or c.get("stage") == "Not moving on":
        return render_template("interview.html", candidate=None, modules=MODULES), 404
    first = (c.get("name") or "").split(" ")[0]
    return render_template("interview.html", modules=MODULES, candidate={
        "id": cid, "first_name": first, "location": c.get("location"),
        "finished": bool((c.get("interview") or {}).get("finished"))})


def _interview_progress(c: dict) -> dict:
    iv = c.setdefault("interview", {})
    started = iv.get("started")
    minutes = 0
    if started:
        minutes = int((datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds() // 60)
    return {"evidence": iv.get("evidence") or {}, "checks": iv.get("checks") or {}, "minutes": minutes}


RANK = {"NOT_EVIDENCED": 0, "PARTIAL": 1, "EVIDENCED": 2}
CHECK_RANK = {"OPEN": 0, "PARTLY": 1, "CLEAR": 2}


def _record(c: dict, events: list) -> None:
    """Keep what the interview gave: the answer per check and per module,
    and the note. Several records on one module: the lowest wins."""
    iv = c.setdefault("interview", {})
    check_ids = {x["id"] for x in selection_checks(c.get("screen"))}
    for e in events:
        i = e.get("input") or {}
        if e["tool"] == "record_evidence" and i.get("pill_id") in PILLS and i.get("status") in RANK and (i.get("quote") or "").strip():
            prev = (iv.setdefault("evidence", {})).get(i["pill_id"])
            if not prev or RANK[i["status"]] < RANK[prev["status"]]:
                iv["evidence"][i["pill_id"]] = {"status": i["status"], "quote": i["quote"].strip(), "missing": i.get("missing") or ""}
        elif e["tool"] == "record_check" and i.get("check_id") in check_ids and i.get("status") in CHECK_RANK:
            prev = (iv.setdefault("checks", {})).get(i["check_id"])
            if not prev or CHECK_RANK[i["status"]] < CHECK_RANK[prev["status"]]:
                iv["checks"][i["check_id"]] = {"status": i["status"], "quote": (i.get("quote") or "").strip(),
                                               "note": i.get("note") or ""}
        elif e["tool"] == "finish_interview":
            iv["note"] = i.get("note_for_hiring_team") or ""
            _finish(c)


def _finish(c: dict) -> None:
    iv = c.setdefault("interview", {})
    if not iv.get("finished"):
        iv["finished"] = _now()
        if c.get("stage") in ("New", "Called", "Interview link sent"):
            c["stage"] = "Interviewed"


@app.route("/api/i/<cid>/turn", methods=["POST"])
def interview_turn(cid):
    c = store.get(cid)
    if not c or c.get("stage") == "Not moving on":
        return jsonify(error="This link isn't active."), 404
    iv = c.setdefault("interview", {})
    if iv.get("finished"):
        return jsonify(text="", events=[], closing=True, finished=True)
    if not iv.get("started"):
        iv["started"] = _now()
    data = request.get_json(force=True) or {}
    profile = {"name": (c.get("name") or "").split(" ")[0], "location": c.get("location")}
    cv = c.get("screen")
    text, events, closing = _run_turn("selection", None, data.get("history") or [], profile,
                                      _interview_progress(c), cv)
    _record(c, events)
    store.save(c)
    return jsonify(text=text, events=[{"tool": e["tool"]} for e in events], closing=closing,
                   finished=bool(iv.get("finished")))


@app.route("/api/i/<cid>/finish", methods=["POST"])
def interview_finish(cid):
    c = store.get(cid)
    if not c:
        return jsonify(error="This link isn't active."), 404
    _finish(c)
    store.save(c)
    return jsonify(ok=True)


# ---------- tools the AI can call ----------

def _tools(mode: str, module_id: str | None, cv: dict | None = None):
    if mode == "selection":
        return [
            {"toolSpec": {
                "name": "record_check",
                "description": "Record the candidate's answer to one CHECK (availability or a question from their CV), after they've answered it. Use the id of the check you actually asked. Never tell them what you recorded.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "check_id": {"type": "string", "enum": [x["id"] for x in selection_checks(cv)]},
                        "status": {"type": "string", "enum": ["CLEAR", "PARTLY", "OPEN"],
                                   "description": "CLEAR = they answered it fully; PARTLY = some of it; OPEN = no real answer, or it needs the hiring team."},
                        "quote": {"type": "string", "description": "Their own words, quoted exactly."},
                        "note": {"type": "string", "description": "For availability: the days, times and start date they gave, in a few words. Otherwise empty."},
                    },
                    "required": ["check_id", "status", "quote"]}}}},
            {"toolSpec": {
                "name": "record_evidence",
                "description": "Record the evidence the candidate's answer gave on one SITUATION, after they've answered it. This is evidence, not a score: the selector scores. Never tell them what you recorded.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "pill_id": {"type": "string", "enum": list(PILLS)},
                        "status": {"type": "string", "enum": ["EVIDENCED", "PARTIAL", "NOT_EVIDENCED"],
                                   "description": "EVIDENCED = the answer contains what the 'shown when' text describes; PARTIAL = some of it; NOT_EVIDENCED = the answer didn't contain it."},
                        "quote": {"type": "string", "description": "The candidate's own words, quoted exactly, that this status rests on."},
                        "missing": {"type": "string", "description": "What the 'shown when' text asks for that the answer didn't contain, in a few words. Empty if EVIDENCED."},
                    },
                    "required": ["pill_id", "status", "quote"]}}}},
            {"toolSpec": {
                "name": "finish_interview",
                "description": "Call once, after the closing words, when the interview is over.",
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {"note_for_hiring_team": {"type": "string", "description": "Two or three neutral sentences on how the conversation went and what to explore in person. No judgment of the person, no recommendation to hire or not."}},
                    "required": ["note_for_hiring_team"]}}}},
        ]
    pills = [p["id"] for p in course.UNIT_BY_ID[module_id]["pills"]] if module_id in course.UNIT_BY_ID else list(course.PILLS)
    extra = _management_tools(pills) if course.KIND == "management" else []
    return extra + [
        {"toolSpec": {
            "name": "pill_understood",
            "description": "Mark one module of this unit as understood with evidence, only after the person has shown it in their own words through a check (a choice, a reconstructed sequence, a recognized mistake, a new case). Never mark a module just because you explained it.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "pill_id": {"type": "string", "enum": pills},
                    "evidence": {"type": "string", "description": "A short quote of what the person said that shows it."},
                },
                "required": ["pill_id", "evidence"]}}}},
        {"toolSpec": {
            "name": "log_referral",
            "description": "Log a question that needs someone else (manual section 9, the referral log).",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["missing information", "unclear content", "necessary escalation"]},
                    "question": {"type": "string"},
                },
                "required": ["type", "question"]}}}},
    ]


def _management_tools(pills: list) -> list:
    """The management course keeps two kinds of evidence: the person's
    reasoning (for People, as training evidence) and how the work actually
    runs (for Organization, to verify)."""
    return [
        {"toolSpec": {
            "name": "record_reasoning",
            "description": "Keep the person's reasoning on one module, once they've reasoned as far as they can. Training evidence, never a score. Never tell them what you recorded.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "pill_id": {"type": "string", "enum": pills},
                    "characteristics": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 17},
                                        "description": "The characteristics (section 3) their reasoning showed or touched."},
                    "quote": {"type": "string", "description": "Their own words that carry the reasoning, quoted exactly, in their language."},
                    "included": {"type": "string", "description": "What their reasoning contained, in a few neutral words."},
                    "missing": {"type": "string", "description": "What the sustainable reasoning has that theirs didn't, neutrally. Empty if nothing."},
                    "kind": {"type": "string", "enum": ["simulation", "self-reported real work", "own account"],
                             "description": "simulation for a case or card; self-reported real work for the real task; own account for Looking back."},
                },
                "required": ["pill_id", "characteristics", "quote", "included", "kind"]}}}},
        {"toolSpec": {
            "name": "record_how_work_runs",
            "description": "Keep something the person described about how a process actually works here. Knowledge about the process, to verify against the procedures; never a complaint about anyone. No names.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "process": {"type": "string", "description": "The process, in a few words (for example: receiving deliveries, ordering supplies, discounts)."},
                    "described": {"type": "string", "description": "What they said happens, in neutral words, without any person's name."},
                    "source": {"type": "string", "enum": ["what I do", "what I've seen", "what I've heard"]},
                },
                "required": ["process", "described", "source"]}}}},
    ]


# ---------- the conversation ----------

def _messages(history):
    """Client history is plain text turns. Bedrock needs alternating roles
    starting with the user, so merge repeats and drop empty turns."""
    out = []
    for turn in history[-MAX_TURNS:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"][0]["text"] += "\n\n" + text
        else:
            out.append({"role": role, "content": [{"text": text}]})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"text": START}]})
    return out


def _converse(system, messages, tools, second_route=False):
    kwargs = dict(system=system, messages=messages,
                  inferenceConfig={"maxTokens": 900, "temperature": 0.6},
                  toolConfig={"tools": tools})

    def call(**kw):
        if not second_route or not SECOND_MODEL_ID:
            return _bedrock.converse(modelId=MODEL_ID, **kw)
        try:
            return _bedrock_once.converse(modelId=MODEL_ID, **kw)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in _AI_BUSY:
                raise
            app.logger.warning("AI route 1 busy, using route 2")
            return _bedrock.converse(modelId=SECOND_MODEL_ID, **kw)

    try:
        resp = call(**kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ValidationException" or "cache" not in str(exc).lower():
            raise
        kwargs["system"] = [b for b in system if "cachePoint" not in b]
        resp = call(**kwargs)
    u = resp.get("usage") or {}
    app.logger.warning("AI usage in=%s out=%s cache_read=%s cache_write=%s", u.get("inputTokens"), u.get("outputTokens"),
                       u.get("cacheReadInputTokens"), u.get("cacheWriteInputTokens"))
    return resp


def _run_turn(mode, module_id, history, profile, progress, cv=None):
    system = (selection_system(profile, progress, cv) if mode == "selection"
              else training_system(module_id, profile, progress))
    messages = _messages(history) or [{"role": "user", "content": [{"text": START}]}]
    tools = _tools(mode, module_id, cv)
    closing = mode == "selection" and selection_closing(progress, cv)
    # Said next to the answer, where the AI can't miss it: the one step to ask
    # now, or no new question at all on the closing turn.
    if mode == "selection" and messages[-1]["role"] == "user" and len(messages) > 3:
        note = ("this was the last answer. Record it, then close: thank them and say goodbye. Don't ask anything new."
                if closing else selection_next(progress, cv))
        if note:
            messages[-1]["content"][0]["text"] += f"\n\n(Note to the AI: {note})"
    # Training: the same reminder next to the answer, so a module the person
    # has just shown gets saved instead of only praised.
    if mode == "training" and course.KIND == "management" and messages[-1]["role"] == "user" and len(messages) >= 3:
        todo = [p for p in course.UNIT_BY_ID[module_id]["pills"] if p["id"] not in ((progress or {}).get("understood") or {})]
        if todo:
            cur = todo[0]
            messages[-1]["content"][0]["text"] += (
                ""
                + (f"\n\n(Note to the AI: their message is in {progress['language']}: answer only in {progress['language']}.)"
                   if progress.get("language") else "")
                + ("\n\n(Note to the AI: we've spent several exchanges on this part. Wrap it up now: share the reference"
                   " briefly as one way of seeing it, call record_reasoning and pill_understood, and move on.)"
                   if int(progress.get("part_turns") or 0) >= 5 else "")
                + "\n\n(Note to the AI: first, if this message describes how something actually works here (who does what,"
                " what gets checked or skipped, how it's really done), call record_how_work_runs for it in this turn,"
                " unless it's already kept."
                f" The current part is {cur['title']}. Look for reasoning, not the right answer."
                " If something in the sustainable reasoning is still missing and you've asked fewer than three follow-ups"
                " on it, ask about one missing part. If they've reasoned as far as they can, share the reference briefly as"
                " one way of seeing it, and in that turn call record_reasoning and pill_understood for"
                f" {cur['id']}. If they've described how something actually works here, call record_how_work_runs."
                " Stay on this part; don't steer toward another module's topic. Never say right, wrong, correct or"
                " incorrect, and never mention recording or saving. Keep this turn under 80 words.)")
    elif mode == "training" and messages[-1]["role"] == "user" and len(messages) >= 3:
        todo = [p for p in course.UNIT_BY_ID[module_id]["pills"] if p["id"] not in ((progress or {}).get("understood") or {})]
        if todo:
            cur = todo[0]
            # Their own question may be a later module's situation: that one comes first.
            asked = messages[-1]["content"][0]["text"].lower()
            for p in todo[1:]:
                words = {w for w in re.findall(r"[a-z]{5,}", p["scenario"].lower())}
                if len(words & set(re.findall(r"[a-z]{5,}", asked))) >= 3:
                    cur = p
                    break
            shows = ("every part of it, because this is a safety unit (if a part is missing, ask only about that part)"
                     if course.UNIT_BY_ID[module_id].get("safety_critical") else "the essentials of it")
            messages[-1]["content"][0]["text"] += (
                f"\n\n(Note to the AI: the current module is {cur['title']}. If this answer, with what they said before,"
                f" shows {shows} ({cur['known']}), call pill_understood for {cur['id']} in this turn and then"
                " start the next module. If you're going to tell them they've got it, you must call it. If something"
                " essential is still missing, ask only about that. Don't call it if the answer contains a mistake the"
                " course names, an invented time, or a dish or ingredient not on the dish cards: correct that first."
                " If their message asks a question of their own, answer it first (rule 0). If you say a detail comes from"
                " the lead because it isn't given here, call log_referral in this turn. Keep this turn under 70 words.)")

    events, texts = [], []
    for _ in range(6):
        resp = _converse(system, messages, tools, second_route=mode == "training")
        content = [b for b in resp["output"]["message"]["content"] if "text" not in b or b["text"].strip()]
        if not content:
            break
        messages.append({"role": "assistant", "content": content})
        results = []
        for block in content:
            if "text" in block:
                texts.append(block["text"].strip())
            if "toolUse" in block:
                tu = block["toolUse"]
                events.append({"tool": tu["name"], "input": tu.get("input") or {}})
                results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": "recorded"}]}})
        if results:
            messages.append({"role": "user", "content": results})
            if mode == "training" and texts and texts[-1].rstrip().endswith("?"):
                break
            continue
        if texts or any(e["tool"] == "finish_interview" for e in events):
            break
        # Tools only and no words yet: ask for the actual turn.
        messages.append({"role": "user", "content": [{"text": "(Now say your next turn to the person.)"}]})

    if not texts and not any(e["tool"] == "finish_interview" for e in events):
        # Never send the person a blank turn.
        if messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": [{"text": "(Say your next turn to the person, in one or two sentences.)"}]})
        resp = _converse(system, messages, tools, second_route=mode == "training")
        texts += [b["text"].strip() for b in resp["output"]["message"]["content"] if b.get("text", "").strip()]

    # Selection's closing turn: make sure the interview really ends here, with
    # the hiring team's note, instead of carrying on after the goodbye.
    if closing and not any(e["tool"] == "finish_interview" for e in events):
        if messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": [{"text": "(The interview is over. Write the note for the hiring team.)"}]})
        resp = _bedrock.converse(modelId=MODEL_ID, system=[b for b in system if "cachePoint" not in b], messages=messages,
                                 inferenceConfig={"maxTokens": 400},
                                 toolConfig={"tools": [t for t in tools if t["toolSpec"]["name"] == "finish_interview"],
                                             "toolChoice": {"tool": {"name": "finish_interview"}}})
        for block in resp["output"]["message"]["content"]:
            if "toolUse" in block:
                events.append({"tool": "finish_interview", "input": block["toolUse"].get("input") or {}})

    text = _clean("\n\n".join(texts))
    if mode == "training" and course.KIND == "management":
        text = _no_verdicts(text)
    return text, events, closing


@app.route("/api/turn", methods=["POST"])
def api_turn():
    """Training turns: one unit of the course file."""
    data = request.get_json(force=True) or {}
    module_id = data.get("module_id")
    if data.get("mode") != "training" or module_id not in course.UNIT_BY_ID:
        return jsonify(error="Unknown unit."), 400
    progress = data.get("progress") or {}
    hid = session.get("hire")
    h = store.get_hire(hid) if hid else None
    profile = data.get("profile") or {}
    if h:
        hp = _progress(h)
        progress = dict(progress, understood=hp["understood"], last_note=hp["last_note"].get(module_id, ""),
                        work_kept=[f"{w['process']}: {w['described']}" for w in hp.get("work_notes") or []][-12:],
                        reasoning_kept=sorted({r["module"] for r in hp.get("reasoning") or []}))
        profile = dict(profile, name=h["name"].split(" ")[0], location=h["location"])
    history = data.get("history") or []
    cur_pid = None
    if course.KIND == "management":
        todo = [p["id"] for p in course.UNIT_BY_ID[module_id]["pills"] if p["id"] not in (progress.get("understood") or {})]
        cur_pid = todo[0] if todo else None
        progress = dict(progress, part_turns=int(((hp.get("part_turns") or {}).get(cur_pid) or 0) if h and cur_pid else 0),
                        language=_language(history))
    if not history:
        # A session with the Trainer on this unit opens the test again after two failed tries.
        lock = _locks().get(module_id) or {}
        if lock.get("fails"):
            _set_lock(module_id, dict(lock, trained=True))
    understood = len((progress.get("understood") or {}).keys() & {p["id"] for p in course.UNIT_BY_ID[module_id]["pills"]})
    try:
        text, events, closing = _run_turn("training", module_id, history, profile, progress)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("ThrottlingException", "ServiceUnavailableException",
                                                          "ModelNotReadyException"):
            app.logger.warning("AI busy: %s", exc)
            return jsonify(error="The Trainer is busy for a moment.", busy=True), 503
        raise
    # The AI sometimes marks modules again when it closes a course: keep only
    # the first save of each module.
    done, kept = set((progress.get("understood") or {}).keys()), []
    for e in events:
        pid = (e.get("input") or {}).get("pill_id")
        if e["tool"] == "pill_understood" and pid in done:
            continue
        done.add(pid) if e["tool"] == "pill_understood" else None
        kept.append(e)
    new = sum(1 for e in kept if e["tool"] == "pill_understood")
    refs = [dict(type=e["input"].get("type"), question=str(e["input"].get("question") or "")[:300], unit=module_id, date=_now())
            for e in kept if e["tool"] == "log_referral"]
    sid = re.sub(r"[^0-9]", "", str(data.get("session") or ""))[:16] or "unknown"
    reasoning, work = _management_records(module_id, kept, sid) if course.KIND == "management" else ([], [])
    if h and course.KIND == "management":
        try:
            store.save_conversation(hid, module_id, sid, history + [{"role": "assistant", "text": text}], _now())
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("conversation not saved: %s", exc)
    if h:
        unit_pills = {p["id"] for p in course.UNIT_BY_ID[module_id]["pills"]}
        def save_progress(rec):
            p = _progress(rec)
            for e in kept:
                pid = (e.get("input") or {}).get("pill_id")
                if e["tool"] == "pill_understood" and pid in unit_pills and pid not in p["understood"]:
                    p["understood"][pid] = {"evidence": str(e["input"].get("evidence") or "")[:300], "date": _now()}
            for r in refs:
                # The same question asked again is one referral.
                if not any(_same_note({"process": "", "described": r["question"]}, {"process": "", "described": x["question"]})
                           for x in p["referrals"] if x.get("unit") == r["unit"]):
                    p["referrals"].append(r)
            if course.KIND == "management" and cur_pid and history and history[-1].get("role") == "user":
                pt = p.setdefault("part_turns", {})
                pt[cur_pid] = int(pt.get(cur_pid) or 0) + 1
            if reasoning or work:
                kept_r = p.setdefault("reasoning", [])
                for r in reasoning:
                    # One record per module per session: the AI sometimes calls it twice.
                    if not any(x["module"] == r["module"] and x.get("session") == r["session"] for x in kept_r):
                        kept_r.append(r)
                notes = p.setdefault("work_notes", [])
                for w in work:
                    # The same description told twice is one note.
                    if not any(_same_note(w, x) for x in notes):
                        notes.append(w)
        store.update_hire(hid, save_progress)
    def upd(rec):
        c = _course(rec, module_id)
        c["modules_done"] = max(c.get("modules_done", 0), min(c["modules"], understood + new))
        c["last"] = _now()
        if refs:
            rec["referrals"] = (rec.get("referrals") or []) + refs
    _track(upd)
    return jsonify(text=text, events=kept, closing=closing)


_ES = {"que", "para", "los", "las", "una", "pero", "porque", "creo", "hay", "está", "esto", "cuando", "también", "sí", "nosotros", "hago", "haría"}
_PT = {"não", "você", "isso", "também", "porque", "então", "uma", "para", "eu", "fazer", "acho"}
_IT = {"che", "non", "per", "sono", "anche", "perché", "quindi", "della", "questo", "faccio", "credo"}


def _language(history: list) -> str:
    """The language of the person's last message, when it's clearly not English."""
    last = next((t.get("text") or "" for t in reversed(history) if t.get("role") == "user"), "")
    words = set(re.findall(r"[a-záéíóúñãõçàèìòù]+", re.sub(r"^\[\d+ min\]", "", last).lower()))
    for name, vocab in (("Spanish", _ES), ("Portuguese", _PT), ("Italian", _IT)):
        if len(words & vocab) >= 2:
            return name
    return ""


# Words that may be capitalized mid-sentence without being someone's name.
_NOT_NAMES = {"Pino", "Rome", "Rome's", "Flavours", "Winter", "Park", "Mount", "Dora", "Clover", "Florida", "Costco",
              "Sysco", "Indeed", "Italian", "English", "Spanish", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday", "January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December", "Module", "Legacy", "Manager", "Model", "Trainer", "Green", "Yellow",
              "Blue", "Red", "OK", "Ok", "AI", "POS", "FOH", "BOH", "GM", "Lunes", "Martes", "Miércoles", "Jueves",
              "Viernes", "Sábado", "Domingo", "Mount Dora"}


def _no_names(text: str) -> str:
    """Roles, not names: a capitalized word in the middle of a sentence that
    isn't a known place, product, day or term is taken to be a name."""
    def sub(m):
        w = m.group(2)
        return m.group(1) + ("someone" if w not in _NOT_NAMES else w)
    return re.sub(r"(?<![.!?:])(\s)([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)(?=[\s,.;:!?'])", sub, text)


def _same_note(a: dict, b: dict) -> bool:
    words = lambda t: set(re.findall(r"[a-z]{3,}", t.lower()))
    wa, wb = words(a["process"] + " " + a["described"]), words(b["process"] + " " + b["described"])
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def _management_records(unit_id: str, events: list, sid: str = ""):
    """The structured records from one turn: reasoning (People, training
    evidence) and how the work runs (Organization, to verify)."""
    pills = {p["id"] for p in course.UNIT_BY_ID[unit_id]["pills"]}
    now, reasoning, work = _now(), [], []
    for e in events:
        i = e.get("input") or {}
        if e["tool"] == "record_reasoning" and i.get("pill_id") in pills and str(i.get("quote") or "").strip():
            chars = sorted({int(c) for c in i.get("characteristics") or [] if str(c).isdigit() and 1 <= int(c) <= 17})
            # The kind follows the part, not the AI: case and card are simulation, the real task is
            # self-reported real work, Looking back is their own account.
            pid = i["pill_id"]
            kind = ("self-reported real work" if pid.endswith(".task") else "own account" if pid.startswith("W5.")
                    else "simulation")
            reasoning.append({"unit": unit_id, "module": pid, "characteristics": chars, "kind": kind,
                              "quote": _no_names(str(i["quote"]).strip()[:600]),
                              "included": _no_names(str(i.get("included") or "")[:400]),
                              "missing": _no_names(str(i.get("missing") or "")[:400]), "date": now, "session": sid})
        elif e["tool"] == "record_how_work_runs" and str(i.get("described") or "").strip():
            src = i.get("source") if i.get("source") in ("what I do", "what I've seen", "what I've heard") else "what I've heard"
            work.append({"unit": unit_id, "process": str(i.get("process") or "")[:120],
                         "described": _no_names(str(i["described"]).strip()[:600]), "source": src, "status": "to verify",
                         "date": now})
    return reasoning, work


_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")
_IDS = re.compile(r"\s*\(?\b(m\d{1,2}\.[a-z_]+|[A-DW][1-5]\.[a-z_]+|cv[1-4])\b\)?")


def _clean(text: str) -> str:
    """House style: no em or en dashes, emoji, bold or internal ids in what people read."""
    text = text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ").replace("–", "-")
    text = _IDS.sub("", _EMOJI.sub("", text.replace("**", "")))
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# Management course: we look at the reasoning, not for the right answer, so a
# short verdict or a word about record keeping the AI slips in is taken out.
_VERDICT = re.compile(
    r"(?:(?<=^)|(?<=[.!?]\s))[^.!?\n]*?\b(?:that'?s (?:the |exactly )?(?:right|correct|wrong)|you'?ve got it|exactly right|"
    r"spot on|well done|great answer|good answer|perfect|that'?s it(?=[.!])|the thinking i'?m looking for|i'?ll (?:note|record|save|write down)|let me (?:note|record|save)|"
    r"i'?ve (?:noted|recorded|saved))\b[^.!?\n]*[.!?]\s*", re.I)


_PRAISE_LEAD = re.compile(r"(?:(?<=^)|(?<=[.!?]\s))(?:Exactly|Perfect|Great|Excellent|Exacto|Exactamente|Perfecto|Excelente|Genial|Muy bien|Esatto|Perfetto|Ottimo|Exato|Perfeito|Ótimo)(?:,\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?[,.!]\s*", re.I)
_PRAISE_CLAUSE = re.compile(r",?\s*(?:that'?s|this is) (?:solid|great|excellent|perfect|spot on)(?: thinking| reasoning)?(?=[.!,])|(?:(?<=^)|(?<=[.!?]\s))(?:that'?s )?(?:solid|good|great) thinking[.!]\s*", re.I)
_SOLID_SENT = re.compile(r"(?:(?<=^)|(?<=[.!?]\s))That'?s (?:a |your )?(?:solid|good|great|excellent)(?: \w+)?[.!:]\s*", re.I)
_SOLID_WORD = re.compile(r"\bsolid\s+(?=[a-z])|\s+solid(?=[:.,!])", re.I)
_RIGHT_THAT = re.compile(r"\b[Yy]ou'?re right (?:that |about )", re.I)
_SENT_Q = re.compile(r"(?<=\?)(?=\s+[A-Z¿\"]|\s*$)")


def _one_question(text: str) -> str:
    """One question at a time: keep everything up to the first question that ends a sentence."""
    parts = _SENT_Q.split(text)
    if sum(1 for p in parts if p.rstrip().endswith("?")) <= 1:
        return text
    out = []
    for p in parts:
        out.append(p)
        if p.rstrip().endswith("?"):
            break
    return "".join(out).strip()


def _no_verdicts(text: str) -> str:
    out = _VERDICT.sub("", text)
    out = _PRAISE_LEAD.sub("", out)
    out = _PRAISE_CLAUSE.sub("", out)
    out = _RIGHT_THAT.sub(lambda m: "", out)
    out = _SOLID_SENT.sub("", out)
    out = _SOLID_WORD.sub("", out)
    out = re.sub(r"^\s*[.,]\s*", "", out)
    out = re.sub(r"([.!?])\s*[.,](?=\s|$)", r"\1", out)
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    out = _one_question(out)
    return re.sub(r"[ \t]{2,}", " ", out).strip() or text


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5099")), debug=False)
