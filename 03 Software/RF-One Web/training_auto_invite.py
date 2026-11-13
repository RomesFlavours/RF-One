"""Automatic Training invitation when Selection records a candidate as Hired.

Selection calls this server to server right after it saves a HIRED decision.
The request is signed with a key derived from the RFONE_FLASK_SECRET_KEY that
every RF-One app already shares, so no new secret or configuration is needed.

The invitation is the same one a trainer creates by hand on Training -> Students
-> Invite student, from the "Selection" source: same enroll.issue(), same
48-hour single-use link, same email text. Nothing else is created; the person,
login and Training access still come into existence only when the recipient
completes activation.

Rules:
- The person who recorded Hired must have Selection rights on that position
  (checked by enroll.issue through confirmed_candidates, unchanged).
- The invitation must be issued by a Training trainer, because activation
  checks the issuer: the person who recorded Hired if they are one, otherwise
  the position's manager, the RF-One owner, an administrator, or any active
  trainer, in that order. No configuration is needed.
- One invitation per hire: if an unexpired pending or a completed invitation
  already exists for that Selection candidate, nothing new is sent.
"""
import hashlib
import hmac
import json
import os
import time

from flask import jsonify, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m
from rfone_data_store.training import enrollment as enroll
from rfone_data_store.technical import account_email
import training_integration as integration
from training_account_routes import public_base

CONTEXT = b'rfone-training-auto-invite-v1'
MAX_SKEW_SECONDS = 300


def signing_key(secret):
    return hmac.new(secret.encode(), CONTEXT, hashlib.sha256).digest()


def sign(secret, body):
    return hmac.new(signing_key(secret), body, hashlib.sha256).hexdigest()


def _is_trainer(db, account):
    if not account or account.status != 'ACTIVE':
        return False
    result = integration.check_training_authorization(db, account)
    return bool(result.training_account and result.training_account.role == 'trainer')


def _issuer(db, hirer, selection_id):
    """The trainer the invitation is issued by, chosen in this order: the person who
    recorded Hired, the position's manager, the RF-One owner, an RF-One administrator,
    then any active trainer. Every candidate is re-checked as a current Training trainer."""
    from rfone_data_store.selection import workspace_models as selection
    pc = db.get(selection.WorkspacePositionCandidate, selection_id)
    position = db.get(selection.WorkspacePosition, pc.position_id) if pc else None
    candidates = [hirer]
    if position and position.manager_account_id:
        candidates.append(db.get(m.RFOneAccount, position.manager_account_id))
    candidates += list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.is_owner.is_(True))))
    candidates += list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.is_admin.is_(True))
                                  .order_by(m.RFOneAccount.id)))
    candidates += list(db.scalars(select(m.RFOneAccount)
        .join(m.RFOneTrainingIdentityLink, m.RFOneTrainingIdentityLink.rfone_account_id == m.RFOneAccount.id)
        .join(m.TrainingAccount, m.TrainingAccount.id == m.RFOneTrainingIdentityLink.training_account_id)
        .where(m.TrainingAccount.role == 'trainer').order_by(m.RFOneAccount.id)))
    for account in candidates:
        if _is_trainer(db, account):
            return account
    return None


def _already_invited(db, selection_id):
    rows = db.scalars(select(enroll.EnrollmentInvitation)
                      .where(enroll.EnrollmentInvitation.selection_id == selection_id)).all()
    stamp = enroll.now()

    def aware(value):
        return value if value.tzinfo else value.replace(tzinfo=stamp.tzinfo)
    return any(r.consumed_at or (not r.revoked_at and aware(r.expires_at) > stamp) for r in rows)


def install(app, *, SessionFactory, secret=None):
    @app.post('/training/manage/enrollment/auto')
    def tw_enrollment_auto():
        key = secret or os.environ.get('RFONE_FLASK_SECRET_KEY') or app.secret_key
        if not key or isinstance(key, bytes):
            return jsonify(status='refused', message='Signing is not configured.'), 503
        body = request.get_data(cache=True)
        sent = request.headers.get('X-RFOne-Signature', '')
        if not sent or not hmac.compare_digest(sent, sign(key, body)):
            return jsonify(status='refused', message='Invalid signature.'), 403
        try:
            data = json.loads(body)
            selection_id, hirer_id, ts = int(data['selection_id']), int(data['actor_id']), int(data['ts'])
        except (ValueError, KeyError, TypeError):
            return jsonify(status='refused', message='Invalid request.'), 400
        if abs(time.time() - ts) > MAX_SKEW_SECONDS:
            return jsonify(status='refused', message='Request expired.'), 403

        with SessionFactory() as db:
            hirer = db.get(m.RFOneAccount, hirer_id)
            if not hirer or hirer.status != 'ACTIVE':
                return jsonify(status='refused', message='The account that recorded Hired is not active.'), 403
            if _already_invited(db, selection_id):
                return jsonify(status='already', message='A Training invitation already exists for this person.')
            source = {r['id']: r for r in enroll.confirmed_candidates(db, hirer)}.get(selection_id)
            if not source:
                return jsonify(status='skipped', message='Not currently Hired, or not a position you manage.'), 409
            if not source['email']:
                return jsonify(status='skipped', message='No email on the application, so no invitation was sent. '
                               'Invite them from Training, Students, Invite student.'), 422
            issuer = _issuer(db, hirer, selection_id)
            if not issuer:
                return jsonify(status='skipped', message='No Training trainer is set to send automatic invitations. '
                               'Invite them from Training, Students, Invite student.'), 422
            try:
                invitation, token = enroll.issue(db, actor=hirer, email=source['email'], selection_id=selection_id)
                invitation.created_by_id = issuer.id
                email = invitation.email
                link = public_base() + url_for('tw_enrollment_link', token=token)
                db.commit()
            except (ValueError, IntegrityError) as exc:
                db.rollback()
                message = str(exc) if isinstance(exc, ValueError) else 'Another session updated this invitation.'
                return jsonify(status='skipped', message=message + ' Invite them from Training, Students, Invite student.'), 409
        try:
            account_email.send_email(to_address=email, subject='RF-One Training: complete your activation',
                text_body=f'Complete your details and activate Training: {link}\n'
                          'The link is personal, valid for 48 hours and works once.\n')
        except account_email.EmailSendError:
            return jsonify(status='created', message='Invitation created but the email could not be sent. '
                           'Create a new one from Training, Students, Invite student after one minute.'), 502
        return jsonify(status='sent', message=f'Training invitation emailed to {email}.')
