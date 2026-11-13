"""CV Selection SP — local prototype (Shelbi + Pino CV engines, consolidated).

Position → Upload CVs → Analyze → Ranking. Scope ends at the ranking: no
interviews, messages, appointments or decisions (those stay in Selection).

Reuses, unchanged, from this worktree:
- Pino (`RF-One Data Store/.../selection/parsing`): text extraction, the
  duplicate content hash, the date normalizer, the AI client (Bedrock);
  `Selection/workspace/ai_adapter`: contact redaction, the quote rule, the
  "never use" list, the JSON retry note;
- Shelbi (`Selection/workspace`): the Server and Line Cook profiles, the
  stability thresholds, the scanned-PDF transcription seam.

    python app.py [--port 5110]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOFTWARE = HERE.parent
sys.path[:0] = [str(HERE), str(SOFTWARE / "Selection"), str(SOFTWARE / "RF-One Data Store")]

# Selection's local AI settings (read only) and its AWS profile; no new credential mechanism.
_AI_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Selection" / "ai.json"
if _AI_FILE.exists():
    for _k, _v in json.loads(_AI_FILE.read_text(encoding="utf-8")).items():
        os.environ.setdefault(_k, str(_v))
os.environ.setdefault("AWS_PROFILE", "rfone-dev-login")

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for  # noqa: E402

from rfone_data_store.selection.parsing import ai_client  # noqa: E402
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable  # noqa: E402
from rfone_data_store.selection.parsing.dedup import compute_content_hash  # noqa: E402
from rfone_data_store.selection.parsing.text_extraction import SUPPORTED_EXTENSIONS, extract_text  # noqa: E402
from workspace import ai_adapter  # noqa: E402

import sp_analysis  # noqa: E402
import sp_profiles as spp  # noqa: E402
import sp_ranking  # noqa: E402
import sp_store as store  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SP_SECRET", os.urandom(16).hex())
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
WORKERS = int(os.environ.get("SP_WORKERS", "3"))  # 4 in parallel made Bedrock throttle (1 Nov 2026)
_pool = ThreadPoolExecutor(max_workers=WORKERS)
GENERATE = None  # tests replace the AI call here


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _position(pid: str) -> dict:
    position = store.load(pid)
    if position is None:
        abort(404)
    return position


def local_time(iso: str | None, tz: str) -> str:
    """Times shown to a person are in the position's local time (RF-One UI rule 1)."""
    if not iso:
        return ""
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(iso).astimezone(ZoneInfo(tz)).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso


app.jinja_env.globals.update(local_time=local_time, STATUS_LABELS=sp_ranking.STATUS_LABELS,
                             CRIT=spp.CRITICALITY_LABELS, level_label=sp_ranking.spp_level,
                             summary=sp_ranking.summary)


def _approved(position) -> dict | None:
    return position.get("approved")


def _current(position, c) -> bool:
    approved = _approved(position)
    return bool(approved and c.get("status") == "DONE" and c.get("analyzed_version") == approved["version"])


def ranked(position) -> list[dict]:
    approved = _approved(position)
    if not approved:
        return []
    cands = [dict(c) for c in position["candidates"].values() if _current(position, c)]
    return sp_ranking.rank(cands, approved["requirements"], position.get("manual_order"))


def _contacts(text: str) -> tuple[str | None, str | None]:
    email = ai_adapter._EMAIL_RE.search(text or "")
    phone = ai_adapter._PHONE_RE.search(text or "")
    digits = "".join(ch for ch in phone.group(0) if ch.isdigit())[-10:] if phone else None
    return (email.group(0).lower() if email else None), digits


# ---------------------------------------------------------------------------
# Positions and requirements
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html", positions=store.all_positions(), roles=spp.ROLES)


@app.route("/positions/new", methods=["POST"])
def position_new():
    role = request.form.get("role")
    if role not in spp.ROLES:
        flash("Choose Server or Line Cook.")
        return redirect(url_for("home"))
    position = {"id": store.new_id(), "title": (request.form.get("title") or spp.ROLES[role]).strip(), "role": role,
                "location": (request.form.get("location") or "Mount Dora").strip(),
                "timezone": request.form.get("timezone") or "America/New_York", "created_at": store.now_iso(),
                "requirements_draft": spp.default_requirements(role), "approved": None, "versions": [],
                "manual_order": [], "candidates": {}}
    store.save(position)
    return redirect(url_for("position_page", pid=position["id"]))


@app.route("/p/<pid>")
def position_page(pid):
    position = _position(pid)
    with store.LOCK:
        rows = ranked(position)
        cands = sorted(position["candidates"].values(), key=lambda c: c["uploaded_at"])
    return render_template("position.html", p=position, rows=rows, cands=cands,
                           running=sum(1 for c in cands if c["status"] in ("QUEUED", "ANALYZING")),
                           to_analyze=sum(1 for c in cands if not _current(position, c)
                                          and c["status"] not in ("QUEUED", "ANALYZING")),
                           current=lambda c: _current(position, c))


@app.route("/p/<pid>/requirements", methods=["POST"])
def requirements_save(pid):
    position = _position(pid)
    with store.LOCK:
        if request.form.get("action") == "edit":
            position["requirements_draft"] = json.loads(json.dumps(position["approved"]["requirements"]))
            position["editing"] = True
            store.save(position)
            return redirect(url_for("position_page", pid=pid) + "#requirements")
        draft = position["requirements_draft"]
        for r in draft:
            if request.form.get(f"crit_{r['id']}") in spp.CRITICALITY_LABELS:
                r["criticality"] = request.form[f"crit_{r['id']}"]
            weight = request.form.get(f"weight_{r['id']}", type=int)
            if weight is not None:
                r["weight"] = max(0, min(100, weight))
        remove = request.form.get("remove")
        if remove:
            position["requirements_draft"] = draft = [r for r in draft if r["id"] != remove]
        name = (request.form.get("new_name") or "").strip()
        if name:
            index = 1 + sum(1 for r in draft if r["id"].startswith("custom"))
            draft.append(spp.custom_requirement(index, name, request.form.get("new_look_for") or name,
                                                request.form.get("new_crit") or spp.PREFERRED,
                                                request.form.get("new_weight", type=int) or 5))
        if request.form.get("action") == "approve":
            if not any(r["criticality"] == spp.MUST_HAVE for r in draft):
                flash("Mark at least one requirement as Must-have: the ranking groups depend on it.")
            else:
                version = len(position["versions"]) + 1
                approved = {"version": version, "approved_at": store.now_iso(), "approved_by": "Manager (local)",
                            "requirements": json.loads(json.dumps(draft))}
                position["versions"].append(approved)
                position["approved"] = approved
                position["editing"] = False
                position["manual_order"] = []
                flash(f"Requirements approved (version {version}). Press Analyze to rank the CVs.")
        store.save(position)
    return redirect(url_for("position_page", pid=pid) + "#requirements")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.route("/p/<pid>/upload", methods=["POST"])
def upload(pid):
    position = _position(pid)
    files = [f for f in request.files.getlist("cv") if f and f.filename]
    if not files:
        flash("Select at least one CV file.")
        return redirect(url_for("position_page", pid=pid))
    added = dup = bad = 0
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            bad += 1
            flash(f"{f.filename}: not supported (PDF, DOCX or TXT).")
            continue
        cid = store.new_id()
        path = store.cv_dir(pid) / f"{cid}{ext}"
        f.save(path)
        text = extract_text(str(path), ext)
        content_hash = compute_content_hash(text, None) if text else hashlib.sha256(path.read_bytes()).hexdigest()
        with store.LOCK:
            same = next((c for c in position["candidates"].values() if c["hash"] == content_hash), None)
            if same:
                path.unlink(missing_ok=True)
                dup += 1
                flash(f"{f.filename}: duplicate of {same['filename']}, not added.")
                continue
            email, phone = _contacts(text or "")
            note = None
            other = next((c for c in position["candidates"].values()
                          if (email and c.get("email") == email) or (phone and c.get("phone") == phone)), None)
            if other:
                note = f"Possible duplicate: same email or phone as {other['filename']}. Please verify."
            position["candidates"][cid] = {
                "id": cid, "filename": f.filename, "stored": path.name, "ext": ext, "hash": content_hash,
                "text": text, "text_source": "Text of the file" if text else
                ("Scanned PDF: read by the AI at analysis" if ext == ".pdf" else None),
                "email": email, "phone": phone, "uploaded_at": store.now_iso(), "status": "UPLOADED",
                "duplicate_note": note, "analysis": None, "error": None}
            store.save(position)
            added += 1
    flash(f"{added} CV(s) added" + (f", {dup} duplicate(s) skipped" if dup else "") +
          (f", {bad} not supported" if bad else "") + ".")
    return redirect(url_for("position_page", pid=pid))


# ---------------------------------------------------------------------------
# Analysis (one AI reading per CV, in parallel)
# ---------------------------------------------------------------------------

def _transcribe_scanned(path: Path) -> str:
    """Shelbi's scanned-PDF reading (`cv_reading._transcribe_transport`): pages as images, text copied by the AI."""
    import pdfplumber

    from workspace import cv_reading
    images = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages[:cv_reading.PDF_PAGES]:
            buffer = io.BytesIO()
            page.to_image(resolution=130).original.convert("RGB").save(buffer, "PNG")
            images.append(buffer.getvalue())
    if not images:
        raise AIProviderUnavailable("The PDF has no pages.")
    return cv_reading._transcribe_transport(images)


def _analyze_one(pid: str, cid: str) -> None:
    position = store.load(pid)
    with store.LOCK:
        c = position["candidates"][cid]
        c["status"] = "ANALYZING"
        approved = position["approved"]
        store.save(position)
    try:
        text = c.get("text")
        if not text and c["ext"] == ".pdf":
            text = _transcribe_scanned(store.cv_dir(pid) / c["stored"])
            with store.LOCK:
                c["text"], c["text_source"] = text, "Scanned PDF: text read by the AI from the page images"
                c["email"], c["phone"] = _contacts(text)
        analysis = sp_analysis.analyze_cv(role_code=position["role"], requirements=approved["requirements"],
                                          cv_text=text or "", generate=GENERATE)
        provider, model = ai_client.active_provider_description()
        with store.LOCK:
            c.update(status="DONE", analysis=analysis, analyzed_version=approved["version"],
                     analyzed_at=store.now_iso(), model=f"{provider} {model or ''}".strip(), error=None)
            store.save(position)
    except Exception as exc:  # one CV failing never stops the others
        with store.LOCK:
            c.update(status="ERROR", error=str(exc)[:500])
            store.save(position)


@app.route("/p/<pid>/analyze", methods=["POST"])
def analyze(pid):
    position = _position(pid)
    if not _approved(position) or position.get("editing"):
        flash("Approve the requirements first: the analysis applies the approved version.")
        return redirect(url_for("position_page", pid=pid))
    everything = request.form.get("all") == "1"
    queued = 0
    with store.LOCK:
        for c in position["candidates"].values():
            if c["status"] in ("QUEUED", "ANALYZING"):
                continue
            if everything or not _current(position, c):
                c["status"] = "QUEUED"
                queued += 1
                _pool.submit(_analyze_one, pid, c["id"])
        if everything:
            position["manual_order"] = []
        store.save(position)
    flash(f"Analyzing {queued} CV(s)…" if queued else "Every CV is already analyzed with the approved requirements.")
    return redirect(url_for("position_page", pid=pid))


@app.route("/p/<pid>/status")
def status(pid):
    position = _position(pid)
    with store.LOCK:
        counts = {}
        for c in position["candidates"].values():
            counts[c["status"]] = counts.get(c["status"], 0) + 1
    return jsonify(counts)


# ---------------------------------------------------------------------------
# Manual order
# ---------------------------------------------------------------------------

@app.route("/p/<pid>/move", methods=["POST"])
def move(pid):
    position = _position(pid)
    with store.LOCK:
        order = [c["id"] for c in ranked(position)]
        cid, direction = request.form.get("cid"), request.form.get("dir")
        if request.form.get("reset"):
            position["manual_order"] = []
        elif cid in order:
            i = order.index(cid)
            j = i - 1 if direction == "up" else i + 1
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
            position["manual_order"] = order
        store.save(position)
    return redirect(url_for("position_page", pid=pid) + "#ranking")


# ---------------------------------------------------------------------------
# Candidate detail and original CV
# ---------------------------------------------------------------------------

@app.route("/p/<pid>/c/<cid>")
def candidate(pid, cid):
    position = _position(pid)
    with store.LOCK:
        rows = ranked(position)
        row = next((r for r in rows if r["id"] == cid), None)
        c = position["candidates"].get(cid) or abort(404)
    return render_template("candidate.html", p=position, c=c, row=row, total=len(rows))


@app.route("/p/<pid>/c/<cid>/cv")
def original_cv(pid, cid):
    position = _position(pid)
    c = position["candidates"].get(cid) or abort(404)
    return send_file(store.cv_dir(pid) / c["stored"], download_name=c["filename"],
                     as_attachment=c["ext"] == ".docx")


@app.route("/p/<pid>/c/<cid>/text")
def cv_text(pid, cid):
    c = _position(pid)["candidates"].get(cid) or abort(404)
    return (c.get("text") or "(no text yet)"), 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CV Selection SP (local prototype)")
    parser.add_argument("--port", type=int, default=5110)
    args = parser.parse_args()
    print(f"CV Selection SP: http://127.0.0.1:{args.port}/  ·  data: {store.DATA}")
    app.run("127.0.0.1", args.port, debug=False, threaded=True)
