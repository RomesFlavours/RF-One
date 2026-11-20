"""RFBank: the recovered Bank shell with the new chat mounted as Rules.

Local working application. Bank actions use its own database; the separate
chat proposes and simulates without applying assignments.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
SOFTWARE = ROOT / '03 Software'
DATA = Path(os.environ.get('RFBANK_DATA_DIR', str(ROOT))).resolve()
DB = DATA / 'rfone.db'
PORT = int(os.environ.get('RFBANK_PORT', '5111'))
os.environ.update(
    RFONE_DATABASE_URL='sqlite:///' + DB.as_posix(),
    RFONE_WEB_TEST_SECRET_KEY=(DATA / 'chat-secret.key').read_text(encoding='utf-8').strip(),
    RFONE_UI_LANGUAGE='it', RFONE_BANK_GUIDED='1', RFONE_BANK_SINGLE_ENGINE='1',
    CBANK_AUTO_RUN='0', CBANK_BANK_DB=str(DB), CBANK_BANK_CODE_ROOT=str(ROOT),
    CBANK_STORE_DIR=str(DATA / 'C-Bank'), RFONE_BANK_CBANK_ROOT=str(SOFTWARE / 'C-Bank Prototype'),
    RFONE_DOMAIN_DATA='', AWS_EC2_METADATA_DISABLED='true',
    RFONE_LOCAL_ENV_PC=socket.gethostname(), RFONE_LOCAL_ENV_KIND='WORK',
    RFONE_LOCAL_ENV_LABEL='RFBank', RFONE_LOCAL_ENV_DB=str(DB), RFONE_LOCAL_ENV_CODE=str(ROOT),
    # AI Rules text interpretation: the documented local default (LOCAL_ENVIRONMENT.md) — the Claude Code CLI on
    # this PC, never the AWS provider (this shell blocks external network for the server process itself).
    RFONE_BANK_AI_MODE='SESSION', RFONE_BANK_CLAUDE_CODE_CLI='auto',
)

# The recovered shell cannot contact external services. ChatGPT runs in its
# existing separate, tools-disabled CLI process; no AWS transport is used.
_original_connect = socket.socket.connect


def local_connect(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):
        raise OSError('RFBank shell: external network disabled')
    return _original_connect(sock, address)


socket.socket.connect = local_connect
sys.path.insert(0, str(SOFTWARE / 'RF-One Data Store'))
sys.path.insert(0, str(SOFTWARE / 'RF-One Web'))
spec = importlib.util.spec_from_file_location('rfbank_web', SOFTWARE / 'RF-One Web' / 'app.py')
web = importlib.util.module_from_spec(spec)
sys.modules['rfbank_web'] = web
spec.loader.exec_module(web)

from flask import abort, redirect, render_template, request, session
import auth


def active_operator():
    # Preserve an existing operator's actual identity and permissions.
    with sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute("SELECT id,session_version FROM rfone_accounts WHERE status='ACTIVE' AND username IN ('rfone','admin') ORDER BY CASE username WHEN 'rfone' THEN 0 ELSE 1 END LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError('Nessun operatore locale esistente: nessun account è stato creato.')
        return row


OPERATOR = active_operator()
web.app.config.update(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_NAME='rfbank_module')


def local_gate():
    if request.remote_addr not in ('127.0.0.1', '::1') or request.host not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
        abort(403)
    if request.path == '/':
        return redirect('/bank/work')
    if not request.path.startswith(('/bank', '/static/', '/shared-brand/')):
        abort(404)
    if not session.get(auth.SESSION_ACCOUNT_KEY):
        auth.log_in(*OPERATOR)


web.app.before_request_funcs.setdefault(None, []).insert(0, local_gate)


# The former "Regole" chat page was removed (Product Owner, 2026-11-17; archived in parking/rules-page-20261117).
# Regole is now the WHO recognition rules page (/bank/rules); old addresses lead there.
web.app.add_url_rule('/bank/configuration/category-trial', 'bank_category_trial', lambda: redirect('/bank/rules'))
if 'bank_ai_rules' in web.app.view_functions:
    web.app.view_functions['bank_ai_rules'] = lambda: redirect('/bank/rules')
application = web.app


if __name__ == '__main__':
    if '--probe' in sys.argv:
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        client = Client(application, Response)
        paths = ['/bank/work', '/bank/review', '/bank/rules',
            '/bank/who-search-text', '/bank/why-signals', '/bank/configuration', '/bank/how-it-works',
            '/bank/flow/snapshot', '/bank/who-search-text/data', '/bank/why-signals/editor-data']
        results = []
        for path in paths:
            response = client.get(path, base_url=f'http://127.0.0.1:{PORT}', environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
            results.append(dict(path=path, status=response.status_code))
        print(json.dumps(results), flush=True)
        assert all(r['status'] == 200 for r in results)
    else:
        from werkzeug.serving import run_simple
        run_simple('127.0.0.1', PORT, application, use_reloader=False, use_debugger=False, threaded=True)
