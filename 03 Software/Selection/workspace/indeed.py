"""Position-bound Indeed transport; no browser or credentials in the web app."""
import io
import os
import secrets
from urllib.parse import quote

from flask import Blueprint, abort, current_app, flash, redirect, request, url_for
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException

from indeed_protocol import MAX_CV_BYTES, call, list_url, service_url
from . import routes as r

callback_bp = Blueprint('indeed_receiver', __name__)


def configured():
    return bool(os.getenv('RFONE_INDEED_WORKER_URL') and os.getenv('RFONE_INDEED_KEY'))


def worker(path, data=None):
    return call(os.environ['RFONE_INDEED_WORKER_URL'], os.environ['RFONE_INDEED_KEY'], path, data, timeout=5)


def panel(position_id):
    draft = r.flask_session.pop('indeed_url_' + str(position_id), '')
    if not configured():
        return {'enabled': False, 'jobs': [], 'draft': draft}
    try:
        return {'enabled': True, 'jobs': worker(f'/api/jobs?position_id={position_id}')['jobs'], 'draft': draft}
    except Exception:
        return {'enabled': True, 'jobs': [], 'unavailable': True, 'draft': draft}


def _job(job_id, position_id):
    job = worker('/api/jobs/' + quote(job_id, safe=''))
    if job['position_id'] != position_id:
        abort(404)
    return job


def _back(position_id):
    return redirect(url_for('positions.position_detail', position_id=position_id, tab='candidature') + '#indeed')


@r.bp.route('/posizioni/<int:position_id>/indeed', methods=['POST'])
@r.access_required
def indeed_start(db, actor, position_id):
    r._position(db, actor, position_id, edit=True)
    try:
        worker('/api/jobs', {'url': list_url(request.form.get('url')), 'position_id': position_id,
                             'actor_id': actor.id})
    except Exception:
        r.flask_session['indeed_url_' + str(position_id)] = request.form.get('url', '')[:2048]
        flash('Importazione Indeed non avviata: verifica URL e disponibilità del servizio.' if current_app.config.get('RFONE_LOCAL_OPERATOR')
              else 'Indeed import was not started: check the URL and service availability.')
    return _back(position_id)


@r.bp.route('/posizioni/<int:position_id>/indeed/<job_id>/<action>', methods=['POST'])
@r.access_required
def indeed_action(db, actor, position_id, job_id, action):
    r._position(db, actor, position_id, edit=True)
    if action not in ('resume', 'stop', 'browser'):
        abort(404)
    try:
        _job(job_id, position_id)
        result = worker('/api/jobs/' + quote(job_id, safe='') + '/' + action, {})
        if action == 'browser':
            # Worker must return a viewer on its configured public origin.
            from urllib.parse import urlsplit
            target = urlsplit(result['url'])
            expected = urlsplit(service_url(os.environ['RFONE_INDEED_WORKER_URL']))
            if (target.scheme, target.netloc) != (expected.scheme, expected.netloc):
                abort(502)
            return redirect(result['url'])
    except HTTPException:
        raise
    except Exception:
        flash('Servizio Indeed non disponibile o richiesta non più attiva.' if current_app.config.get('RFONE_LOCAL_OPERATOR')
              else 'Indeed service unavailable or request no longer active.')
    return _back(position_id)


@callback_bp.post('/internal/indeed/<job_id>/<candidate_id>')
def receive(job_id, candidate_id):
    key = os.getenv('RFONE_INDEED_KEY', '')
    if not key or not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + key):
        abort(401)
    job = worker('/api/jobs/' + quote(job_id, safe=''))
    if job['state'] != 'RUNNING' or not candidate_id.isalnum() or len(candidate_id) > 64:
        abort(409)
    if request.content_length is None or not 0 < request.content_length <= MAX_CV_BYTES:
        abort(413)
    content = request.stream.read(MAX_CV_BYTES + 1)
    if len(content) > MAX_CV_BYTES:
        abort(413)
    filename = request.headers.get('X-Resume-Filename', '')
    from werkzeug.utils import secure_filename
    filename = secure_filename(filename)
    if not filename.lower().endswith(('.pdf', '.docx', '.txt')):
        abort(415)
    with r._cfg.SessionFactory() as db:
        # Recheck current grants, including revocation after the import began.
        account = db.get(r.m.RFOneAccount, job['actor_id'])
        actor = r.actor_for(db, account)
        if actor is None:
            abort(403)
        position = r._position(db, actor, job['position_id'], edit=True)
        result = r.engine.import_cv(db, documents=r._cfg.documents, restaurant_id=r._restaurant_id(db),
                                    position=position, channel='INDEED', actor_id=actor.id, actor_name=actor.name,
                                    file_storage=FileStorage(stream=io.BytesIO(content), filename=filename))
        return {k: result[k] for k in ('status', 'message', 'position_candidate_id') if k in result}


def install(app):
    app.register_blueprint(callback_bp)
