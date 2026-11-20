"""PayPal source evidence; never writes financial transactions or classifications."""
import base64
import csv
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

from sqlalchemy import select
from .. import models as m

KIND = 'PAYPAL_ACTIVITY'
HEADERS = {'Date', 'Time', 'Name', 'Type', 'Status', 'Currency', 'Amount', 'Fees', 'Total', 'Transaction ID'}
MONEY = r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'


def minor(value):
    try:
        number = Decimal(str(value).replace(',', '').strip()) * 100
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError()
        return int(number)
    except (InvalidOperation, ValueError):
        raise ValueError('Importo PayPal non leggibile.') from None


def day(value):
    try:
        return datetime.strptime(value.strip(), '%m/%d/%Y').date().isoformat()
    except ValueError:
        raise ValueError('Data PayPal non leggibile.') from None


def parse_csv(content):
    try:
        text = content.decode('utf-8-sig')
    except UnicodeError:
        text = content.decode('cp1252')
    reader = csv.DictReader(StringIO(text, newline=''))
    if not HEADERS <= set(reader.fieldnames or []):
        raise ValueError('Formato CSV PayPal non riconosciuto: usa il report attività con Transaction ID.')
    events = []
    for number, row in enumerate(reader, 2):
        if not any(row.values()):
            continue
        try:
            if None in row or any(row.get(k) is None for k in HEADERS):
                raise ValueError('Colonne incomplete.')
            currency = row['Currency'].strip().upper()
            identifier = row['Transaction ID'].strip()
            if not identifier or not re.fullmatch(r'[A-Z]{3}', currency):
                raise ValueError('Transaction ID o valuta mancante.')
            amount, fees, total = (minor(row[k]) for k in ('Amount', 'Fees', 'Total'))
            if amount + fees != total:
                raise ValueError('Amount, Fees e Total non quadrano.')
            events.append(dict(transaction_id=identifier, date=day(row['Date']),
                time=row['Time'].strip(), timezone=row.get('TimeZone', '').strip(),
                name=row['Name'].strip(), type=row['Type'].strip(), status=row['Status'].strip(),
                currency=currency, amount_minor=amount, fees_minor=fees, total_minor=total,
                reference_id=row.get('Reference Txn ID', '').strip() or row.get('Reference Transaction ID', '').strip(),
                funding=[], raw=row, source_row=number))
        except ValueError as exc:
            raise ValueError(f'Riga PayPal {number}: {exc}') from None
    if not events:
        raise ValueError('Il CSV PayPal non contiene operazioni.')
    return dict(format='CSV', account=None, events=events)


def parse_pdf(content):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError('Per leggere gli statement PayPal installa la dipendenza pypdf indicata in requirements-paypal.txt.') from None
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError('PDF protetto o con più di 100 pagine.')
        text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    except Exception as exc:
        raise ValueError('Statement PDF PayPal non leggibile: serve un PDF testuale non protetto.') from exc
    if 'PAYPAL ACCOUNT' not in text or 'Statement Period' not in text:
        raise ValueError('Il PDF non è uno statement PayPal riconosciuto.')
    accounts = set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text))
    if len(accounts) != 1:
        raise ValueError('Account PayPal assente o ambiguo nello statement.')
    # PayPal sometimes wraps the last digit of the year onto a separate line.
    events = []
    for page_number, page in enumerate(reader.pages, 1):
        body = re.sub(r'(\d{2}/\d{2}/202)\s+(\d)\b', r'\1\2', page.extract_text() or '')
        if 'ACCOUNT ACTIVITY' not in body:
            continue
        body = body.split('ACCOUNT ACTIVITY', 1)[1]
        first_event = len(events)
        for match in re.finditer(r'(?m)^\s*(\d{2}/\d{2}/\d{4})\s+(.+?)(?=\n\s*\d{2}/\d{2}/\d{4}\s|\Z)', body, re.S):
            date_text, block = match.groups()
            ids = re.findall(r'(?<!Ref )\bID:\s*([A-Z0-9]+)', block)
            totals = re.search(r'\b([A-Z]{3})\s+('+MONEY+r')\s+('+MONEY+r')\s+('+MONEY+r')', block)
            if len(ids) != 1 or not totals:
                raise ValueError(f'Operazione PDF non leggibile a pagina {page_number}; nessun dato importato.')
            prefix = re.split(r'\bID:', block, maxsplit=1)[0]
            funding = re.findall(r'([^\n]+?\bx-[0-9]{4})[^\n]*', prefix)
            description = re.split(r'\n[^\n]*\bx-[0-9]{4}', prefix, maxsplit=1)[0]
            description = ' '.join(description.split())
            kind, sep, name = description.partition(':')
            ref = re.search(r'\bRef ID:\s*([A-Z0-9]+)', block)
            currency, amount, fees, total = totals.groups()
            if minor(amount) + minor(fees) != minor(total):
                raise ValueError('Totali incoerenti nello statement PayPal.')
            events.append(dict(transaction_id=ids[0], date=day(date_text), time=None, timezone=None,
                name=name.strip() if sep else '', type=kind.strip(), status=None,
                currency=currency, amount_minor=minor(amount), fees_minor=minor(fees), total_minor=minor(total),
                reference_id=ref.group(1) if ref else '', funding=[' '.join(f.split()) for f in funding],
                source_page=page_number))
        expected = len(re.findall(r'(?<!Ref )\bID:\s*[A-Z0-9]+', body))
        if len(events) - first_event != expected:
            raise ValueError(f'Non tutte le operazioni sono leggibili a pagina {page_number}; nessun dato importato.')
    if not events:
        raise ValueError('Nessuna operazione leggibile: usa lo statement PDF testuale o il CSV attività.')
    return dict(format='PDF', account=next(iter(accounts)), events=events)


def reports(db):
    return [json.loads(p) for p in db.scalars(select(m.BankFlowArtifact.payload)
        .where(m.BankFlowArtifact.kind == KIND).order_by(m.BankFlowArtifact.id))]


def evidence(saved):
    """Merge observations, not amounts. Preserve statuses, provenance and conflicts."""
    transactions = {}
    for report in saved:
        for event in report['events']:
            key = (event['transaction_id'], event['currency'])
            item = transactions.setdefault(key, dict(transaction_id=key[0], currency=key[1], observations=[], accounts=set()))
            if report.get('account'):
                item['accounts'].add(report['account'])
            observation = {k: v for k, v in event.items() if k not in ('raw', 'source_row', 'source_page')}
            if observation not in item['observations']:
                item['observations'].append(observation)
    for item in transactions.values():
        item['accounts'] = sorted(item['accounts'])
        item['conflict'] = len(item['accounts']) > 1 or len({e['total_minor'] for e in item['observations']}) > 1
        item['reference_ids'] = sorted({e['reference_id'] for e in item['observations'] if e['reference_id']})
        item['funding'] = sorted({f for e in item['observations'] for f in e['funding']})
    return list(transactions.values())


def ingest(db, filename, content, account_id):
    if len(content) > 25 * 1024 * 1024:
        raise ValueError('Il file PayPal supera 25 MB.')
    digest = hashlib.sha256(content).hexdigest()
    previous = reports(db)
    for report in previous:
        if report['digest'] == digest:
            return dict(report, new_transactions=0, already_stored=len({(e['transaction_id'], e['currency']) for e in report['events']})), False
    report = parse_pdf(content) if content.startswith(b'%PDF-') else parse_csv(content)
    old_keys = {(e['transaction_id'], e['currency']) for r in previous for e in r['events']}
    keys = {(e['transaction_id'], e['currency']) for e in report['events']}
    report.update(file_name=filename, digest=digest, content_b64=base64.b64encode(content).decode('ascii'),
        days=sorted({e['date'] for e in report['events']}), new_transactions=len(keys-old_keys), already_stored=len(keys & old_keys))
    db.add(m.BankFlowArtifact(kind=KIND, account_id=account_id, payload=json.dumps(report, ensure_ascii=False)))
    db.flush()
    return report, True
