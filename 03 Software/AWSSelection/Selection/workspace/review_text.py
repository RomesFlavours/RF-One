"""Local review batches through RF-One's existing AWS SMS transport."""
import json
import os
from sqlalchemy import select, update
from rfone_data_store.selection import workspace_models as ps, candidate_identity_service as identity
from rfone_data_store.technical import sms_text
from . import position_settings


def available():
    return bool(os.environ.get('RFONE_SMS_ORIGINATION_IDENTITY', '').strip())


def settings():
    sender = os.environ.get('RFONE_SMS_ORIGINATION_IDENTITY', '').strip()
    if not sender:
        raise ValueError('Il mittente SMS AWS non è configurato. Configura il mittente registrato prima di inviare Text.')
    return {'origination_identity': sender, 'region_name': os.environ.get('AWS_REGION') or 'us-east-1',
        'profile_name': os.environ.get('RFONE_SMS_AWS_PROFILE') or os.environ.get('AWS_PROFILE') or 'rfone-dev-login'}


def recipient(phone):
    try:
        number = identity.normalize_us_phone(phone)
    except ValueError:
        raise ValueError('Il candidato non ha un numero mobile statunitense valido per Text.') from None
    if not number:
        raise ValueError('Il candidato non ha un numero di telefono per Text.')
    return number


def body(questions):
    text = 'RF-One · Domande sulla candidatura\n\n' + '\n\n'.join(f'{n}. {q}' for n, q in enumerate(questions, 1))
    if len(text) > 1600:
        raise ValueError('Le domande superano i 1600 caratteri consentiti per Text. Riduci il testo oppure scegli Email.')
    return text


def deliver(db, position_id, key, config):
    """Called once, only after SENDING was committed with the approved content."""
    db.expire_all()
    position = db.get(ps.Position, position_id)
    batch = position_settings.context(position)['candidate_text_outbox'][key]
    try:
        message_id = sms_text.send_text(to_number=batch['recipient'], body=batch['body'], **config)
        if not message_id:
            raise RuntimeError('No provider confirmation')
        status, error = 'SENT', None
    except Exception:
        message_id, status, error = None, 'UNKNOWN', 'AWS non ha confermato l’invio. Verifica prima di ripetere; nessun reinvio automatico.'
    # Other candidates/reviews may have changed while AWS was responding.
    # Merge into the latest document, never overwrite concurrent work.
    for _ in range(3):
        db.expire_all()
        position = db.scalar(select(ps.Position).where(ps.Position.id == position_id).with_for_update())
        raw = position.organization_context_json
        context = position_settings.context(position)
        current = context.get('candidate_text_outbox', {}).get(key)
        if current is None or current.get('status') != 'SENDING':
            return current.get('status', 'UNKNOWN') if current else 'UNKNOWN'
        current.update(status=status, provider_message_id=message_id, error=error, completed_at=ps.utcnow().isoformat())
        changed = db.execute(update(ps.Position).where(ps.Position.id == position_id,
            ps.Position.organization_context_json == raw).values(organization_context_json=json.dumps(context, ensure_ascii=False))
            .execution_options(synchronize_session=False))
        if changed.rowcount == 1:
            db.commit()
            return status
        db.rollback()
    return 'UNKNOWN'
