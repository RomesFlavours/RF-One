"""Discover WHY Patterns on the Rules and Profiles page (BANK_WHY_PATTERNS_001).

The AI proposes, a person decides: a discovery (background) reads every
description format once, consolidates WHY rules and verifies them; the page
shows each proposal with what it covers, what argues against it and what
approving it changes. Approve / Reject / Discuss with AI. Only Approve
creates a rule, and an approved rule is executed by the single engine as
code, without AI. Nothing here writes a classification.
"""
import json
import os
import threading

from flask import jsonify, request
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import rule_application_safety as safety, why_patterns
import bank_chatgpt

KIND = "WHY_DISCOVERY"


def enabled() -> bool:
    """Discover WHY Patterns is kept but switched off (Product Owner, 2026-10-25: back to the old
    "Find standard formats" generator). RFONE_BANK_WHY_PATTERNS=1 shows it and registers its routes again;
    otherwise the page does not show it and none of its addresses exists. Its data and rules are kept."""
    return os.environ.get("RFONE_BANK_WHY_PATTERNS") == "1"


def _read(record):
    return json.loads(record.payload)


def _write(record, data):
    record.payload = json.dumps(data, ensure_ascii=False, default=str)


def _latest_cache(db, before_id=None):
    """The AI readings of the previous discovery: a format whose movements did not change is not asked again."""
    q = select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == KIND).order_by(m.BankFlowArtifact.id.desc())
    for record in db.scalars(q.limit(10)):
        if before_id and record.id >= before_id:
            continue
        data = _read(record)
        if data.get("cache"):
            return data["cache"]
    return {}


def discovery(factory, scan_id, generate=bank_chatgpt.generate_json):
    """Background discovery; progress and result are kept on the scan record."""
    def save(**values):
        with factory() as db:
            record = db.get(m.BankFlowArtifact, scan_id)
            data = _read(record)
            data.update(values)
            _write(record, data)
            db.commit()
    try:
        save(status="RUNNING", step="Reading the movements and their information")
        with factory() as db:
            cache = _latest_cache(db, before_id=scan_id)
            result = why_patterns.discover(
                db, generate, cache=cache,
                progress=lambda done, total: save(step=f"AI reading the formats: batch {done} of {total}"))
        save(status="PARTIAL" if result["errors"] else "COMPLETE", step="", **result)
    except Exception as exc:  # noqa: BLE001 — the page shows the reason; nothing was changed
        save(status="ERROR", error=str(exc)[:500])


def _public(data):
    """The scan as the page reads it (the AI reading cache stays on the server)."""
    return {k: v for k, v in data.items() if k != "cache"}


def _rule_row(rule, version, spec):
    return dict(id=rule.id, title=rule.user_title or rule.title, text=version.rule_text, status=rule.status,
                why=spec.get("why"), version=version.version_no, created_at=str(rule.created_at)[:16],
                optional=why_patterns.uses_extra(spec))


def why_rules(db):
    return [_rule_row(r, v, s) for r, v, s in why_patterns.all_rules(db) if s.get("scope") != "WHO"]


def _start_engine_run():
    """The approved knowledge changed: the single engine re-runs in the background (no-op when unavailable)."""
    try:
        import bank_guided_reconciliation
        bank_guided_reconciliation.run_after_import()
    except Exception:  # noqa: BLE001 — the next automatic check runs it anyway
        pass


def register(app, *, gate, SessionFactory, require_csrf, owner, endpoint, consent):
    def scan(db, scan_id):
        record = db.get(m.BankFlowArtifact, scan_id)
        if record is None or record.kind != KIND or record.account_id != owner(db):
            raise ValueError("Discovery unavailable. Run Discover WHY Patterns again.")
        return record

    def proposal_of(data, proposal_id):
        found = next((p for p in data.get("proposals", []) if p["id"] == proposal_id), None)
        if found is None:
            raise ValueError("Proposal unavailable.")
        if found["status"] != "PROPOSED":
            raise ValueError(f"This proposal is already {found['status'].lower()}.")
        return found

    @app.route("/bank/flow/why-discover", methods=["POST"])
    @gate
    @endpoint
    def bank_why_discover():
        require_csrf()
        consent()
        with SessionFactory() as db:
            record = m.BankFlowArtifact(kind=KIND, payload=json.dumps(dict(status="QUEUED", proposals=[])),
                                        account_id=owner(db))
            db.add(record)
            db.commit()
            scan_id = record.id
        if not app.testing:
            threading.Thread(target=discovery, args=(SessionFactory, scan_id), daemon=True,
                             name="bank-why-discovery").start()
        return jsonify(ok=True, id=scan_id)

    @app.route("/bank/flow/why-discover/latest")
    @gate
    @endpoint
    def bank_why_discover_latest():
        with SessionFactory() as db:
            record = db.scalars(select(m.BankFlowArtifact).where(
                m.BankFlowArtifact.kind == KIND, m.BankFlowArtifact.account_id == owner(db))
                .order_by(m.BankFlowArtifact.id.desc()).limit(1)).first()
            return jsonify(ok=True, id=record.id if record else None)

    @app.route("/bank/flow/why-discover/<int:scan_id>")
    @gate
    @endpoint
    def bank_why_discover_status(scan_id):
        with SessionFactory() as db:
            return jsonify(ok=True, id=scan_id, **_public(_read(scan(db, scan_id))))

    @app.route("/bank/flow/why-discover/<int:scan_id>/proposals/<int:proposal_id>/<action>", methods=["POST"])
    @gate
    @endpoint
    def bank_why_proposal(scan_id, proposal_id, action):
        require_csrf()
        if action not in ("approve", "reject", "discuss"):
            raise ValueError("Unknown action.")
        body = request.get_json(silent=True) or request.form
        if action == "discuss":
            consent()
            message = " ".join(str(body.get("message") or "").split())[:1000]
            if not message:
                raise ValueError("Write what should change in this proposal.")
            with SessionFactory() as db:
                data = _read(scan(db, scan_id))
                revised = why_patterns.revise(db, proposal_of(data, proposal_id), message, bank_chatgpt.generate_json)
            with SessionFactory() as db:
                record = scan(db, scan_id)
                data = _read(record)
                data["proposals"] = [revised if p["id"] == proposal_id else p for p in data["proposals"]]
                _write(record, data)
                db.commit()
            return jsonify(ok=True, proposal=revised)
        with SessionFactory() as db:
            safety.lock_writes(db)
            record = scan(db, scan_id)
            data = _read(record)
            proposal = proposal_of(data, proposal_id)
            if action == "approve":
                if body.get("confirm") not in (True, "yes"):
                    raise ValueError("Confirm the approval after reading what it changes.")
                rule = why_patterns.approve(db, proposal, account_id=owner(db))
                proposal.update(status="APPROVED", rule_id=rule.id)
            else:
                proposal.update(status="REJECTED", note=" ".join(str(body.get("note") or "").split())[:500])
            _write(record, data)
            db.commit()
        if action == "approve":
            _start_engine_run()
        return jsonify(ok=True, proposal=proposal)

    @app.route("/bank/flow/why-rules")
    @gate
    @endpoint
    def bank_why_rules():
        with SessionFactory() as db:
            return jsonify(ok=True, rules=why_rules(db))

    @app.route("/bank/flow/why-rules/<int:rule_id>/<action>", methods=["POST"])
    @gate
    @endpoint
    def bank_why_rule_state(rule_id, action):
        require_csrf()
        if action not in ("activate", "deactivate"):
            raise ValueError("Unknown action.")
        with SessionFactory() as db:
            safety.lock_writes(db)
            why_patterns.set_active(db, rule_id, action == "activate")
            db.commit()
        _start_engine_run()
        return jsonify(ok=True)
