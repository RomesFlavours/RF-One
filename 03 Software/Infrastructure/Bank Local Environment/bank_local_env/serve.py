"""The local Bank server process, started ONLY by "Avvia Bank" (`start`),
which has already checked the data, the code, the migrations, the
dependencies and the port, and passes everything through the environment:

  RFONE_DATABASE_URL      the local working database chosen by `start`
  RFONE_LOCAL_ENV_*       what the page header shows (PC, database, code, kind)
  RFONE_BANK_AI_MODE      SESSION (Claude Code session) or PROVIDER
  RFONE_BANK_CLAUDE_CODE_CLI  SESSION only: "auto" — a Preview interprets a new
                          rule through the local Claude Code CLI (BANK_AI_RULES_012)

Local only: when no session exists, a request from this machine
(127.0.0.1 / ::1) is signed in as the local administrator. Product
authentication is not modified; this hook lives only in this process.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import REPO_ROOT, WEB_DIR


def main(port: int) -> None:
    if not os.environ.get("RFONE_DATABASE_URL") or not os.environ.get("RFONE_LOCAL_ENV_PC"):
        sys.exit("Refused: the Bank server is started only by “Avvia Bank” (bank_local_env start).")
    os.environ.setdefault("RFONE_WEB_TEST_SECRET_KEY", "local-working-environment-only")
    _guided_reconciliation_environment()
    sys.path.insert(0, str(WEB_DIR))
    os.chdir(WEB_DIR)

    import app as web_app  # noqa: E402
    import bank_guided_reconciliation  # noqa: E402
    from flask import request, session  # noqa: E402
    from sqlalchemy import select  # noqa: E402

    import auth  # noqa: E402
    from db import SessionFactory  # noqa: E402
    from rfone_data_store import models as m  # noqa: E402

    @web_app.app.before_request
    def _local_autologin():
        if request.remote_addr not in ("127.0.0.1", "::1") or session.get(auth.SESSION_ACCOUNT_KEY):
            return None
        with SessionFactory() as s:
            account = s.scalars(select(m.RFOneAccount).where(m.RFOneAccount.username == "admin")).one_or_none()
            if account is not None and account.status == "ACTIVE":
                auth.log_in(account.id, account.session_version)
        return None

    bank_guided_reconciliation.start_auto_runs()
    web_app.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


def _guided_reconciliation_environment() -> None:
    """Bank unification Phase 1: Guided Reconciliation (C-Bank) served by this
    server, reading THIS profile's database read-only and writing only to its
    own store beside the Bank folder — the work profile keeps the existing
    `RF-One\\C-Bank`, a test copy gets `RF-One\\C-Bank TEST`. Every value can be
    overridden from the environment; `RFONE_BANK_GUIDED=0` starts the Bank as
    before (rollback)."""
    db = Path(os.environ["RFONE_LOCAL_ENV_DB"])
    store = "C-Bank TEST" if os.environ.get("RFONE_LOCAL_ENV_KIND") == "TEST" else "C-Bank"
    os.environ.setdefault("RFONE_BANK_GUIDED", "1")
    os.environ.setdefault("CBANK_BANK_DB", str(db))
    os.environ.setdefault("CBANK_STORE_DIR", str(db.parent.parent / store))
    os.environ.setdefault("CBANK_BANK_CODE_ROOT", str(REPO_ROOT))
    # Approved WHO -> WHY knowledge, as "Avvia C-Bank" ran it (Product Owner, 2026-10-24).
    os.environ.setdefault("CBANK_WHO_WHY", "1")


if __name__ == "__main__":
    main(int(sys.argv[1]))
