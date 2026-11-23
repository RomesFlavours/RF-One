"""Research-scoped human review; AI judgments remain separate and unchanged."""
from copy import deepcopy
import json
import os
from flask import abort, current_app, jsonify, request, url_for, render_template
from sqlalchemy import select, update
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps
from . import conversational_rules as conversation, incremental_rules as inc, position_settings, mail_delivery, review_text
from .routes import bp, access_required, _position, _pc, _cfg
from local_i18n import ui, italian


def default_question(detail):
    """The proposed clarification question in the interface language (Italian locally, English on AWS).
    The rule title and the AI's reason are stored facts and are quoted unchanged."""
    if italian():
        return f"Puoi chiarire questo punto relativo a «{detail['title']}»? {detail.get('reason', '')}"
    return f"Could you clarify this point about “{detail['title']}”? {detail.get('reason', '')}"

PRIORITIES = {'HIGH': 'Alta', 'MEDIUM': 'Media', 'LOW': 'Bassa'}
MODES = ('OPEN', 'ANSWER', 'IGNORE', 'ASK')


def conclusions(result):
    if not result or not result.get('active'):
        return ui('Analisi non disponibile: applica prima le regole ai candidati.')
    sentences = []
    priority = result.get('qualitative_priority')
    if priority:
        sentences.append(ui('Priorità ' + priority.lower() + (' impostata dal selezionatore.' if result.get('manual_priority')
            else ' rispetto alle preferenze della ricerca.')))
    favorable = [d['title'] for d in result.get('details', []) if d.get('ai_outcome') == 'ALTA']
    less_favorable = [d['title'] for d in result.get('details', []) if d.get('ai_outcome') == 'BASSA']
    if favorable:
        sentences.append(ui('Aspetti favorevoli: ') + '; '.join(favorable) + '.')
    if less_favorable:
        sentences.append(ui('Aspetti meno favorevoli: ') + '; '.join(less_favorable) + '.')
    blocked = [d['title'] for d in result.get('details', []) if d.get('ai_outcome') == 'NON_IN_LINEA']
    if blocked:
        sentences.append(ui('Non in linea con i requisiti: ') + '; '.join(blocked) + '.')
    elif any(d.get('section') == 'requirements' and d.get('ai_outcome') == 'IN_LINEA' for d in result.get('details', [])):
        sentences.append(ui('I requisiti valutabili risultano in linea.'))
    pending = [d['title'] for d in result.get('details', []) if d.get('outcome') is None
        and d.get('review_resolution') not in ('ANSWER', 'IGNORE')]
    if pending:
        sentences.append(ui('Prima di completare la valutazione occorre chiarire: ') + '; '.join(pending) + '.')
    elif result.get('reviewed'):
        sentences.append(ui('I punti da chiarire sono stati gestiti dal selezionatore.'))
    if result.get('accepted'):
        sentences.append(ui('Analisi accettata dal selezionatore.'))
    return ' '.join(sentences) or ui('Nessuna conclusione supportata dalle regole valutate.')


def current(db, position, pc):
    run = position_settings.context(position).get('pdl_filter_run') or {}
    result = run.get('results', {}).get(str(pc.id))
    if not result or run.get('role_code') != position.role_code:
        raise ValueError('Applica prima le regole a questo candidato.')
    _, cv_hash = inc.cv_input(db, pc)
    signature = conversation.signature(conversation.active(db, position.role_code))
    if run.get('signature') != signature or (run.get('incremental_version') == 1 and run.get('cv_hashes', {}).get(str(pc.id)) != cv_hash):
        raise ValueError('CV o regole cambiati: applica le regole prima di revisionare l’analisi.')
    anchor = inc.digest({'cv': cv_hash, 'role': position.role_code, 'rules': signature, 'analysis': result})
    return result, cv_hash, anchor


def item_key(detail, cv_hash, role):
    return inc.digest({'cv': cv_hash, 'role': role, 'id': detail['id'], 'instruction': detail.get('condition'),
        'section': detail.get('section'), 'title': detail.get('title'), 'question': detail.get('reason')})


def effective(db, position, pc, result):
    if not result:
        return result
    value = deepcopy(result)
    saved = position_settings.context(position).get('candidate_reviews', {}).get(str(pc.id), {})
    cv_hash = inc.cv_input(db, pc)[1]
    for detail in value.get('details', []):
        entry = saved.get('items', {}).get(str(detail['id']), {})
        if detail.get('outcome') is None and entry.get('key') == item_key(detail, cv_hash, position.role_code):
            detail['review_resolution'] = entry.get('mode')
            detail['review_answer'] = entry.get('answer', '')
    try:
        _, _, anchor = current(db, position, pc)
    except ValueError:
        anchor = None
    if anchor and saved.get('anchor') == anchor:
        if saved.get('priority') in PRIORITIES:
            value['priority'] = conversation.PRIORITIES[saved['priority']]
            value['qualitative_priority'] = PRIORITIES[saved['priority']]
            value['manual_priority'] = True
        value['accepted'] = saved.get('accepted', False)
    value['unknown'] = any(d.get('outcome') is None and d.get('review_resolution') not in ('ANSWER', 'IGNORE') for d in value.get('details', []))
    value['reviewed'] = any(d.get('review_resolution') in ('ANSWER', 'IGNORE') for d in value.get('details', []))
    value['status'] = 'UnFit' if value.get('unfit') else 'Da chiarire' if value['unknown'] else 'Revisionata' if value['reviewed'] else value.get('status', 'In linea')
    value['reason'] = conclusions(value)
    return value


def view(db, position, pc, actor):
    result, cv_hash, anchor = current(db, position, pc)
    saved = position_settings.context(position).get('candidate_reviews', {}).get(str(pc.id), {})
    effective_result = effective(db, position, pc, result)
    candidate = db.get(m.Candidate, pc.candidate_id)
    items = []
    for detail in result.get('details', []):
        if detail.get('outcome') is not None:
            continue
        key = item_key(detail, cv_hash, position.role_code)
        entry = saved.get('items', {}).get(str(detail['id']), {})
        if entry.get('key') != key:
            entry = {}
        items.append({'id': detail['id'], 'title': detail['title'], 'reason': detail.get('reason', ''),
            'mode': entry.get('mode', 'OPEN'), 'answer': entry.get('answer', ''),
            'question': entry.get('question') or default_question(detail)})
    outbox = db.get(mail_delivery.EmailOutbox, saved.get('outbox_id')) if saved.get('outbox_id') else None
    account = db.get(ps.CandidateAccount, pc.candidate_account_id) if pc.candidate_account_id else None
    phone = (account.phone if account and account.phone else pc.declared_phone or (candidate.phone if candidate else None)) or ''
    text_batch = position_settings.context(position).get('candidate_text_outbox', {}).get(saved.get('text_batch'), {})
    return {'name': (candidate.full_name if candidate else None) or pc.declared_name or ui('Candidato'),
        'analysis': conclusions(effective_result), 'items': items,
        'accepted': bool(saved.get('accepted') and saved.get('anchor') == anchor),
        'priority': saved.get('priority', '') if saved.get('anchor') == anchor else '',
        'ai_priority': ui(result.get('qualitative_priority') or 'Da chiarire'),
        'can_edit': actor.can_edit(position), 'email': mail_delivery.email_for(db, pc),
        'phone': phone, 'channel': saved.get('channel', 'EMAIL'), 'custom_questions': saved.get('custom_questions', []),
        'text_available': review_text.available(),
        'reading_url': url_for('positions.candidate_cv_observations', position_id=position.id, pc_id=pc.id),
        'delivery': text_batch.get('status') if saved.get('channel') == 'TEXT' else outbox.status if outbox else None,
        'version': inc.digest({'anchor': anchor, 'saved': saved})}


def local_operator():
    return bool(current_app.config.get('RFONE_LOCAL_OPERATOR')) and request.remote_addr in ('127.0.0.1', '::1')


def candidate_email(questions):
    """What the candidate receives: in English from Rome's Flavours on AWS, as before locally."""
    listed = '\n\n'.join(f'{n}. {q}' for n, q in enumerate(questions, 1))
    if local_operator():
        return ('Chiarimenti sulla candidatura',
                'Buongiorno,\n\nper completare la valutazione della tua candidatura, ti chiediamo:\n\n' + listed + '\n\nGrazie.')
    return ("Rome's Flavours: questions about your application",
            "Hello,\n\nTo finish reviewing your application, we'd like to ask you:\n\n" + listed +
            "\n\nJust reply to this email with your answers.\n\nThank you,\nRome's Flavours")


def smtp_settings():
    """Local: the operator's own SMTP set-up. On AWS: the company mailbox in the RFONE_SMTP_* settings."""
    from rfone_data_store.technical import smtp_email
    if not local_operator():
        try:
            settings = smtp_email.settings_from_environment()
        except Exception:
            settings = None
        if settings is None:
            raise ValueError('Email is not set up for Selection yet. Ask the RF-One administrator.')
        return settings
    from smtp_local_config import apply_to_environment
    try:
        apply_to_environment()
        settings = smtp_email.settings_from_environment()
    except Exception:
        raise ValueError('La configurazione SMTP locale non è utilizzabile. Controlla Configura Email Selection.') from None
    if settings is None:
        raise ValueError('Configura la posta SMTP locale prima di inviare le domande.')
    return settings


@bp.get('/posizioni/<int:position_id>/candidati/<int:pc_id>/sintesi-cv')
@access_required
def candidate_cv_observations(db, actor, position_id, pc_id):
    from . import cv_observations
    position = _position(db, actor, position_id)
    pc = _pc(db, position, pc_id)
    run = position_settings.context(position).get('pdl_filter_run') or {}
    state = run.get('rule_cache', {}).get(str(pc.id), {})
    rules = conversation.snapshot(conversation.active(db, position.role_code))
    summary_context = {'role_code': position.role_code, 'title': position.title,
        'location': position.location_label, 'description': position.description}
    sections = []
    if (state.get('cv_hash') == inc.cv_input(db, pc)[1] and state.get('role_code') == position.role_code
            and cv_observations.valid(state, rules, summary_context)):
        sections = state['cv_observations']['sections']
    return render_template('workspace/_cv_observations.html', sections=sections,
        preparing=run.get('state') == 'RUNNING', has_rules=bool(rules))


def deliver(db, row, settings):
    """Send exactly this approved batch; never claim unrelated queued mail."""
    from rfone_data_store.technical import smtp_email
    result = db.execute(update(mail_delivery.EmailOutbox).where(mail_delivery.EmailOutbox.id == row.id,
        mail_delivery.EmailOutbox.status == 'QUEUED').values(status='SENDING'))
    db.commit()
    if result.rowcount != 1:
        db.refresh(row)
        return row.status
    db.refresh(row)
    try:
        smtp_email.send_email(settings=settings, to_address=row.recipient, subject=row.subject,
            text_body=row.body, from_address=os.environ.get('RFONE_SMTP_FROM_ADDRESS') or settings.username)
    except Exception:
        row.status = 'UNKNOWN'
        row.last_error = 'Invio non confermato: verifica la posta prima di ripetere. Nessun reinvio automatico.'
    else:
        row.status = 'SENT'; row.sent_at = ps.utcnow()
    db.commit()
    return row.status


@bp.route('/posizioni/<int:position_id>/candidati/<int:pc_id>/revisione-ai', methods=['GET', 'POST'])
@access_required
def candidate_review(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id)
    pc = _pc(db, position, pc_id)
    try:
        if request.method == 'GET':
            return jsonify(view(db, position, pc, actor))
        if not actor.can_edit(position):
            abort(403)
        if request.content_length and request.content_length > 100000:
            abort(413)
        data = json.loads(request.form.get('payload', '{}'))
        if not isinstance(data, dict):
            raise ValueError('Richiesta non valida.')
        current_view = view(db, position, pc, actor)
        if data.get('version') != current_view['version']:
            return jsonify(error='Analisi o revisione cambiate. Riapri la modale prima di salvare.'), 409
        action = data.get('action')
        if action not in ('save', 'send') or data.get('priority', '') not in ('', *PRIORITIES):
            raise ValueError('Scegli un’azione e una priorità valide.')
        channel = data.get('channel', 'EMAIL')
        if channel not in ('EMAIL', 'TEXT'):
            raise ValueError('Scegli Email oppure Text.')
        custom = data.get('custom_questions', [])
        if not isinstance(custom, list) or len(custom) > 20 or any(not isinstance(q, str) or len(q) > 2000 for q in custom):
            raise ValueError('Puoi aggiungere fino a 20 domande, massimo 2000 caratteri ciascuna.')
        custom = [q.strip() for q in custom if q.strip()]
        result, cv_hash, anchor = current(db, position, pc)
        supplied = data.get('items')
        expected = {item['id'] for item in current_view['items']}
        if (not isinstance(supplied, list) or any(not isinstance(i, dict) or type(i.get('id')) is not int for i in supplied)
                or len(supplied) != len(expected) or {i['id'] for i in supplied} != expected):
            raise ValueError('L’elenco dei chiarimenti non corrisponde all’analisi corrente.')
        items, questions = {}, []
        for item in supplied:
            mode = item.get('mode'); answer = item.get('answer', ''); question = item.get('question', '')
            if mode not in MODES or not isinstance(answer, str) or not isinstance(question, str) or len(answer) > 4000 or len(question) > 2000:
                raise ValueError('Controlla modalità e testo del chiarimento.')
            if mode == 'ANSWER' and not answer.strip():
                raise ValueError('Inserisci la risposta per ogni voce impostata su Rispondi.')
            if mode == 'ASK' and not question.strip():
                raise ValueError('Inserisci la domanda da inviare.')
            detail = next(d for d in result['details'] if d['id'] == item['id'])
            items[str(item['id'])] = {'key': item_key(detail, cv_hash, position.role_code), 'mode': mode,
                'answer': answer.strip() if mode == 'ANSWER' else '', 'question': question.strip() if mode == 'ASK' else ''}
            if mode == 'ASK':
                questions.append(question.strip())
        questions.extend(custom)
        if action == 'send' and not questions:
            raise ValueError('Seleziona almeno una domanda da inviare al candidato.')
        settings = None
        text_recipient = text_body = None
        if action == 'send':
            if channel == 'EMAIL':
                settings = smtp_settings()
            else:
                if not local_operator() and not review_text.available():
                    raise ValueError('Text messages are not switched on yet. Send the questions by Email.')
                text_recipient = review_text.recipient(current_view['phone'])
                text_body = review_text.body(questions, english=not local_operator())
                settings = review_text.settings(local=local_operator())
        raw_context = position.organization_context_json
        context = position_settings.context(position)
        previous = context.setdefault('candidate_reviews', {}).get(str(pc.id), {})
        saved = {'anchor': anchor, 'priority': data.get('priority', ''), 'accepted': data.get('priority', '') == '',
            'channel': channel, 'custom_questions': custom, 'items': items,
            'by': actor.name, 'at': ps.utcnow().isoformat()}
        row = None
        text_key = None
        new_text = False
        if previous.get('outbox_id'):
            saved['outbox_id'] = previous['outbox_id']
        if previous.get('text_batch'):
            saved['text_batch'] = previous['text_batch']
        if action == 'send' and channel == 'EMAIL':
            if not current_view['email']:
                raise ValueError('Il candidato non ha un indirizzo email valido.')
            source = 'review:' + str(pc.id) + ':' + inc.digest({'anchor': anchor, 'channel': channel, 'recipient': current_view['email'], 'questions': questions})
            subject, body = candidate_email(questions)
            if len(body) > 16000:
                raise ValueError('Le domande selezionate superano il limite di 16000 caratteri. Riduci il testo prima dell’invio.')
            row = mail_delivery.enqueue(db, pc=pc, source_key=source, subject=subject, body=body)
            saved['outbox_id'] = row.id
        elif action == 'send' and channel == 'TEXT':
            text_key = inc.digest({'anchor': anchor, 'channel': 'TEXT', 'recipient': text_recipient, 'body': text_body})
            batches = context.setdefault('candidate_text_outbox', {})
            if text_key not in batches:
                batches[text_key] = {'pc_id': pc.id, 'recipient': text_recipient, 'body': text_body,
                    'status': 'SENDING', 'at': ps.utcnow().isoformat(), 'by': actor.name}
                new_text = True
            saved['text_batch'] = text_key
        context['candidate_reviews'][str(pc.id)] = saved
        changed = db.execute(update(ps.Position).where(ps.Position.id == position.id,
            ps.Position.organization_context_json == raw_context).values(organization_context_json=json.dumps(context, ensure_ascii=False))
            .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.rollback()
            return jsonify(error='La ricerca è cambiata. Riapri la modale; la bozza resta disponibile.'), 409
        db.commit()
        delivery = deliver(db, row, settings) if row is not None else None
        if text_key:
            delivery = review_text.deliver(db, position.id, text_key, settings) if new_text else context['candidate_text_outbox'][text_key]['status']
        return jsonify(ok=True, delivery=delivery)
    except (ValueError, TypeError) as exc:
        db.rollback()
        return jsonify(error=str(exc)), 422
