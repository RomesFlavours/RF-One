"""Historical payout observations; never calculation runs or payment obligations."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata

from sqlalchemy import select, text
from .. import models as m

SOURCE = 'CHASE_PDF'
DOCUMENT = 'tips_historical_document'
PAYMENT = 'tips_historical_payment'


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _name(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def import_document(session, *, payload, restaurant_id, location_id, file_name):
    """Caller owns transaction. Same document is immutable and idempotent."""
    sha = payload['pdf_sha256']
    if not re.fullmatch('[a-f0-9]{64}', sha):
        raise ValueError('Invalid document SHA256')
    ledger = payload['ledger']
    if not ledger or len({r['pdf_row'] for r in ledger}) != len(ledger):
        raise ValueError('Missing or repeated physical row identifiers')
    for row in ledger:
        if type(row['amount_minor']) is not int or row['amount_minor'] < 0:
            raise ValueError('Amounts must be nonnegative integer cents')
        if row['page'] < 1 or row['pdf_row'] < 1:
            raise ValueError('Invalid source coordinates')
        if row['category'] == 'in_scope' and (row['status'] != 'Completed' or not row['explicit_tip']):
            raise ValueError('Only completed explicit tips can enter paid totals')
    if sum(r['amount_minor'] for r in ledger if r['category'] == 'in_scope') != payload['totals']['in_scope_minor']:
        raise ValueError('Document total does not balance')
    location_ids = set(session.scalars(select(m.RestaurantLocation.location_id).where(
        m.RestaurantLocation.restaurant_id == restaurant_id)))
    if location_id not in location_ids:
        raise ValueError('Location does not belong to restaurant')
    # Serialize imports sharing a source/catalog, and the restaurant/document.
    if session.bind.dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 7420191019})
    source = session.scalars(select(m.SourceSystem).where(m.SourceSystem.code == SOURCE)).first()
    if source is None:
        source = m.SourceSystem(code=SOURCE, name='Chase PDF historical tip payment evidence', active=True)
        session.add(source); session.flush()
    identity = f'{restaurant_id}:{sha}'
    existing = session.scalars(select(m.SourceRecord).where(
        m.SourceRecord.source_system_id == source.id, m.SourceRecord.entity_type == DOCUMENT,
        m.SourceRecord.source_id == identity)).all()
    if len(existing) > 1:
        raise ValueError('Duplicate document imports require review')
    input_hash = _hash({'scope':payload['scope'], 'ledger':ledger, 'people':[p['name'] for p in payload['people']]})
    if existing:
        doc = existing[0]
        stored = session.scalars(select(m.SourceRecord).where(
            m.SourceRecord.ingestion_run_id == doc.ingestion_run_id, m.SourceRecord.entity_type == PAYMENT)).all()
        if doc.raw_json['input_hash'] != input_hash or len(stored) != len(ledger):
            raise ValueError('Existing document differs; no observations overwritten')
        expected = {r['pdf_row']:r for r in ledger}
        for record in stored:
            raw = record.raw_json
            if raw['observation'] != expected.get(raw['observation']['pdf_row']) or record.payload_hash != _hash(raw):
                raise ValueError('Existing observation integrity failure')
        return {'run_id':doc.ingestion_run_id,'created':False,'rows':len(stored)}
    employees = defaultdict(list)
    for employee in session.scalars(select(m.Employee).where(m.Employee.location_id.in_(location_ids))):
        employees[_name(employee.display_name)].append(employee)
    now = datetime.now(timezone.utc)
    run = m.IngestionRun(source_system_id=source.id, location_id=location_id, started_at=now,
        finished_at=now, status='COMPLETE', acquisition_mode='DOCUMENT_EVIDENCE', resource_type='tips_historical_payment',
        notes='Historical paid-tip observations from user-supplied PDF; no payout obligations, finalization or Bank changes.')
    session.add(run); session.flush()
    manifest = {'restaurant_id':restaurant_id,'location_id':location_id,'document_sha256':sha,
        'file_name':file_name,'scope':payload['scope'],'currency':'USD','input_hash':input_hash,
        'row_count':len(ledger),'display_recipients':[p['name'] for p in payload['people']],
        'basis':payload['basis'],'schema_version':1,'eligible_for_payout':False,'finalized':False}
    session.add(m.SourceRecord(ingestion_run_id=run.id, source_system_id=source.id,
        entity_type=DOCUMENT, source_id=identity, retrieved_at=now, payload_hash=_hash(manifest), raw_json=manifest))
    for row in ledger:
        candidates = employees[_name(row['recipient'])]
        employee = candidates[0] if len(candidates) == 1 else None
        raw = {'restaurant_id':restaurant_id,'document_sha256':sha,'currency':'USD','observation':row,
            'employee_id':employee.id if employee else None,
            'source_employee_id':employee.source_employee_id if employee else None,
            'identity_status':'EXACT_NAME' if employee else ('AMBIGUOUS' if candidates else 'UNRESOLVED')}
        session.add(m.SourceRecord(ingestion_run_id=run.id, source_system_id=source.id,
            entity_type=PAYMENT, source_id=f'{sha}:{row["pdf_row"]}', retrieved_at=now,
            payload_hash=_hash(raw), raw_json=raw))
    session.flush()
    return {'run_id':run.id,'created':True,'rows':len(ledger)}


def list_documents(session, *, restaurant_id):
    records = session.scalars(select(m.SourceRecord).where(m.SourceRecord.entity_type == DOCUMENT)
        .order_by(m.SourceRecord.id.desc())).all()
    return [{'run_id':r.ingestion_run_id, **r.raw_json} for r in records
            if r.raw_json.get('restaurant_id') == restaurant_id]


def report(session, *, restaurant_id, run_id):
    document = next((d for d in list_documents(session, restaurant_id=restaurant_id) if d['run_id']==run_id),None)
    if document is None:
        return None
    observations = session.scalars(select(m.SourceRecord).where(
        m.SourceRecord.ingestion_run_id == run_id, m.SourceRecord.entity_type == PAYMENT)
        .order_by(m.SourceRecord.id)).all()
    rows = [r.raw_json for r in observations]
    if len(rows)!=document['row_count'] or any(r.payload_hash != _hash(r.raw_json) for r in observations):
        raise ValueError('Stored historical evidence integrity failure')
    categories = ['in_scope','cross_boundary','outside_scope','tip_period_unclear']
    names = set(document['display_recipients'])
    names.update(r['observation']['recipient'] for r in rows if r['observation']['explicit_tip'])
    people=[]
    for name in sorted(names):
        own=[r for r in rows if r['observation']['recipient']==name]
        p={'name':name,'payments':own}
        p.update({c:sum(r['observation']['amount_minor'] for r in own if r['observation']['category']==c) for c in categories})
        eligible=[r for r in own if r['observation']['category']=='in_scope']
        p['unresolved']=any(r['identity_status']!='EXACT_NAME' for r in eligible)
        p['payment_count']=len(eligible)
        repeat=Counter((r['observation']['date'],r['observation']['amount_minor'],r['observation']['memo']) for r in eligible)
        p['exact_repeat_extra']=sum((n-1)*key[1] for key,n in repeat.items())
        p['employee_id']=next((r['employee_id'] for r in own if r['employee_id']),None)
        people.append(p)
    return {'document':document,'people':people,'totals':{c:sum(p[c] for p in people) for c in categories},
        'repeat_extra':sum(p['exact_repeat_extra'] for p in people),'rows':len(rows)}
