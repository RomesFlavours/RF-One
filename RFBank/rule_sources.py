"""Reuse BankMerge's bounded read-only lookup workspace. No AI at execution."""
from contextlib import ExitStack
from pathlib import Path
import hashlib
import json
import re
import sys

WEB = Path(__file__).resolve().parent / '03 Software' / 'RF-One Web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
import bank_trial_sources as legacy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def walk(actions):
    for action in actions:
        yield action
        if action['op'] == 'branch':
            yield from walk(action['then'])
            yield from walk(action['else'])


def key(action):
    return json.dumps(action, sort_keys=True, ensure_ascii=False)


class Sources:
    def __init__(self, database):
        self.stack = ExitStack()
        self.engine = create_engine('sqlite:///file:' + Path(database).resolve().as_posix() + '?mode=ro&uri=true')
        self.stack.callback(self.engine.dispose)
        self.db = self.stack.enter_context(Session(self.engine))
        # Pin one SQLite snapshot for every source copied during this execution.
        self.db.connection().exec_driver_sql("BEGIN")
        self.lookups = {}
        # Owned by this Sources execution only, never reused across database revisions.
        self.workspace_cache = {}
        self.failures = {}
        self.warnings = []
        try:
            available = legacy.sources(self.db, warnings=self.warnings)
            # Business evidence only: never authentication/session tables.
            self.catalog = {k: v for k, v in available.items() if
                k.startswith(('file.', 'rf.')) and not any(x in k.lower() for x in ('account', 'secret', 'session', 'token', 'credential'))
                or k.startswith(('bank.bank_', 'bank.financial_', 'bank.payment_', 'bank.raw_bank_', 'bank.reporting_'))}
        except Exception:
            self.stack.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stack.close()

    def schema(self):
        result = dict(self.catalog)
        for name in list(result):
            if name.startswith('file.'):
                try:
                    result[name] = list(dict.fromkeys(k for row in legacy.uploaded(self.db, name) for k in row))
                except (ValueError, UnicodeError):
                    del result[name]
        return result

    def prepare(self, plan, *, strict=False):
        for rule in plan['rules']:
            for action in walk(rule['actions']):
                if action['op'] != 'lookup' or key(action) in self.lookups or key(action) in self.failures:
                    continue
                try:
                    # A lookup returns candidate facts, not an arbitrary first match.
                    if re.search(r'\b(limit|offset)\b', action['query'], re.I):
                        raise ValueError('La ricerca non può nascondere corrispondenze con LIMIT/OFFSET.')
                    lookup = legacy.Lookup(self.db, action, dict(self.catalog), populate=True,
                                           workspace_cache=self.workspace_cache)
                    self.stack.callback(lookup.conn.close)
                    self.lookups[key(action)] = lookup
                except Exception as exc:
                    message = 'Fonte o ricerca non disponibile: ' + str(exc)
                    if strict:
                        raise ValueError(message) from exc
                    self.failures[key(action)] = message

    def find(self, action, params):
        if key(action) in self.failures:
            raise ValueError(self.failures[key(action)])
        try:
            return self.lookups[key(action)].find(params)
        except Exception as exc:
            raise ValueError('Ricerca non completata: ' + str(exc)) from exc

    def fingerprint(self):
        """Hash the exact evidence snapshot, including external/file lookups."""
        hashes = {}
        for name, lookup in self.lookups.items():
            hashes[name] = lookup.evidence_digest
        return hashes
