"""C-Bank Prototype local web app (127.0.0.1 only).

One page: runs, exception dashboard grouped by type and WHO (decisions 17, 18),
full movement list, and the assisted modal with structured fields plus free AI
conversation (decision 33). Writes go only to the experimental store.
"""
from __future__ import annotations

import secrets
from collections import Counter, defaultdict
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request, send_file
import io

from . import ai, config, engine as engine_mod, export, legacy, prior, sample, service, store

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo(config.DISPLAY_TZ)
except Exception:  # tzdata missing on this PC: fall back to the PC's local time
    _TZ = None


def local_time(value: str | None) -> str:
    if not value:
        return ""
    dt = datetime.fromisoformat(value)
    dt = dt.astimezone(_TZ) if _TZ else dt.astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def create_app(con=None) -> Flask:
    app = Flask(__name__)
    app.config["CON"] = con or store.connect()
    token = secrets.token_urlsafe(24)

    def db():
        return app.config["CON"]

    def check():
        if request.headers.get("X-CBank-Token") != token:
            abort(403)

    @app.template_filter("money")
    def money(v):
        return f"{v / 100:,.2f}"

    def filters(args) -> dict:
        return dict(status=args.get("status", ""), case=args.get("case", ""), exc=args.get("exc", ""),
                    cmp=args.get("cmp", ""), q=args.get("q", "").strip(), group=args.get("group", ""))

    def apply_filters(results, f):
        return [r for r in results
                if (not f["status"] or r["status"] == f["status"])
                and (not f["case"] or f["case"] in r.get("cases", []))
                and (not f["exc"] or any(e["code"] == f["exc"] for e in r["exceptions"]))
                and (not f["cmp"] or (r["comparison"] or "").startswith(f["cmp"]))
                and (not f["group"] or (r["group_key"] or "—") == f["group"])
                and (not f["q"] or f["q"].lower() in (r["description"] + " " + (r["who_name"] or "")).lower())]

    @app.route("/")
    def index():
        runs = store.runs(db())
        run_id = request.args.get("run", type=int) or (runs[0]["id"] if runs else None)
        run = store.run(db(), run_id) if run_id else None
        results = store.results(db(), run_id) if run else []
        f = filters(request.args)
        groups = defaultdict(list)
        for r in results:
            for e in r["exceptions"]:
                groups[(e["code"], r["group_key"] or "—")].append(r["txn_id"])
        dashboard = sorted(((code, key, ids) for (code, key), ids in groups.items()), key=lambda g: (-len(g[2]), g[0]))
        codes = Counter(e["code"] for r in results for e in r["exceptions"])
        return render_template("index.html", runs=runs, run=run, total=len(results),
                               dashboard=dashboard[:40], codes=codes, f=f, cases=sample.CASES, token=token,
                               local_time=local_time, months=[f"2026-{m:02d}" for m in range(1, 11)],
                               bank_url=f"http://127.0.0.1:5080/bank")

    @app.post("/api/runs")
    def create_run():
        check()
        run_id = service.execute(db(), request.form.get("kind", "sample"), request.form.get("month"))
        return jsonify(ok=True, run_id=run_id)

    @app.get("/api/runs/<int:run_id>/results")
    def run_results(run_id):
        """Read-only list for the transactions modal (same filters as before)."""
        rows = apply_filters(store.results(db(), run_id), filters(request.args))
        keep = ("txn_id", "date", "description", "cases", "amount_minor", "payer", "source", "who_name", "who_method",
                "beneficiary", "beneficiary_method", "why", "why_method", "category", "qb_account", "operation_type",
                "status", "protected", "exceptions", "comparison", "group_key")
        return jsonify(ok=True, rows=[{k: r.get(k) for k in keep} for r in rows])

    def _priors(run_id, rows):
        c = legacy.Catalog.load(legacy.session())
        return c, prior.recover(c.db, c, rows, store.human_decisions(db()))

    @app.get("/api/runs/<int:run_id>/prior")
    def prior_groups(run_id):
        """Decision 59: previous Bank classifications of the filtered open movements (read-only)."""
        rows = apply_filters(store.results(db(), run_id), filters(request.args))
        _, priors = _priors(run_id, rows)
        return jsonify(ok=True, priors={str(k): v for k, v in priors.items()}, groups=prior.groups(priors),
                       **_catalog_lists())

    @app.post("/api/runs/<int:run_id>/prior/approve")
    def prior_approve(run_id):
        check()
        ids = [int(x) for x in request.form.get("txn_ids", "").split(",") if x.strip().isdigit()]
        if not ids:
            return jsonify(ok=False, error="Select at least one movement."), 400
        corrections = {k: request.form.get(k, type=int) for k in ("beneficiary_id", "why_id", "category_id")}
        all_rows = store.results(db(), run_id)
        c, priors = _priors(run_id, [r for r in all_rows if r["txn_id"] in ids])
        try:
            outcome = prior.approve(db(), run_id, ids, priors=priors, results={r["txn_id"]: r for r in all_rows},
                                    corrections=corrections, catalog=c)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        saved_ids = {s["id"] for s in outcome["saved"]}
        changed = service.reevaluate(db(), run_id, saved_ids) if saved_ids else 0
        updated = [{k: r.get(k) for k in ("txn_id", "description", "status", "who_name", "why", "category",
                                           "beneficiary", "protected")}
                   for r in store.results(db(), run_id) if r["txn_id"] in saved_ids]
        return jsonify(ok=True, reevaluated_changed=changed, summary=store.run(db(), run_id)["summary"],
                       updated=updated, **outcome)

    def find(run_id, txn_id):
        for r in store.results(db(), run_id):
            if r["txn_id"] == txn_id:
                return r
        abort(404)

    @app.get("/api/runs/<int:run_id>/txn/<int:txn_id>")
    def txn(run_id, txn_id):
        r = find(run_id, txn_id)
        cat = _catalog_lists()
        return jsonify(ok=True, result=r, messages=store.messages(db(), txn_id),
                       history=store.decision_history(db(), txn_id), **cat)

    _cache = {}

    def _catalog_lists():
        if "c" not in _cache:
            c = legacy.Catalog.load(legacy.session())
            legal = {le.id: le.legal_name for le in c.db.query(legacy.m.LegalEntity)}
            _cache["c"] = dict(
                entities=[dict(id=e.id, name=e.name, legal_name=legal.get(e.legal_entity_id))
                          for e in c.entities.values() if e.status == "ACTIVE"],
                whys=sorted([dict(id=r.id, name=r.name, category_id=r.accounting_classification_id)
                             for r in c.whys.values()], key=lambda x: x["name"]),
                categories=sorted([dict(id=a.id, label=f"{a.code} {a.name}") for a in c.classes.values()
                                   if a.active and (a.node_type or "").startswith("POSTING")], key=lambda x: x["label"]),
                whos=sorted(c.whos.values()))
        return _cache["c"]

    @app.post("/api/runs/<int:run_id>/txn/<int:txn_id>/decision")
    def decide(run_id, txn_id):
        check()
        find(run_id, txn_id)
        form = request.form
        who = (form.get("who") or "").strip().upper() or None
        why_id = form.get("why_id", type=int)
        if not who or not why_id:
            return jsonify(ok=False, error="WHO and WHY are required for a human decision."), 400
        store.save_human_decision(db(), txn_id, who_name=who, beneficiary_id=form.get("beneficiary_id", type=int),
                                  why_id=why_id, category_id=form.get("category_id", type=int),
                                  note=(form.get("note") or "").strip() or None)
        changed = service.reevaluate(db(), run_id, {txn_id})
        return jsonify(ok=True, result=find(run_id, txn_id), reevaluated_changed=changed)

    @app.post("/api/runs/<int:run_id>/txn/<int:txn_id>/chat")
    def chat(run_id, txn_id):
        check()
        r = find(run_id, txn_id)
        text = (request.form.get("text") or "").strip()
        if not text:
            return jsonify(ok=False, error="Write a message."), 400
        try:
            answer = ai.converse(service.new_engine(db()), db(), r, text)
        except Exception as exc:
            return jsonify(ok=False, error=f"OpenAI (ChatGPT) unavailable: {exc}. Nothing was changed."), 503
        return jsonify(ok=True, answer=answer, messages=store.messages(db(), txn_id))

    @app.post("/api/runs/<int:run_id>/investigate")
    def investigate(run_id):
        check()
        ids = {int(x) for x in request.form.get("txn_ids", "").split(",") if x.strip().isdigit()}
        rows = [r for r in store.results(db(), run_id) if r["txn_id"] in ids and r["status"] != engine_mod.RECONCILED]
        if not rows:
            return jsonify(ok=False, error="No open movement in this group."), 400
        try:
            answer = ai.investigate(service.new_engine(db()), db(), rows)
        except Exception as exc:
            return jsonify(ok=False, error=f"OpenAI (ChatGPT) unavailable: {exc}. Nothing was changed."), 503
        changed = service.reevaluate(db(), run_id)
        return jsonify(ok=True, answer=answer, reevaluated_changed=changed)

    @app.get("/export/<int:run_id>.zip")
    def export_run(run_id):
        run = store.run(db(), run_id) or abort(404)
        c = legacy.Catalog.load(legacy.session())
        label = f"run{run_id}"
        data = export.build_zip(store.results(db(), run_id), c.entities, label)
        config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        (config.EXPORT_DIR / f"CBank_EXPERIMENTAL_{label}.zip").write_bytes(data)
        return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                         download_name=f"CBank_EXPERIMENTAL_{label}.zip")

    return app
