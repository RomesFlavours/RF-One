"""Import integrity, idempotence and plan-refresh fidelity on a LOCAL disposable PostgreSQL copy (fixes A4, A5).

Target: a loopback `selection_production_test_*` database holding the pre-import state of the reviewed plan
(for example a restore of the pre-deploy dump).  The runner's own guard refuses any other target.  The test
writes only to that database and leaves the plan applied with a test batch id.  No AWS, no AI, no email.

    python test_import_integrity_local.py --dsn postgresql+psycopg://user@127.0.0.1:PORT/selection_production_test_x
        --plan production-plan.json --receipt production-plan.local-objects.json
        [--parent-plan parent.json --spec cutover-20261115.reconciliation.json --document-manifest manifest.json]

Checks: (1) optional - reconcile_plan.py regenerates exactly the applied plan; (2) an import that changes an
existing Selection row is refused and rolled back; (3) an import that writes outside Selection is refused and
rolled back; (4) a concurrent write by another transaction does not fail the import and is not attributed to
it; (5) repeat apply is a no-op; (6) post-commit verify reports later edits by other transactions separately;
(7) a batch without the pre-commit check is never reported as passed.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

import psycopg
from sqlalchemy import MetaData, event
from sqlalchemy.engine import make_url

import production_import as runner
import reconcile_plan

failures = []


def check(label, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else f'  [{detail}]'), flush=True)
    if not ok:
        failures.append(label)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--dsn', required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--parent-plan', type=Path)
    p.add_argument('--spec', type=Path)
    p.add_argument('--document-manifest', type=Path)
    args = p.parse_args()
    applied = runner.load_plan(args.plan)
    receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
    url = make_url(args.dsn)
    pg = f"host={url.host} port={url.port} user={url.username} dbname={url.database}"
    engine = runner.connect_target(args.dsn, 'local', 'apply', None, applied)   # refuses any non-test target

    def ledger(batch):
        with psycopg.connect(pg) as c:
            return c.execute('select status from selection_migration_batches where batch_id=%s', (batch,)).fetchone()

    def counts():
        with psycopg.connect(pg) as c:
            return {t: c.execute(f'select count(*) from "{t}"').fetchone()[0] for t in sorted(applied['inserts'])}

    def variant(tag):
        v = copy.deepcopy(applied)
        v.pop('plan_sha256')
        v['batch_id'] += '-' + tag
        v['plan_sha256'] = runner.digest(v)
        return v

    if args.parent_plan and args.spec:
        parent = runner.load_plan(args.parent_plan)
        spec = json.loads(args.spec.read_text(encoding='utf-8'))
        manifest = json.loads(args.document_manifest.read_text(encoding='utf-8')) if args.document_manifest else None
        ro = runner.connect_target(args.dsn, 'local', 'check', None, parent)
        names = sorted({a['table'] for a in parent['anchors']} | {s['table'] for s in parent['baseline_counts']}
                       | {'raw_resumes', 'candidates', 'applications', 'candidate_persons'})
        metadata = MetaData()
        metadata.reflect(ro, only=names, resolve_fks=False)
        with ro.connect() as c:
            regenerated, _, _ = reconcile_plan.refresh(c, parent, spec, metadata, manifest)
        ro.dispose()
        check('reconcile_plan regenerates exactly the applied plan', runner.digest(regenerated) == applied['plan_sha256'])

    runner.prepare_schema(engine)
    base = counts()

    def inject(sql, other_transaction=False):
        state = {'done': False}

        def listener(conn, cursor, statement, parameters, context, executemany):
            if not state['done'] and statement.lstrip().upper().startswith('INSERT INTO CANDIDATE_SKILLS'):
                state['done'] = True
                if other_transaction:
                    with psycopg.connect(pg, autocommit=True) as other:
                        other.execute(sql)
                else:
                    cursor.connection.cursor().execute(sql)
        event.listen(engine, 'after_cursor_execute', listener)
        return listener

    with psycopg.connect(pg) as c:
        victim, victim_md5 = c.execute('select id,md5(raw_text) from raw_resumes order by id limit 1').fetchone()
        other_table = c.execute("select relname from pg_class where relname in ('orders','restaurants') and relkind='r' order by relname limit 1").fetchone()[0]

    plan = variant('integrity-existing')
    listener = inject(f"UPDATE raw_resumes SET raw_text=raw_text||' ' WHERE id={victim}")
    try:
        runner.apply(engine, plan, 'local', receipt)
        check('existing Selection row changed -> import refused', False)
    except runner.PlanError as exc:
        check('existing Selection row changed -> import refused', 'Existing Selection rows changed' in str(exc), exc)
    event.remove(engine, 'after_cursor_execute', listener)
    with psycopg.connect(pg) as c:
        intact = c.execute('select md5(raw_text) from raw_resumes where id=%s', (victim,)).fetchone()[0] == victim_md5
    check('  ... rolled back: row intact, no ledger, counts unchanged', intact and ledger(plan['batch_id']) is None and counts() == base)

    plan = variant('integrity-outside')
    listener = inject(f'UPDATE "{other_table}" SET id=id WHERE id=(select min(id) from "{other_table}")')
    try:
        runner.apply(engine, plan, 'local', receipt)
        check('non-Selection write by the import -> refused', False)
    except runner.PlanError as exc:
        check('non-Selection write by the import -> refused', 'outside the reviewed plan' in str(exc), exc)
    event.remove(engine, 'after_cursor_execute', listener)
    check('  ... rolled back', ledger(plan['batch_id']) is None and counts() == base)

    plan = variant('integrity-final')
    # Another module keeps writing an unrelated table during the import (as Clover orders did on 2026-11-15).
    listener = inject('UPDATE orders SET id=id WHERE id=(select min(id) from orders)', other_transaction=True)
    result = runner.apply(engine, plan, 'local', receipt)
    event.remove(engine, 'after_cursor_execute', listener)
    check('concurrent write by another transaction does not fail the import', result['status'] == 'APPLIED')
    check('  ... pre-commit integrity recorded with 0 non-Selection rows',
          result['integrity']['checked_before_commit'] and result['integrity']['non_selection_rows_written'] == 0
          and 'orders' not in result['integrity']['rows_written_by_table'])
    check('repeat apply is a no-op', runner.apply(engine, plan, 'local', receipt) == {'status': 'ALREADY_APPLIED', 'new_rows': 0})
    verified = runner.verify(engine, plan)
    check('post-commit verify passed', verified['status'] == 'passed' and not verified['imported_rows_changed_later_by_other_transactions'])

    with psycopg.connect(pg, autocommit=True) as other:
        payload = other.execute('select payload from selection_migration_batches where batch_id=%s', (plan['batch_id'],)).fetchone()[0]
        candidate = next(e['id'] for e in payload['inserted'] if e['table'] == 'candidates')
        phone = other.execute('select phone from candidates where id=%s', (candidate,)).fetchone()[0]
        other.execute("UPDATE candidates SET phone=coalesce(phone,'')||' ' WHERE id=%s", (candidate,))
    verified = runner.verify(engine, plan)
    check('later edit by another transaction is reported, not attributed to the import',
          {'table': 'candidates', 'id': candidate, 'state': 'changed'} in verified['imported_rows_changed_later_by_other_transactions']
          and verified['non_selection_rows_written_by_import'] == 0)
    with psycopg.connect(pg, autocommit=True) as other:
        other.execute('UPDATE candidates SET phone=%s WHERE id=%s', (phone, candidate))
        other.execute("UPDATE selection_migration_batches SET payload=payload-'integrity' WHERE batch_id=%s", (plan['batch_id'],))
    try:
        runner.verify(engine, plan)
        check('batch without the pre-commit check is never reported as passed', False)
    except runner.PlanError as exc:
        check('batch without the pre-commit check is never reported as passed', 'pre-commit' in str(exc), exc)
    with psycopg.connect(pg, autocommit=True) as other:
        other.execute('UPDATE selection_migration_batches SET payload=%s WHERE batch_id=%s', (json.dumps(payload), plan['batch_id']))
    engine.dispose()
    print('ALL PASSED' if not failures else f'{len(failures)} FAILED')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
