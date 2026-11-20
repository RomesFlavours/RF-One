"""Reusable statement narratives for operations performed by the issuing bank."""
import re
from sqlalchemy import inspect, text

TABLE = 'bank_statement_purposes'
METHOD = 'Causale bancaria'
# Only whole bank narratives: a shop whose name contains "FEE" is not a bank operation.
BANK_TEXT = re.compile(
    r'(?:MONTHLY SERVICE FEE|OFFICIAL CHECKS CHARGE|FEE REVERSAL|LATE FEE|ANNUAL MEMBERSHIP FEE|'
    r'ONLINE (?:DOMESTIC|US DOLLAR INTL) WIRE FEE|FOREIGN TRANSACTION FEE|'
    r'INTEREST PAYMENT|CASH REDEMPTION|(?:CREDIT|DEBIT) MEMORANDUM REF: (?:ADVANCE ON LOAN|INTEREST PAYMENT ON LOAN))$')
def key(txn, instrument):
    if not instrument or not instrument.institution or not txn.amount_minor:
        return None
    narrative = ' '.join((txn.description_original or '').upper().split())
    if not narrative:
        return None
    narrative = re.sub(r'\s+TRN:\s*[A-Z0-9]+(?:\s+\d{2}/\d{2})?$', '', narrative)
    for pattern in (r'^FOREIGN EXCHANGE RATE ADJUSTMENT FEE\b', r'^FDR DEBIT CARD VISA DEBIT FOREIGN TRANSACTION FEE\b'):
        matched = re.match(pattern, narrative)
        if matched:
            narrative = matched.group()
            break
    return (instrument.institution.strip().upper(), 'OUT' if txn.amount_minor < 0 else 'IN', narrative)

def candidate(k, txn=None):
    if k and txn and (txn.classification == "FEE" or (txn.native_transaction_type or "").strip().upper() in
                      {"BANK FEE", "SERVICE CHARGE", "BANK INTEREST"}):
        return True
    # Limit generic matches to full banking phrases, including new institutions' wording.
    generic = r'(?:(?:MONTHLY|ANNUAL|QUARTERLY) )?(?:ACCOUNT MAINTENANCE|ACCOUNT SERVICE|OVERDRAFT|WIRE TRANSFER|STATEMENT|FOREIGN TRANSACTION|ATM WITHDRAWAL) (?:FEE|CHARGE)(?: REVERSAL)?'
    return k and (BANK_TEXT.fullmatch(k[2]) or re.fullmatch(generic,k[2]) or k[2] in (
        'FOREIGN EXCHANGE RATE ADJUSTMENT FEE','FDR DEBIT CARD VISA DEBIT FOREIGN TRANSACTION FEE'))

def rules(db):
    if not inspect(db.connection()).has_table(TABLE):
        return {}
    return {(r.bank,r.direction,r.narrative):r.why_id for r in db.execute(text(
        'SELECT bank,direction,narrative,why_id FROM bank_statement_purposes ORDER BY bank,direction,narrative'))}

def persist(db,k,why_id,previous):
    args=dict(bank=k[0],direction=k[1],narrative=k[2],why=why_id,previous=previous)
    if previous is None:
        db.execute(text('INSERT INTO bank_statement_purposes VALUES (:bank,:direction,:narrative,:why) ON CONFLICT(bank,direction,narrative) DO NOTHING'),args)
    else:
        db.execute(text('UPDATE bank_statement_purposes SET why_id=:why WHERE bank=:bank AND direction=:direction AND narrative=:narrative AND why_id=:previous'),args)
    if rules(db).get(k)!=why_id:
        raise ValueError('La causale è stata modificata. Riapri la sezione.')
