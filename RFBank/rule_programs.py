"""Versioned rule programs and deterministic execution; deliberately no AI imports."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import uuid
import weakref

import engine
from rule_sources import Sources

OVERRIDE = ContextVar('rfbank_program_override', default=None)
METHOD = 'REGOLA NIDIFICATA'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def initialize(database):
    """Explicit setup only, never called by reconciliation."""
    with sqlite3.connect(database) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS rfbank_rule_programs (
            id TEXT NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL,
            plan TEXT NOT NULL, status TEXT NOT NULL, signature TEXT NOT NULL,
            created_at TEXT NOT NULL, events TEXT NOT NULL,
            PRIMARY KEY (id, version))''')


def records(database, *, active=False):
    with engine.connect(database) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='rfbank_rule_programs'").fetchone():
            return []
        rows = db.execute('''SELECT p.* FROM rfbank_rule_programs p WHERE version =
            (SELECT max(version) FROM rfbank_rule_programs q WHERE q.id=p.id) ORDER BY created_at,id''').fetchall()
    return [dict(r, plan=json.loads(r['plan']), events=json.loads(r['events'])) for r in rows
            if r['status'] == 'ACTIVE' or not active and r['status'] != 'DELETED']


def generation(database):
    return engine.signature({'programs': [(r['id'], r['version'], r['status'], r['signature']) for r in records(database)]})


def activate(database, plan, program_id=None, expected_version=None, expected_generation=None):
    engine.validate(plan)
    identifier = program_id or uuid.uuid4().hex
    with sqlite3.connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        if expected_generation is not None and generation(database) != expected_generation:
            raise ValueError('Le regole sono cambiate: ripeti la simulazione.')
        previous = db.execute('SELECT version,status FROM rfbank_rule_programs WHERE id=? ORDER BY version DESC LIMIT 1', (identifier,)).fetchone()
        if program_id and (not previous or previous[0] != expected_version or previous[1] == 'DELETED'):
            raise ValueError('La regola è cambiata o è stata eliminata: riaprila e simula.')
        version = previous[0]+1 if previous else 1
        if previous:
            db.execute("UPDATE rfbank_rule_programs SET status='SUPERSEDED' WHERE id=?", (identifier,))
        db.execute('INSERT INTO rfbank_rule_programs VALUES (?,?,?,?,?,?,?,?)',
            (identifier, version, plan['title'], json.dumps(plan, ensure_ascii=False), 'ACTIVE',
             engine.signature(plan), stamp(), json.dumps([{'at': stamp(), 'action': 'ACTIVATE'}])))
    return identifier, version


def change_status(database, identifier, version, status):
    if status not in ('INACTIVE', 'DELETED'):
        raise ValueError('Azione non disponibile.')
    with sqlite3.connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT version,status,events FROM rfbank_rule_programs WHERE id=? ORDER BY version DESC LIMIT 1', (identifier,)).fetchone()
        if not row or row[0] != version or row[1] == 'DELETED':
            raise ValueError('La regola è cambiata: aggiorna l’elenco.')
        events = json.loads(row[2]) + [{'at': stamp(), 'action': status}]
        db.execute('UPDATE rfbank_rule_programs SET status=?,events=? WHERE id=? AND version=?',
                   (status, json.dumps(events), identifier, version))


class Runtime:
    def __init__(self, database, programs=None):
        self.database = Path(database)
        self.programs = records(database, active=True) if programs is None else programs
        self.data = engine.load_data(database) if self.programs else None
        self.sources = Sources(database) if self.programs else None
        self.failures = []
        if self.sources:
            weakref.finalize(self, self.sources.stack.close)
            for program in self.programs:
                try:
                    engine.validate(program['plan'])
                    self.sources.prepare(program['plan'])
                except ValueError as exc:
                    self.failures.append(str(exc))

    def close(self):
        if self.sources:
            self.sources.stack.close()

    def evaluate(self, row):
        proposals = []
        if self.failures:
            return dict(status='DOUBT', who=None, why=None, memo=None, steps=[], issues=self.failures)
        for p in self.programs:
            result = engine.simulate(p['plan'], dict(self.data, rows=[row]), self.sources)
            if result['rows']:
                found = result['rows'][0]
                found['steps'].insert(0, p['title'] + ' · versione ' + str(p['version']))
                proposals.append(found)
        if not proposals:
            return None
        conflict = any(len({str(r[k]).casefold() for r in proposals if r.get(k)}) > 1 for k in ('who', 'why', 'memo'))
        status = 'CONFLICT' if conflict or any(r['status'] == 'CONFLICT' for r in proposals) else 'DOUBT' if any(r['status'] == 'DOUBT' for r in proposals) else 'MATCH'
        return dict(status=status,
            **{k: next((r[k] for r in proposals if r.get(k)), None) for k in ('who', 'why', 'memo')},
            steps=[v for r in proposals for v in r['steps']],
            issues=[v for r in proposals for v in r['issues']] + (['Regole attive in conflitto.'] if conflict else []))

    def apply(self, owner, txn, result, auto):
        # Transfer/settlement and document splits retain their dedicated paths.
        if not self.programs or result.match or auto.get('split') or owner.bank_split(txn):
            return auto
        row = dict(id=txn.id, posting_date=str(txn.posting_date), day=str(txn.posting_date),
            description=txn.description_original or '', amount_minor=txn.amount_minor,
            source_id=txn.payment_instrument_id, source=result.source, memo=txn.source_memo,
            who=auto.get('who'), why=owner._why_name(auto.get('why_id')))
        proposal = self.evaluate(row)
        if not proposal:
            return auto
        auto['trace'].append(dict(stage='Regole nidificate', method=METHOD, value=proposal['status'],
                                  evidence='; '.join(proposal['steps'] + proposal['issues']), confidence=''))
        who = next((w for w in self.data['who'] if proposal.get('who') and w['canonical_name'].casefold() == proposal['who'].casefold()), None)
        why = next((w for w in self.data['why'] if proposal.get('why') and w['name'].casefold() == proposal['why'].casefold()), None)
        differs = (who and auto.get('who_id') and who['id'] != auto['who_id']) or (why and auto.get('why_id') and why['id'] != auto['why_id'])
        if proposal['status'] != 'MATCH' or differs:
            auto['exceptions'].append(dict(code='METHOD_CONFLICT' if differs or proposal['status'] == 'CONFLICT' else 'NESTED_RULE_UNRESOLVED',
                message='; '.join(proposal['issues']) or 'Regola nidificata in conflitto con la classificazione esistente.'))
            return auto
        if who:
            auto.update(who=who['canonical_name'], who_id=who['id'], who_method=METHOD)
            auto['exceptions'] = [x for x in auto['exceptions'] if x['code'] not in ('WHO_UNKNOWN',)]
        if why:
            auto.update(why_id=why['id'], category_id=why['accounting_classification_id'], why_method=METHOD)
            auto['exceptions'] = [x for x in auto['exceptions'] if x['code'] not in ('WHO_SOURCE_CLASSIFICATION_MISSING', 'WHY_RULE_MISSING', 'WHY_MISSING')]
        # Causale is evidence in the trace, never an overwrite of the original bank memo.
        return auto


def integrate(owner, txn, result, auto):
    if hasattr(owner, '_rfbank_programs'):
        return owner._rfbank_programs.apply(owner, txn, result, auto)
    database = owner.db.get_bind().url.database
    if not database:
        return auto
    if database.startswith('file:'):
        from urllib.parse import unquote
        database = unquote(database[5:].split('?', 1)[0])
    override = OVERRIDE.get()
    if not hasattr(owner, '_rfbank_programs'):
        owner._rfbank_programs = Runtime(database, override)
    return owner._rfbank_programs.apply(owner, txn, result, auto)


def preview(database, plan, replace_id=None):
    """Simulator: executes only this plan's instructions on every movement (engine.execute_plan), in memory and
    read-only. It does not run other rules or the Bank reconciliation pipeline and checks nothing against the
    WHO/WHY catalogue. replace_id is kept for the callers' signature."""
    engine.validate(plan)
    data = engine.load_data(database)
    with Sources(database) as sources:
        sources.prepare(plan)
        result = engine.execute_plan(plan, data, sources)
        evidence = sources.fingerprint()
    result['fingerprint'] = engine.signature(dict(data=data, evidence=evidence, plan=plan,
        generation=generation(database), results=result['rows']))
    return result
