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
  their Training account. Training reads the email and the training site back
  from the course's fixed address (never from the request) and sends its normal
  invitation, the same one as Students -> Invite student, issued by a current
  trainer. The site is the one the manager chose for that hire in the course
  (Winter Park or Mount Dora), bound to the invitation code; the role is Server.
  No site is ever assumed: a code without a known site is refused
  (REGISTRY_MULTISITE_001, Product Owner 2026-11-22).
  Asking again with the same code and the same email: while that invitation is
  valid and not activated, the link is sent again to the address already on
  the invitation (same invitation, card and site; no second invitation or
  account); once activated, the person is sent to sign in. The code is bound to
  its invitation on the card history (SERVER_COURSE_INVITE).

No shared secret, no new setting: RFONE_SERVER_COURSE_URL only overrides the
course's address.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta, timezone

from flask import jsonify, redirect, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m, student_registry as registry
from rfone_data_store import employee_directory as directory
from rfone_data_store import rfone_web_session as shared
from rfone_data_store.training import enrollment as enroll, service, courses
from rfone_data_store.technical import account_email
import training_integration as integration
from training_account_routes import public_base
from training_auto_invite import default_trainer

COURSE_URL = (os.environ.get('RFONE_SERVER_COURSE_URL') or 'https://grjswwm9u4.us-east-1.awsapprunner.com').rstrip('/')
CONTEXT = b'rfone-server-course-handoff-v1'
CODE_SECONDS = 120
NEED_TEXT = 'Server training'
INVITE_CODE = re.compile(r'^[a-f0-9]{20}\.[A-Za-z0-9_-]{32}$')
# The two training sites the course manager chooses from, and the Registry site each one is.
COURSE_SITES = {'Winter Park': 'WP', 'Mount Dora': 'MD'}
SERVER_ROLE = 'Server'


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


def server_course_pill(db):
    """The Server Course in Training's catalog: the course whose lesson opens this course."""
    host = urllib.parse.urlsplit(COURSE_URL).hostname or ''
    for pill in db.scalars(select(m.TrainingPill).order_by(m.TrainingPill.id)):
        if pill.slug == 'visual-menu':
            continue
        revision = courses.active_revision(db, pill.id)
        lessons = json.loads(revision.content_json).get('lessons', []) if revision else []
        for lesson in lessons:
            url = str(lesson.get('url') or '')
            if url.startswith('/training/courses/server') or (host and urllib.parse.urlsplit(url).hostname == host):
                return pill
    return None


def _assigned(db, student_training_id, pill_id):
    return db.scalar(select(m.TrainingAssignment)
        .join(m.TrainingNeed, m.TrainingNeed.id == m.TrainingAssignment.need_id)
        .where(m.TrainingNeed.student_account_id == student_training_id, m.TrainingAssignment.pill_id == pill_id)
        .limit(1))


def ensure_visual_menu(db, student_training_id):
    """Assign Visual Menu and the Server Course (from Training's catalog) to a student who
    doesn't have them yet, so both are tracked as Training courses. Returns True if anything was assigned."""
    pills = [p for p in (db.scalar(select(m.TrainingPill).where(m.TrainingPill.slug == 'visual-menu')),
                         server_course_pill(db)) if p is not None]
    missing = [p for p in pills if not _assigned(db, student_training_id, p.id)]
    if not missing:
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
    done = False
    for pill in missing:
        try:
            service.assign_pill(db, need_id=need.id, pill_id=pill.id, assigned_by_account_id=by)
            done = True
        except ValueError:
            pass
    return done


def mark_opened(db, student_training_id):
    """Opening the course from Training counts as opening its Training assignment."""
    pill = server_course_pill(db)
    a = _assigned(db, student_training_id, pill.id) if pill else None
    if a is not None and a.first_opened_at is None:
        from datetime import datetime, timezone
        a.first_opened_at = datetime.now(timezone.utc)
        return True
    return False


def own_progress(secret, account):
    """This person's own Server Course progress, or None if unknown."""
    from training_hire_confirm import course_status
    status = course_status(secret, account, [account.id])
    return (status or {}).get(account.id) if status is not None else None


def _course_invite_details(code):
    """(email, site) the course has on file for this invitation code, read from its fixed address.
    `site` is the training site the manager chose for the hire ('' when the course gives none)."""
    url = COURSE_URL + '/api/training-link/' + urllib.parse.quote(code, safe='')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method='GET'), timeout=15) as resp:
            data = json.loads(resp.read() or b'{}')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, ''
    if not isinstance(data, dict):
        return None, ''
    email = str(data.get('email') or '').strip().lower()
    return email or None, str(data.get('site') or '').strip()


def _name_tokens(name):
    return re.findall(r'[a-z0-9]+', str(name or '').casefold())


def course_site(db, label):
    """The Registry site of a course training site: the only site whose name ends with its code (WP / MD)
    or contains its name. None when the label is unknown or the site is missing or not unique."""
    from rfone_data_store import employee_directory as directory
    code = COURSE_SITES.get(label)
    if not code:
        return None
    words = _name_tokens(label)
    found = [site for site in directory.sites(db)
             if (_name_tokens(site.name)[-1:] == [code.casefold()])
             or ' '.join(words) in ' '.join(_name_tokens(site.name))]
    return found[0] if len(found) == 1 else None


def server_role(db, restaurant_id):
    """(role_id, area_id) of the Server role at this site, or None when it is missing or not unique."""
    from rfone_data_store import employee_directory as directory
    from rfone_data_store.technical.connectors.clover.employee_writer import same_name_key
    pairs = [(role.id, area.id) for role, area in directory.site_role_choices(db, restaurant_id)
             if same_name_key(role.name) == same_name_key(SERVER_ROLE)]
    return pairs[0] if len(pairs) == 1 else None


INVITE_ACTION = 'SERVER_COURSE_INVITE'
RESEND_ACTION = 'SERVER_COURSE_RESEND'


def code_digest(code):
    return hashlib.sha256(code.encode()).hexdigest()


def bound_invitation(db, code):
    """(invitation, card_id, site_id) the course code was first used for, or None."""
    wanted = code_digest(code)
    for event in db.scalars(select(m.EmployeeDirectoryEvent).where(m.EmployeeDirectoryEvent.action == INVITE_ACTION)
                            .order_by(m.EmployeeDirectoryEvent.id)):
        details = event.details or {}
        if details.get('code_digest') == wanted:
            invitation = db.get(enroll.EnrollmentInvitation, details.get('invitation_id'))
            return (invitation, event.employee_id, details.get('restaurant_id')) if invitation else None
    return None


def _utc(value):
    """Naive UTC, whatever the database gives back (PostgreSQL keeps the zone, SQLite does not)."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _resend_too_soon(db, invitation_id):
    """The same limits as a new invitation: one per minute, five per hour."""
    stamp = _utc(enroll.now())
    times = [_utc(e.created_at) for e in db.scalars(select(m.EmployeeDirectoryEvent)
             .where(m.EmployeeDirectoryEvent.action == RESEND_ACTION))
             if (e.details or {}).get('invitation_id') == invitation_id]
    return any(x > stamp - timedelta(seconds=60) for x in times) or sum(x > stamp - timedelta(hours=1) for x in times) >= 5


def install(app, *, SessionFactory, auth):
    def secret():
        return app.secret_key

    @app.before_request
    def _assign_before_home():
        """A student's courses exist before their home page lists them (never "No training path assigned")."""
        if request.endpoint != 'training.home':
            return None
        try:
            with SessionFactory() as db:
                account = auth.load_current_account(db)
                if account is None:
                    return None
                result = integration.check_training_authorization(db, account)
                if result.training_account is not None and result.training_account.role == 'student'                         and ensure_visual_menu(db, result.training_account.id):
                    db.commit()
        except Exception:
            app.logger.exception('Training: could not assign the courses before the home page')
        return None

    @app.context_processor
    def _server_course_pill_id():
        def server_course_pill_id():
            try:
                with SessionFactory() as db:
                    pill = server_course_pill(db)
                    return pill.id if pill else None
            except Exception:
                return None
        return dict(server_course_pill_id=server_course_pill_id)

    @app.context_processor
    def _server_course_progress():
        def server_course_progress():
            """For the student home card: units done, read from the course when the page is shown."""
            try:
                with SessionFactory() as db:
                    account = auth.load_current_account(db)
                    if account is None:
                        return None
                    result = integration.check_training_authorization(db, account)
                    if result.training_account is None or result.training_account.role != 'student':
                        return None
                    if ensure_visual_menu(db, result.training_account.id):
                        db.commit()
                    return own_progress(secret(), account) or {}
            except Exception:
                return None
        return dict(server_course_progress=server_course_progress)

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
                changed = ensure_visual_menu(db, result.training_account.id)
                changed = mark_opened(db, result.training_account.id) or changed
                if changed:
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
        email, site_label = _course_invite_details(code)
        if not email:
            return jsonify(status='refused', message='The course did not confirm this request.'), 403
        with SessionFactory() as db:
            trainer = default_trainer(db)
            if trainer is None:
                return jsonify(status='skipped', message='There is no active trainer to send the invitation yet. Ask your manager.'), 422
            # The site comes only from the code the course confirmed; it is never assumed.
            site = course_site(db, site_label)
            if site is None:
                return jsonify(status='skipped', message='Your training site is not set for your course link. '
                               'Ask your manager. Your course keeps working as it is.'), 409
            role = server_role(db, site.id)
            if role is None:
                return jsonify(status='skipped', message=f'The Server role is not set up at {site.name} yet. '
                               'Ask your manager. Your course keeps working as it is.'), 409
            bound = bound_invitation(db, code)
            if bound is not None:
                # The same code again: only its own invitation, for the same email and site, is ever reused.
                invitation, card_id, bound_site = bound
                if invitation.email != email or bound_site != site.id:
                    return jsonify(status='refused', message='This request does not match your invitation. '
                                   'Ask your manager.'), 409
                if invitation.consumed_at:
                    return jsonify(status='activated', login_url=public_base() + url_for('tw_login'),
                                   message='You have already activated your RF-One Training access. Sign in.'), 200
                if invitation.revoked_at or _utc(invitation.expires_at) <= _utc(enroll.now()) \
                        or invitation.failed_attempts >= 5:
                    return jsonify(status='skipped', message='Your invitation is no longer valid, so your manager needs '
                                   'to send a new one from Training. Your course keeps working as it is.'), 409
                if _resend_too_soon(db, invitation.id):
                    return jsonify(status='skipped', message='Wait at least one minute before asking again '
                                   '(up to five per hour).'), 409
                # Same invitation row: a fresh secret replaces the old one (only its digest is ever stored, so the
                # previous link cannot be read back); the newest email is the one that works.
                token = secrets.token_urlsafe(32)
                invitation.token_digest = enroll.digest(token)
                directory._event(db, RESEND_ACTION, employee_id=card_id, account_id=trainer.id,
                                 details={'invitation_id': invitation.id, 'restaurant_id': site.id})
                link = public_base() + url_for('tw_enrollment_link', token=token)
                email = invitation.email
                db.commit()
                return _send_invitation(email, link)
            try:
                invitation, token = enroll.issue(db, actor=trainer, email=email, restaurant_id=site.id,
                                                 role_id=role[0], area_id=role[1])
                card = directory.card_for_person(db, invitation.person_id)
                directory._event(db, INVITE_ACTION, employee_id=card.id if card else None, account_id=trainer.id,
                                 details={'code_digest': code_digest(code), 'invitation_id': invitation.id,
                                          'restaurant_id': site.id})
                link = public_base() + url_for('tw_enrollment_link', token=token)
                db.commit()
            except (registry.ConfirmationRequired, directory.CardConfirmationRequired):
                db.rollback()
                return jsonify(status='skipped', message='This email is already in RF-One, so your manager needs to send '
                               'your invitation from Training. Your course keeps working as it is.'), 409
            except (ValueError, IntegrityError) as exc:
                db.rollback()
                return jsonify(status='skipped', message=str(exc) if isinstance(exc, ValueError) else 'Try again in a minute.'), 409
        return _send_invitation(email, link)

    def _send_invitation(email, link):
        try:
            from training_enrollment_routes import invitation_email
            subject, body = invitation_email('', link)
            account_email.send_email(to_address=email, subject=subject, text_body=body)
        except account_email.EmailSendError:
            return jsonify(status='created', message='The email could not be sent. Try again in a minute.'), 502
        return jsonify(status='sent')
