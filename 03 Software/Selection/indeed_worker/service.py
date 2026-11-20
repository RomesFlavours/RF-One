"""One AWS container: headed Chromium + authenticated noVNC + durable jobs.

Run exactly one process/replica. Public ingress requires TLS; VNC is loopback
only. RF-One API authentication and browser tickets are separate capabilities.
"""
import os
import secrets
import socket
import threading
import time
import uuid
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlsplit

from flask import Flask, abort, make_response, redirect, request, send_from_directory
from itsdangerous import BadSignature, URLSafeTimedSerializer

from indeed_protocol import call, list_url, service_url
from .store import ACTIVE, Store


def create_app(*, store=None, launch=True, vnc_address=None):
    app = Flask(__name__)
    key = os.environ['RFONE_INDEED_KEY']
    if len(key) < 32:
        raise ValueError('RFONE_INDEED_KEY requires at least 32 random characters.')
    public = service_url(os.environ['RFONE_INDEED_PUBLIC_URL'])
    if urlsplit(public).path:
        raise ValueError('Browser public URL must use a dedicated hostname root.')
    selection = service_url(os.environ['RFONE_INDEED_SELECTION_URL'])
    ledger = store or Store(os.getenv('RFONE_INDEED_STATE', '/data/indeed.sqlite'))
    signer = URLSafeTimedSerializer(key, salt='indeed-remote-browser')
    lock = threading.RLock()
    threads = {}

    def viewer_job():
        try:
            ticket = signer.loads(request.cookies.get('indeed_viewer', ''), max_age=1800)
            job = ledger.get(ticket['id'])
            if ticket['generation'] != job['generation'] or job['state'] != 'WAITING_LOGIN':
                abort(403)
            return job
        except (BadSignature, KeyError):
            abort(403)

    @app.before_request
    def protect():
        if request.path.startswith('/api/'):
            if not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + key):
                abort(401)
        elif request.path not in ('/open', '/health'):
            viewer_job()

    @app.after_request
    def private(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.errorhandler(KeyError)
    def missing(error):
        return {'error': 'Unknown request'}, 404

    @app.errorhandler(ValueError)
    def invalid(error):
        return {'error': str(error)}, 409

    def upload(job, candidate, filename, content):
        from werkzeug.utils import secure_filename
        return call(selection, key, f'/internal/indeed/{job["id"]}/{candidate}', raw=content,
                    headers={'X-Resume-Filename': secure_filename(filename)})

    def run(job_id):
        from playwright.sync_api import sync_playwright
        from .runner import LoginRequired, collect
        deadline = time.monotonic() + 1800

        def keep_running():
            state = ledger.get(job_id)['state']
            if state == 'STOPPING':
                raise InterruptedError('Stopped by operator.')
            if time.monotonic() > deadline:
                raise InterruptedError('Browser expired; reopen browser and sign in again.')

        try:
            with TemporaryDirectory(prefix='indeed-') as directory, sync_playwright() as pw:
                # The interactive browser must not inherit machine/API secrets.
                # The Linux image also runs it under a different OS uid from
                # this service, so file:// cannot read the service's /proc env
                # or the durable ledger.
                browser_env = {name: os.environ[name] for name in
                               ('DISPLAY', 'HOME', 'PATH', 'LANG', 'TMPDIR') if name in os.environ}
                browser_env['RFONE_CHROMIUM_BINARY'] = pw.chromium.executable_path
                browser = pw.chromium.launch(headless=False,
                    executable_path=os.getenv('RFONE_INDEED_BROWSER_LAUNCHER') or None,
                    env=browser_env, args=['--disable-dev-shm-usage'])
                try:
                    context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 900})
                    page = context.new_page()
                    page.goto(ledger.get(job_id)['url'], wait_until='domcontentloaded')
                    if ledger.get(job_id)['state'] != 'STOPPING':
                        ledger.update(job_id, state='WAITING_LOGIN', message='Complete login/SMS in the browser, then start/resume.')
                    while True:
                        keep_running()
                        if ledger.get(job_id)['state'] != 'RUNNING':
                            time.sleep(.5)
                            continue
                        try:
                            result = collect(page, ledger.get(job_id), ledger, upload, directory, keep_running)
                        except LoginRequired:
                            ledger.update(job_id, state='WAITING_LOGIN', message='Indeed needs your verification. Complete it, then resume.')
                            continue
                        except InterruptedError:
                            raise
                        except Exception:
                            ledger.update(job_id, state='WAITING_LOGIN', message='List not recognized or interrupted. Check the browser and resume.')
                            continue
                        # Close the browser before freeing its single-user slot.
                        browser.close()
                        ledger.update(job_id, state=result, message='Some candidates failed; resume to retry.' if result == 'PAUSED' else '')
                        return
                finally:
                    browser.close()
        except InterruptedError as error:
            stopped = ledger.get(job_id)['state'] == 'STOPPING'
            ledger.update(job_id, state='STOPPED' if stopped else 'PAUSED', message=str(error))
        except Exception:
            ledger.update(job_id, state='PAUSED', message='Browser unavailable. Reopen it to sign in again.')

    def start_thread(job_id):
        if launch:
            thread = threading.Thread(target=run, args=(job_id,), daemon=True)
            threads[job_id] = thread
            thread.start()

    @app.get('/api/jobs')
    def jobs():
        position_id = request.args.get('position_id', type=int)
        return {'jobs': [j for j in ledger.jobs() if j['position_id'] == position_id][:20]}

    @app.post('/api/jobs')
    def create():
        data = request.get_json()
        url = list_url(data.get('url'))
        position_id, actor_id = int(data['position_id']), int(data['actor_id'])
        if position_id < 1 or actor_id < 1:
            abort(400)
        with lock:
            job = ledger.create(url, position_id, actor_id)
            start_thread(job['id'])
        return job, 201

    @app.get('/api/jobs/<job_id>')
    def get(job_id):
        return ledger.get(job_id)

    @app.post('/api/jobs/<job_id>/resume')
    def resume(job_id):
        with lock:
            job = ledger.get(job_id)
            if job['state'] == 'WAITING_LOGIN':
                ledger.update(job_id, state='RUNNING', message='')
            elif job['state'] in ('PAUSED', 'STOPPED'):
                if any(j['state'] in ACTIVE for j in ledger.jobs()):
                    raise ValueError('Another browser is active.')
                # A thread may be just finishing its cleanup. Never overlap desktops.
                if job_id in threads and threads[job_id].is_alive():
                    raise ValueError('Browser is closing. Try again shortly.')
                ledger.update(job_id, state='STARTING', generation=uuid.uuid4().hex)
                start_thread(job_id)
            else:
                raise ValueError('Request cannot resume in this state.')
        return ledger.get(job_id)

    @app.post('/api/jobs/<job_id>/stop')
    def stop(job_id):
        with lock:
            if ledger.get(job_id)['state'] in ACTIVE:
                ledger.update(job_id, state='STOPPING')
        return ledger.get(job_id)

    @app.post('/api/jobs/<job_id>/browser')
    def browser(job_id):
        job = ledger.get(job_id)
        if job['state'] != 'WAITING_LOGIN':
            raise ValueError('Browser access is available while awaiting human verification.')
        token = signer.dumps({'id': job_id, 'generation': job['generation']})
        return {'url': public + '/open?ticket=' + quote(token)}

    @app.get('/open')
    def open_browser():
        try:
            ticket = signer.loads(request.args.get('ticket', ''), max_age=120)
            job = ledger.get(ticket['id'])
            if job['generation'] != ticket['generation'] or job['state'] != 'WAITING_LOGIN':
                abort(403)
        except (BadSignature, KeyError):
            abort(403)
        response = make_response(redirect('/vnc.html?autoconnect=true&resize=scale&path=websockify'))
        response.set_cookie('indeed_viewer', signer.dumps(ticket), httponly=True,
                            secure=urlsplit(public).scheme == 'https', samesite='Lax', max_age=1800)
        return response

    @app.get('/<path:asset>')
    def assets(asset):
        return send_from_directory(os.getenv('RFONE_NOVNC_DIR', '/usr/share/novnc'), asset)

    from flask_sock import Sock
    from simple_websocket import ConnectionClosed
    from werkzeug.exceptions import HTTPException
    sock = Sock(app)

    @sock.route('/websockify')
    def websocket(ws):
        if request.headers.get('Origin') != public:
            ws.close()
            return
        original = viewer_job()
        tcp = socket.create_connection(vnc_address or ('127.0.0.1', 5900), timeout=5)
        tcp.settimeout(.05)
        try:
            while True:
                # Expiry/stop/new session revoke an already open viewer as well.
                if viewer_job()['generation'] != original['generation']:
                    break
                incoming = ws.receive(timeout=.05)
                if incoming is not None:
                    if not isinstance(incoming, bytes):
                        break
                    tcp.sendall(incoming)
                try:
                    outgoing = tcp.recv(65536)
                    if not outgoing:
                        break
                    ws.send(outgoing)
                except socket.timeout:
                    pass
        except (ConnectionClosed, OSError, HTTPException):
            pass
        finally:
            tcp.close()
            ws.close()

    app.extensions['indeed_store'] = ledger
    return app
