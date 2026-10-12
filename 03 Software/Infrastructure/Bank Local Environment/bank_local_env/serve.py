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

from .config import WEB_DIR


def main(port: int) -> None:
    if not os.environ.get("RFONE_DATABASE_URL") or not os.environ.get("RFONE_LOCAL_ENV_PC"):
        sys.exit("Refused: the Bank server is started only by “Avvia Bank” (bank_local_env start).")
    os.environ.setdefault("RFONE_WEB_TEST_SECRET_KEY", "local-working-environment-only")
    sys.path.insert(0, str(WEB_DIR))
    os.chdir(WEB_DIR)

    import app as web_app  # noqa: E402
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

    web_app.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
