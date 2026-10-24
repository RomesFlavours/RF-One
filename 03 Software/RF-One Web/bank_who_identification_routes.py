"""RF-One Web — automatic WHO identification after a bank import
(BANK_WHO_IDENTIFICATION_001).

After every successful bank import the movements just imported are identified
(WHO and activity labels) by `rfone_data_store.bank_reconciliation.
who_identification`, in ONE background thread, so two runs never overlap.
AI: OpenAI / ChatGPT only (`bank_chatgpt`), never another provider, and only
when this database's provider consent exists.

The only control is "Resume WHO identification" in Configuration > WHO. The
automatic start can leave movements unprocessed: queuing can fail after an
import (database busy), a run can fail, and a run interrupted by a server stop
stays stopped — the worker only starts on an import. The button resumes
stopped / failed runs, queues the movements that were never identified, and
starts the worker.
"""

import threading

from flask import abort, flash, redirect, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules
from rfone_data_store.bank_reconciliation import who_identification as engine


def _generate(prompt, web_research):
    import bank_chatgpt
    return bank_chatgpt.generate_json(prompt, web_research=web_research)


def _ai_allowed() -> bool:
    from bank_assistant_preview_routes import _provider_context_approved
    return _provider_context_approved()


class WhoWorker:
    """One daemon thread that runs queued runs one after the other."""

    def __init__(self, app, factory):
        self.app, self.factory = app, factory
        self.event, self.lock, self.thread = threading.Event(), threading.Lock(), None
        self.recovered = False

    def wake(self):
        if self.app.testing or self.app.config.get("BANK_WHO_WORKER_ENABLED") is False:
            return
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self._recover()
                self.thread = threading.Thread(target=self._loop, daemon=True, name="bank-who-identification")
                self.thread.start()
        self.event.set()

    def _recover(self):
        if self.recovered:
            return
        with self.factory() as db:
            engine.recover_orphans(db)
            db.commit()
        self.recovered = True

    def drain(self, *, generate=None, ai_allowed=None):
        """Run every queued run now, in this thread (tests and the loop)."""
        while True:
            with self.factory() as db:
                run_id = engine.claim(db)
            if run_id is None:
                return
            with self.factory() as db:
                try:
                    engine.run_once(db, run_id, generate=generate or _generate,
                                    ai_allowed=_ai_allowed() if ai_allowed is None else ai_allowed)
                except Exception:  # noqa: BLE001 — recorded on the run; the next one still runs
                    self.app.logger.exception("Identify WHO run %s failed; saved results kept", run_id)

    def _loop(self):
        with self.app.app_context():
            while True:
                self.event.wait(60)
                self.event.clear()
                try:
                    self.drain()
                except Exception:  # noqa: BLE001
                    self.app.logger.exception("Identify WHO worker paused; runs retained")


def enqueue_new(app, factory, transaction_ids, account_id=None):
    """After a successful import: identify the movements just imported. Never
    raises — an engine problem must not touch the import."""
    import time
    from sqlalchemy.exc import OperationalError
    try:
        ids = [int(i) for i in transaction_ids or []]
        if not ids:
            return
        for attempt in range(6):
            try:
                with factory() as db:
                    engine.enqueue(db, scope="NEW", transaction_ids=ids, account_id=account_id)
                    db.commit()
                break
            except OperationalError:  # the database is briefly busy (the import worker): retry
                if attempt == 5:
                    raise
                time.sleep(0.5 * (attempt + 1))
        worker = app.extensions.get("bank_who_worker")
        if worker:
            worker.wake()
    except Exception:  # noqa: BLE001
        app.logger.exception("Identify WHO could not be queued after the import; the import is unaffected")


def register(app, *, gate, SessionFactory, load_current_account, require_csrf):
    worker = WhoWorker(app, SessionFactory)
    app.extensions["bank_who_worker"] = worker

    @app.route("/bank/who-identification/resume-pending", methods=["POST"])
    @gate
    def bank_who_identification_resume_pending():
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            if account is None:
                abort(403)
            engine.recover_orphans(db)
            resumed = 0
            for run in db.scalars(select(m.BankWhoIdentifyRun).where(
                    m.BankWhoIdentifyRun.status.in_(("STOPPED", "FAILED")))):
                try:
                    engine.resume(db, run.id)
                    resumed += 1
                except ValueError:
                    pass
            done = select(m.BankWhoIdentification.financial_transaction_id)
            missing = list(db.scalars(ai_rules._scope_query().with_only_columns(m.FinancialTransaction.id)
                                      .where(m.FinancialTransaction.id.not_in(done))))
            if missing:
                engine.enqueue(db, scope="NEW", transaction_ids=missing, account_id=account.id)
            queued = db.scalar(select(m.BankWhoIdentifyRun.id).where(
                m.BankWhoIdentifyRun.status == "QUEUED").limit(1))
            db.commit()
        worker.wake()
        if resumed or missing or queued:
            flash(f"WHO identification resumed: {resumed} run(s) resumed, {len(missing)} movement(s) never "
                  "identified queued.", "success")
        else:
            flash("WHO identification: no movements left to process.", "info")
        return redirect(url_for("bank_configuration", _anchor="cp-who"))

    return worker
