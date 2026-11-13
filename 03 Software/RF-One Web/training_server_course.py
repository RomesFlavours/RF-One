"""The Server Course (the AI course) joined to RF-One Training, 13 November 2026.

The course keeps its own records (units, tests, practical checks, time); nothing
is copied or moved, so nothing can be lost. Training gives it the person:

- GET  /training/courses/server   A signed-in Training user opens their own course.
  For a student, Visual Menu is assigned first if it isn't already, so they
  see it in Training too. Then Training sends them to the course with a code
  signed by Training's own key (two minutes, the key never leaves Training).
- POST /training/courses/server/verify   The course checks that code with
  Training and gets back the account and its verified email.
- POST /training/courses/server/invite   A hire on their course link asked for
  their Training account. Training reads the email back from the course's
  fixed address (never from the request) and sends its normal invitation,
  the same one as Students -> Invite student, issued by a current trainer.

No shared secret, no new setting: RFONE_SERVER_COURSE_URL only overrides the
course's address.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, redirect, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m, student_registry as registry
from rfone_data_store import rfone_web_session as shared
from rfone_data_store.training import enrollment as enroll, service
from rfone_data_store.technical import account_email
import training_integration as integration
from training_account_routes import public_base
from training_auto_invite import default_trainer

COURSE_URL = (os.environ.get('RFONE_SERVER_COURSE_URL') or 'https://grjswwm9u4.us-east-1.awsapprunner.com').rstrip('/')
CONTEXT = b'rfone-server-course-handoff-v1'
CODE_SECONDS = 120
NEED_TEXT = 'Server training'
INVITE_CODE = re.compile(r'^[a-f0-9]{20}\.[A-Za-z0-9_-]{32}$')


def _key(secret):
    return hmac.new(secret.encode() if isinstance(secret, str) else secret, CONTEXT, hashlib.sha256).digest()


def make_code(secret, payload):
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    return body + '.' + hmac.new(_key(secret), body.encode(), hashlib.sha256).hexdigest()


def read_code(secret, code):
    try:
        body, sig = code.rsplit('.', 1)
    except (AttributeError, ValueError):
        return None
    if not hmac.compare_digest(sig, hmac.new(_key(secret), body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    except ValueError:
        return None
    if not isinstance(data, dict) or abs(time.time() - int(data.get('t', 0))) > CODE_SECONDS:
        return None
    return data


def ensure_visual_menu(db, student_training_id):
    """Assign Visual Menu to a student who doesn't have it yet. Returns True if assigned now."""
    pill = db.scalar(select(m.TrainingPill).where(m.TrainingPill.slug == 'visual-menu'))
    if pill is None:
        return False
    have = db.scalar(select(m.TrainingAssignment.id)
        .join(m.TrainingNeed, m.TrainingNeed.id == m.TrainingAssignment.need_id)
        .where(m.TrainingNeed.student_account_id == student_training_id, m.TrainingAssignment.pill_id == pill.id)
        .limit(1))
    if have:
        return False
    trainer = default_trainer(db)
    if trainer is None:
        return False
    by = integration.check_training_authorization(db, trainer).training_account.id
    need = db.scalar(select(m.TrainingNeed).where(m.TrainingNeed.student_account_id == student_training_id,
                                                  m.TrainingNeed.text == NEED_TEXT))
    if need is None:
        need = service.create_need(db, student_account_id=student_training_id, text=NEED_TEXT, origin=None,
                                   created_by_account_id=by)
    try:
        service.assign_pill(db, need_id=need.id, pill_id=pill.id, assigned_by_account_id=by)
    except ValueError:
        return False
    return True


def _course_invite_email(code):
    """The email the course has on file for this invitation code, read from its fixed address."""
    url = COURSE_URL + '/api/training-link/' + urllib.parse.quote(code, safe='')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='GET'), timeout=15) as resp:
            data = json.loads(resp.read() or b'{}')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    email = str(data.get('email') or '').strip().lower()
    return email or None


def install(app, *, SessionFactory, auth):
    def secret():
        return app.secret_key

    @app.get('/training/courses/server')
    def tw_server_course():
        with SessionFactory() as db:
            account = auth.load_current_account(db)
            if account is None:
                return redirect(url_for('tw_login'))
            result = integration.check_training_authorization(db, account)
            if result.training_account is None:
                return redirect(url_for('tw_login'))
            if result.training_account.role == 'student':
                if ensure_visual_menu(db, result.training_account.id):
                    db.commit()
            code = make_code(secret(), dict(a=account.id, e=(account.email or '').lower(),
                                            n=shared.account_display_name(account), t=int(time.time())))
        response = redirect(COURSE_URL + '/rf?' + urllib.parse.urlencode({'code': code}))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.post('/training/courses/server/verify')
    def tw_server_course_verify():
        data = read_code(secret(), str((request.get_json(silent=True) or {}).get('code') or ''))
        if not data:
            return jsonify(error='Invalid or expired code.'), 403
        with SessionFactory() as db:
            account = db.get(m.RFOneAccount, int(data['a']))
            if account is None or account.status != 'ACTIVE':
                return jsonify(error='Account not active.'), 403
            if integration.check_training_authorization(db, account).training_account is None:
                return jsonify(error='No Training access.'), 403
            return jsonify(account_id=account.id, email=(account.email or '').lower(),
                           name=shared.account_display_name(account))

    @app.post('/training/courses/server/invite')
    def tw_server_course_invite():
        code = str((request.get_json(silent=True) or {}).get('code') or '')
        if not INVITE_CODE.fullmatch(code):
            return jsonify(status='refused', message='Invalid request.'), 400
        email = _course_invite_email(code)
        if not email:
            return jsonify(status='refused', message='The course did not confirm this request.'), 403
        with SessionFactory() as db:
            trainer = default_trainer(db)
            if trainer is None:
                return jsonify(status='skipped', message='There is no active trainer to send the invitation yet. Ask your manager.'), 422
            try:
                invitation, token = enroll.issue(db, actor=trainer, email=email)
                link = public_base() + url_for('tw_enrollment_link', token=token)
                db.commit()
            except registry.ConfirmationRequired:
                db.rollback()
                return jsonify(status='skipped', message='This email is already in RF-One, so your manager needs to send '
                               'your invitation from Training. Your course keeps working as it is.'), 409
            except (ValueError, IntegrityError) as exc:
                db.rollback()
                return jsonify(status='skipped', message=str(exc) if isinstance(exc, ValueError) else 'Try again in a minute.'), 409
        try:
            account_email.send_email(to_address=email, subject='RF-One Training: complete your activation',
                text_body=f'Complete your details and activate Training: {link}\n'
                          'The link is personal, valid for 48 hours and works once.\n')
        except account_email.EmailSendError:
            return jsonify(status='created', message='The email could not be sent. Try again in a minute.'), 502
        return jsonify(status='sent')
