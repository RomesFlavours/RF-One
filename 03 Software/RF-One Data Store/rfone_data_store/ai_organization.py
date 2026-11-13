"""Persistent interview orchestration; approved writes reuse Organization services."""
from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import json
import uuid
import hashlib

from sqlalchemy import ForeignKey, Integer, String, Text, Boolean, select
from sqlalchemy.orm import Mapped, mapped_column
from . import models as m
from . import organizational_responsibility_service as org


class Interview(m.Base):
    __tablename__ = 'ai_organization_interviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('rfone_accounts.id'))
    entity_id: Mapped[int] = mapped_column(ForeignKey('legal_entities.id'))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document: Mapped[str] = mapped_column(Text, default='{}')


class CompanyGrant(m.Base):
    __tablename__ = 'ai_organization_company_grants'
    account_id: Mapped[int] = mapped_column(ForeignKey('rfone_accounts.id'), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey('legal_entities.id'), primary_key=True)
    can_apply: Mapped[bool] = mapped_column(Boolean, default=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def authorize(db, account, entity_id, *, apply=False):
    grant = db.get(CompanyGrant, (account.id, entity_id))
    if not account.is_admin and (not grant or (apply and not grant.can_apply)):
        raise PermissionError('Non sei autorizzato per questa azienda o operazione.')
    if not db.get(m.LegalEntity, entity_id):
        raise ValueError('Azienda non disponibile.')


def companies(db, account):
    query = select(m.LegalEntity).where(m.LegalEntity.status == 'ACTIVE')
    if not account.is_admin:
        query = query.join(CompanyGrant, CompanyGrant.entity_id == m.LegalEntity.id).where(CompanyGrant.account_id == account.id)
    return list(db.scalars(query.order_by(m.LegalEntity.legal_name)))


def context(db, entity_id):
    """Only explicitly company-scoped records; never leak global/other-company data."""
    positions = list(db.scalars(select(m.Position).join(m.PositionScope).where(
        m.PositionScope.scope_type == 'LEGAL_ENTITY', m.PositionScope.scope_id == entity_id,
        m.Position.is_active.is_(True))).unique())
    result = []
    for p in positions:
        # A shared position cannot be edited from a single-company interview.
        scopes = list(db.scalars(select(m.PositionScope).where(m.PositionScope.position_id == p.id)))
        exclusive = all(s.scope_type == 'LEGAL_ENTITY' and s.scope_id == entity_id for s in scopes)
        ownerships = list(db.scalars(select(m.ProcessOwnership).where(
            m.ProcessOwnership.position_id == p.id,
            m.ProcessOwnership.scope_type == 'LEGAL_ENTITY', m.ProcessOwnership.scope_id == entity_id)))
        result.append(dict(id=p.id, name=p.name, description=p.description or '', exclusive=exclusive,
                           processes=[o.process_name for o in ownerships],
                           vacant=org.resolve_current_occupant(db, position=p) is None))
    restaurants = list(db.scalars(select(m.Restaurant).where(m.Restaurant.legal_entity_id == entity_id)))
    restaurant_ids = [r.id for r in restaurants]
    areas = list(db.scalars(select(m.OperationalArea).where(m.OperationalArea.restaurant_id.in_(restaurant_ids))))
    roles = list(db.scalars(select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id.in_(restaurant_ids))))
    return dict(positions=sorted(result, key=lambda x: x['id']), restaurants=[r.name for r in restaurants],
                areas=[a.name for a in areas], roles=[r.name for r in roles])


def create(db, account, entity_id):
    authorize(db, account, entity_id)
    row = Interview(id=str(uuid.uuid4()), account_id=account.id, entity_id=entity_id,
                    document=json.dumps(dict(messages=[], evidence=[], draft=[], history=[],
                    summary='', missing=[], alternatives=[], baseline=context(db, entity_id),
                    research='Ricerca esterna non eseguita. Puoi aggiungere riferimenti in conversazione.',
                    mode='DEMO', approved=None, applied=[])))
    db.add(row)
    db.flush()
    return row


def load(db, account, interview_id):
    row = db.get(Interview, interview_id)
    if not row or row.account_id != account.id:
        raise PermissionError('Sessione non disponibile per questo account.')
    authorize(db, account, row.entity_id)
    return row


def validate_draft(draft):
    if not isinstance(draft, list) or len(draft) > 30:
        raise ValueError('Bozza non valida.')
    names = set()
    for item in draft:
        if not isinstance(item, dict):
            raise ValueError('Posizione non valida.')
        for field, limit in [('name', 255), ('description', 5000), ('process', 128)]:
            if not isinstance(item.get(field), str) or not item[field].strip() or len(item[field]) > limit:
                raise ValueError('Ogni proposta richiede nome, responsabilità e processo validi.')
        name = item['name'].strip().casefold()
        if name in names:
            raise ValueError('Due proposte hanno lo stesso nome: chiarire la sovrapposizione.')
        names.add(name)
        if set(item) - {'name', 'description', 'process'}:
            raise ValueError('La proposta contiene operazioni non supportate.')
    return draft


def demo_reply(doc, text):
    """Proposal-first demo. Rules and researched references, never simulated AI."""
    from .ai_organization_research import attach_research
    attach_research(doc)
    facts = doc['evidence']
    combined = ' '.join(f['text'] for f in facts).casefold()
    current = doc.get('baseline', {}).get('positions', [])
    reopening = any(word in combined for word in ('riapri', 'riaper', 'aprire', 'apertura'))
    deliveries = any(word in combined for word in ('consegn', 'ordini', 'fornitor'))
    distributed = any(word in text.casefold() for word in ('preferisco distribuit', 'scelgo distribuit', 'dividiamo'))
    subject = 'riapertura' if reopening else ('consegne' if deliveries else 'risultato')
    name = 'Coordinamento della ' + subject if subject == 'riapertura' else 'Coordinamento del ' + subject
    if deliveries and not reopening:
        name = 'Coordinamento delle consegne'
    process = 'Coordinamento ' + subject
    recommended = (
        'Ti propongo di partire con un presidio leggero di coordinamento: una responsabilità '
        'riconoscibile che tiene insieme attività, impedimenti e decisioni da ottenere, '
        'senza aggiungere subito livelli gerarchici. Prima verifichiamo se può essere coperta '
        'da una posizione e da risorse già presenti. Le decisioni restano a chi è già autorizzato.'
    )
    if distributed:
        recommended = ('Sviluppo l’alternativa distribuita che hai indicato: responsabilità per attività, '
            'un punto di passaggio delle informazioni e un referente di coordinamento, '
            'senza attribuirgli automaticamente autorità sulle altre persone.')
    existing = ('Nel sistema vedo ' + ', '.join(p['name'] for p in current) + '. '
        + ('Ci sono posizioni scoperte: crearne altre non risolverebbe da solo la copertura. '
           if any(p['vacant'] for p in current) else 'Valuterei prima il riuso di questa struttura. ')) if current else (
        'Nel perimetro aziendale selezionato non risultano posizioni esplicitamente collegate. '
        'Questo non prova che nella realtà manchino responsabilità. ')
    doc['summary'] = '\n'.join(f['text'] for f in facts)
    doc['recommendation'] = recommended
    doc['hypotheses'] = ['Una responsabilità di coordinamento può essere utile: ipotesi da verificare sul caso.',
        'Copertura, capacità e autorità decisionale non vengono dedotte dai titoli.']
    doc['verification'] = 'Proposta da concordare: una prova limitata, verificando attività senza responsabile, decisioni in attesa e passaggi di informazioni persi.'
    doc['alternatives'] = [
        'A — Presidio leggero, proposta iniziale: pochi passaggi e un punto di coordinamento. Impegno: verificare copertura e carico; rischio: diventare un collo di bottiglia. Il richiamo a ruoli decisionali distinti è coerente con Bain, senza imporre il suo modello.',
        'B — Responsabilità distribuite: decisioni operative vicine al lavoro e responsabilità per attività. Impegno: chiarire interfacce e deleghe; rischio: sovrapposizioni se i confini restano ambigui. Il confronto con McKinsey suggerisce di distinguere i tipi di decisione, non di delegare automaticamente.',
    ]
    if not doc['draft']:
        doc['draft'] = [dict(name=name, description='Proposta da approvare: coordinare attività e passaggi informativi, rilevare impedimenti e portare le decisioni a chi è autorizzato. Nessuna persona assegnata e nessuna nuova delega.', process=process)]
    # The user validates a discriminating fact rather than designing the solution.
    question = ('Per valutare se riusare il presidio esistente: oggi c’è qualcuno che tiene già insieme queste attività?'
                if len(facts) == 1 else 'Nella proposta che ti ho presentato, quale punto non corrisponde alla situazione reale?')
    doc['missing'] = [question]
    return (existing + '\n\n' + recommended + '\n\n'
        'Confronterei questa soluzione con responsabilità distribuite: meno concentrazione del carico, '
        'ma più accordi sui passaggi. La proposta iniziale è reversibile e non richiede di assumere nuove persone. '
        'Non posso ancora definirla la migliore senza verificarne la copertura. '
        '\n\n' + doc['verification'] + '\n\n' + question)


def turn(db, row, account, text, provider=None):
    text = text.strip()
    if not text or len(text) > 12000:
        raise ValueError('Inserisci un messaggio tra 1 e 12000 caratteri.')
    doc = json.loads(row.document)
    doc['history'].append(dict(revision=row.revision, draft=deepcopy(doc['draft']), approved=row.approved_revision, at=now()))
    event = dict(text=text, author=account.display_name, at=now(), source='utente', status='dichiarato')
    doc['messages'].append(dict(event, role='user'))
    doc['evidence'].append(event)
    from .ai_organization_research import attach_research
    attach_research(doc)
    if provider:
        # The provider receives demo-only data in the local launcher. Never import
        # Selection's dotenv/AWS client here or silently fall back after a failure.
        answer = provider(dict(document=deepcopy(doc), current=context(db, row.entity_id),
            instruction='Proponi tu soluzioni motivate, riusando prima i dati presenti. Non chiedere all’utente di progettare ruoli o processi. Confronta alternative usando le fonti allegate e distingui fonti da deduzioni. Chiedi soltanto un fatto discriminante ancora ignoto. Italiano. Desiderio → risorse → vincoli → processo → obiettivo verificabile. Una domanda mirata. Distingui fatti, ipotesi e proposte. Non inventare persone o autorità. Restituisci reply, summary, missing, alternatives, draft.'))
        if not isinstance(answer, dict) or not all(isinstance(answer.get(k), str) for k in ('reply', 'summary')):
            raise ValueError('Risposta AI non valida; nessuna modifica salvata.')
        for key in ('missing', 'alternatives'):
            if not isinstance(answer.get(key), list) or not all(isinstance(x, str) for x in answer[key]):
                raise ValueError('Risposta AI non valida.')
        validate_draft(answer.get('draft'))
        for key in ('summary', 'missing', 'alternatives', 'draft'):
            doc[key] = answer[key]
        reply = answer['reply']
        doc['mode'] = 'AI'
    else:
        doc['mode'] = 'DEMO'
        reply = demo_reply(doc, text)
    doc['messages'].append(dict(role='assistant', text=reply, source=doc['mode'], status='proposto', at=now(), author='AI Organization'))
    row.revision += 1
    row.approved_revision = None
    row.document = json.dumps(doc, ensure_ascii=False)


def revise(row, draft, account):
    validate_draft(draft)
    doc = json.loads(row.document)
    doc['history'].append(dict(revision=row.revision, draft=doc['draft'], approved=row.approved_revision, at=now()))
    doc['draft'] = draft
    doc['evidence'].append(dict(text='Bozza corretta esplicitamente', draft=draft, author=account.display_name,
                                source='utente', status='proposto', at=now()))
    row.revision += 1
    row.approved_revision = None
    row.document = json.dumps(doc, ensure_ascii=False)


def preview(db, row):
    doc = json.loads(row.document)
    current = context(db, row.entity_id)
    changes = []
    for item in validate_draft(doc['draft']):
        matches = [p for p in current['positions'] if p['name'].casefold() == item['name'].strip().casefold()]
        if len(matches) > 1 or any(not p['exclusive'] for p in matches):
            raise ValueError('Posizione ambigua o condivisa con altri ambiti: modifica bloccata.')
        old = matches[0] if matches else None
        changes.append(dict(proposal=item, before=old, action='Modifica/riuso' if old else 'Aggiunta',
                            consequence='Posizione senza nuove assegnazioni personali; nessun accesso concesso.'))
    return current, changes


def approve(db, row, account):
    authorize(db, account, row.entity_id, apply=True)
    baseline, changes = preview(db, row)
    if not changes:
        raise ValueError('La bozza non contiene posizioni applicabili.')
    doc = json.loads(row.document)
    doc['approved'] = dict(revision=row.revision, baseline=baseline, draft=doc['draft'],
                           evidence=deepcopy(doc['evidence']), author=account.display_name, at=now(), status='approvato')
    row.approved_revision = row.revision
    row.document = json.dumps(doc, ensure_ascii=False)


def apply(db, row, account):
    authorize(db, account, row.entity_id, apply=True)
    engine = db.get_bind()
    if engine.dialect.name != 'sqlite' or not engine.url.database or not engine.url.database.endswith('ai-organization-local.sqlite3'):
        raise ValueError('Applicazione consentita solo nel database dimostrativo locale isolato.')
    # Serialize competing confirms before checking the persisted application marker.
    db.connection().exec_driver_sql('UPDATE ai_organization_interviews SET revision=revision WHERE id=?', (row.id,))
    db.refresh(row)
    if row.applied_revision == row.revision:
        return
    if row.approved_revision != row.revision:
        raise ValueError('Approva questa revisione prima di applicarla.')
    doc = json.loads(row.document)
    current, changes = preview(db, row)
    if current != doc['approved']['baseline']:
        raise ValueError('Organization è cambiata: rivedi il confronto e approva di nuovo.')
    applied = []
    for change in changes:
        item, old = change['proposal'], change['before']
        if old:
            position = db.get(m.Position, old['id'])
            position.description = item['description']
        else:
            position = org.create_position(db, name=item['name'].strip(), description=item['description'])
            org.add_position_scope(db, position=position, scope_type='LEGAL_ENTITY', scope_id=row.entity_id)
        existing = db.scalar(select(m.ProcessOwnership).where(m.ProcessOwnership.position_id == position.id,
            m.ProcessOwnership.domain == 'ORGANIZATION', m.ProcessOwnership.process_name == item['process'],
            m.ProcessOwnership.scope_type == 'LEGAL_ENTITY', m.ProcessOwnership.scope_id == row.entity_id))
        if not existing:
            existing = org.set_process_ownership(db, domain='ORGANIZATION', process_name=item['process'],
                position=position, scope_type='LEGAL_ENTITY', scope_id=row.entity_id)
        applied.append(dict(position_id=position.id, process_ownership_id=existing.id,
                            entity_id=row.entity_id, responsibility=item['description'], process=item['process']))
    doc['applied'].append(dict(revision=row.revision, at=now(), author=account.display_name,
                              status='approvato', source='approvazione esplicita', records=applied))
    row.applied_revision = row.revision
    row.document = json.dumps(doc, ensure_ascii=False)
