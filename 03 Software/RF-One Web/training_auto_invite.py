"""Selection releases a Hired candidate to Training (step 1 of the approved sequence).

Selection calls this server to server right after it saves a HIRED decision (unchanged caller,
`Selection/workspace/training_invite.py`). The request is signed with a key derived from the
RFONE_FLASK_SECRET_KEY that every RF-One app already shares.

Approved sequence (Product Owner, 2026-11-21): the release only puts the candidate in charge of a
Training operator (`enrollment.release`, event `training.released`). It does NOT register a Student,
send an invitation or create anything in Clover. The operator then confirms the arrival on
Training -> Students -> Invite student ("Released by Selection: confirm arrival"); only that confirmation registers the
Student and starts the enrollment.

The operator is chosen as before: the person who recorded Hired if they are a Training trainer,
otherwise the position's manager, the RF-One owner, an administrator, or any active trainer.
One release per candidate: a second call answers 'already'.
"""
import hashlib
import hmac
import json
import os
import time

from flask import jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m
from rfone_data_store.training import enrollment as enroll
import training_integration as integration

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
    first = [hirer]
    if position and position.manager_account_id:
        first.append(db.get(m.RFOneAccount, position.manager_account_id))
    return default_trainer(db, first)


def default_trainer(db, first=()):
    """The first current Training trainer among `first`, then the RF-One owner, an
    administrator, then any active trainer."""
    candidates = list(first)
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
            source = {r['id']: r for r in enroll.confirmed_candidates(db, hirer)}.get(selection_id)
            if not source:
                return jsonify(status='skipped', message='Not currently Hired, or not a position you manage.'), 409
            # One active invitation per person (Registry ID): the Trainer resends it, Selection never adds one.
            person_id = source.get('person_id')
            card = enroll._card_id(db, person_id) if person_id else None
            if person_id and enroll.active_invitations(db, person_id=person_id, employee_id=card):
                return jsonify(status='already', message='This person already has an active Training invitation. '
                               + enroll.RESEND_HINT)
            operator = _issuer(db, hirer, selection_id)
            if not operator:
                return jsonify(status='skipped', message='No Training trainer can take charge of this candidate. '
                               'Ask an administrator to set up a Training trainer.'), 422
            try:
                status = enroll.release(db, selection_id=selection_id, released_by=hirer, operator=operator)
                db.commit()
            except (ValueError, IntegrityError) as exc:
                db.rollback()
                message = str(exc) if isinstance(exc, ValueError) else 'Another session updated this candidate.'
                return jsonify(status='skipped', message=message), 409
            name = operator.display_name or operator.username
        if status == 'already':
            return jsonify(status='already', message='Already released to Training.')
        return jsonify(status='released', message=f'Released to Training: {name} will confirm the arrival. '
                       'No enrollment or Clover record is created before that.')
