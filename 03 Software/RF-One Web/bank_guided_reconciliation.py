"""Guided Reconciliation inside the Bank application (Bank unification, Phase 1).

The C-Bank Dashboard and Guided Reconciliation Wizard are served by THIS
Bank application, under `/bank/reconcile/`, behind the same Bank gate as
every other Bank page — no second server is needed. Nothing is copied:
the one C-Bank application (its pages, API, engine and store, in the C-Bank
worktree) is mounted as it is, and each request under the prefix is handed
to it unchanged except for its base path.

Phase 1 limits (Product Owner, 2026-10-24): one Bank interface, not yet one
engine. C-Bank keeps its own store and reads the operational Bank database
read-only (`cbank/legacy.py`); its engine, AI and the Bank engine are not
changed here.

Active only when the process asks for it (`RFONE_BANK_GUIDED=1`, set by the
local environment's "Avvia Bank") and the C-Bank code is present; otherwise
nothing is registered and the Bank is exactly as before. Rollback: start
with `RFONE_BANK_GUIDED=0` (or the previous commit) — the standalone C-Bank
on 5090 still works as before.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

PREFIX = "/bank/reconcile"
ENDPOINT = "bank_guided"

_DEFAULT_ROOT = (Path(__file__).resolve().parents[3] / "rf-one-c-bank-prototype"
                 / "03 Software" / "C-Bank Prototype")


def cbank_root() -> Path:
    return Path(os.environ.get("RFONE_BANK_CBANK_ROOT") or _DEFAULT_ROOT)


def available() -> bool:
    """Whether this process mounts Guided Reconciliation (and shows its tab)."""
    return os.environ.get("RFONE_BANK_GUIDED") == "1" and (cbank_root() / "cbank" / "web.py").is_file()


_lock = threading.Lock()
_cbank = {}


def _cbank_app():
    """The one C-Bank application, created on first use (its store opens only then)."""
    with _lock:
        if "app" not in _cbank:
            root = str(cbank_root())
            if root not in sys.path:
                sys.path.insert(0, root)
            from cbank.web import create_app
            _cbank["app"] = create_app()
        return _cbank["app"]


def start_auto_runs() -> None:
    """C-Bank's own watcher (a full run after a new Bank import), as the 5090 server ran it."""
    if not available() or os.environ.get("CBANK_AUTO_RUN", "1") == "0":
        return
    try:
        con = _cbank_app().config["CON"]   # first: it puts the C-Bank code on the path
        from cbank import service
        service.start_auto_runs(con)
    except Exception as exc:  # noqa: BLE001 — Guided Reconciliation must never stop the Bank
        print(f"Guided Reconciliation: automatic runs not started: {exc}", flush=True)


def run_after_import() -> None:
    """Phase 3A: right after a CSV import, the single engine processes the Bank in the background (new
    movements, transfers and card payments, WHO rules, labels, profiles, approved WHO -> WHY, WHY/WHAT,
    exceptions for the Guided Wizard). Idempotent: a run starts only when the imported data changed, and
    runs never overlap (`service.run_if_bank_changed`). Never raises into the import."""
    if not available():
        return

    def work():
        try:
            con = _cbank_app().config["CON"]   # first: it puts the engine code on the path
            from cbank import service
            run_id = service.run_if_bank_changed(con)
            if run_id:
                print(f"Single engine: run #{run_id} after the import.", flush=True)
        except Exception as exc:  # noqa: BLE001 — the import is already committed; the watcher retries
            print(f"Single engine: run after the import not completed: {exc}", flush=True)

    threading.Thread(target=work, daemon=True, name="bank-engine-after-import").start()


def register(app, *, require_domain_access) -> None:
    if not available():
        return
    from flask import render_template, request, url_for
    from werkzeug.wrappers import Response

    @app.route(PREFIX + "/", defaults={"sub": ""}, methods=["GET", "POST"], endpoint=ENDPOINT)
    @app.route(PREFIX + "/<path:sub>", methods=["GET", "POST"], endpoint=ENDPOINT)
    @require_domain_access("BANK")
    def guided(sub):
        environ = dict(request.environ)
        environ["SCRIPT_NAME"] = PREFIX
        environ["PATH_INFO"] = "/" + sub
        if request.method == "GET" and not sub:
            # The page only: the Bank shell (header, local environment, breadcrumb and Bank tabs) around the C-Bank page.
            environ["rfone.bank_shell"] = {
                "css": url_for("static", filename="css/rf-one.css") + "?v=29",
                "header": render_template("bank_guided_shell.html"),
            }
        return Response.from_app(_cbank_app().wsgi_app, environ, buffered=True)
