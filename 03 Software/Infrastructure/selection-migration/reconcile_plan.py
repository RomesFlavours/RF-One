"""Refresh a reviewed Selection import plan with explicit identity reconciliations (fix A4).

This is the versioned form of the plan refresh performed by the unversioned
`cutover_import.py` during the 2026-11-15 cutover.  It never writes to a
database: it reads the target (RFONE_MIGRATION_DATABASE_URL, supplied by the
operator, never stored), accepts only the baseline changes and the identity
reconciliations declared in a reviewed spec, runs the import preflight and
writes a new plan with a new checksum.  Applying the plan stays with
`production_import.py apply`, under its own approval gates.

    python reconcile_plan.py --plan parent-plan.json --spec cutover-20261115.reconciliation.json --output plan.json
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import production_import as runner  # noqa: E402


def refresh(c, plan, spec, metadata, document_manifest=None):
    """Return (new plan without checksum, preflight result, baseline changes)."""
    plan = copy.deepcopy(plan)
    parent = plan.pop('plan_sha256')
    changes = []
    for item in plan['baseline_counts']:
        table = metadata.tables[item['table']]
        query = select(text('count(*)')).select_from(table)
        if 'restaurant_id' in item:
            query = query.where(table.c.restaurant_id == item['restaurant_id'])
        actual = c.scalar(query)
        if actual != item['count']:
            changes.append({'table': item['table'], 'before': item['count'], 'after': actual})
            item['count'] = actual
    expected = {x['table']: x['delta'] for x in spec.get('expected_baseline_changes', [])}
    if {x['table']: x['after'] - x['before'] for x in changes} != expected:
        raise runner.PlanError('Target changed differently from the reviewed spec: ' + json.dumps(changes))
    reused = {}
    reconciliations = []
    for item in spec['identity_reconciliations']:
        applications = metadata.tables['applications']
        existing = c.execute(select(applications).where(applications.c.id == item['existing_application_id'])).mappings().one()
        if (existing['candidate_id'], existing['person_id']) != (item['existing_candidate_id'], item['existing_person_id']):
            raise runner.PlanError('Existing application does not match the reviewed identity.')
        local_apps = [x for x in plan['inserts']['applications'] if x['candidate_id'] == item['local_candidate_id']]
        if len(local_apps) != 1 or local_apps[0]['person_id'] != item['local_person_id']:
            raise runner.PlanError('Local application does not match the reviewed identity.')
        if len([x for x in plan['inserts']['candidate_persons'] if x['id'] == item['local_person_id']]) != 1:
            raise runner.PlanError('Local person to reuse is not in the plan exactly once.')
        if document_manifest is not None and item['existing_original_sha256'] not in {
                x['sha256'] for x in document_manifest['objects']}:
            raise runner.PlanError('Existing original CV is not in the verified document manifest.')
        for name, pk in item['anchor_existing']:
            if name not in metadata.tables:
                metadata.reflect(c, only=[name], resolve_fks=False)
            table = metadata.tables[name]
            row = dict(c.execute(select(table).where(table.c.id == pk)).mappings().one())
            plan['anchors'].append({'table': name, 'id': pk, 'before': runner.canonical(row)})
        plan['inserts']['candidate_persons'] = [x for x in plan['inserts']['candidate_persons']
                                                if x['id'] != item['local_person_id']]
        reused[str(item['local_person_id'])] = item['existing_person_id']
        reconciliations.append({key: item[key] for key in (
            'type', 'local_candidate_id', 'existing_candidate_id', 'local_person_id', 'existing_person_id',
            'local_position_id', 'existing_position_id', 'local_original_sha256', 'existing_original_sha256', 'reason')})
    plan['reused_ids'] = {'candidate_persons': reused} if reused else {}
    plan['identity_reconciliation'] = reconciliations
    result = runner.check(c, plan, metadata)
    plan['batch_id'] += spec['batch_suffix']
    plan['refresh'] = {'parent_plan_sha256': parent, 'changes': changes, 'reason': spec['reason']}
    return plan, result, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--document-manifest', type=Path)
    parser.add_argument('--mode', choices=('local', 'production'), default='local')
    args = parser.parse_args()
    if args.output.exists():
        raise runner.PlanError('Refusing to overwrite an existing plan.')
    plan = runner.load_plan(args.plan)
    spec = json.loads(args.spec.read_text(encoding='utf-8'))
    manifest = json.loads(args.document_manifest.read_text(encoding='utf-8')) if args.document_manifest else None
    dsn = os.environ.get('RFONE_MIGRATION_DATABASE_URL')
    if not dsn:
        raise runner.PlanError('Set RFONE_MIGRATION_DATABASE_URL securely; never put credentials in a file.')
    engine = runner.connect_target(dsn, args.mode, 'check', None, plan, False, False)
    try:
        names = sorted({a['table'] for a in plan['anchors']} | {s['table'] for s in plan['baseline_counts']}
                       | {'raw_resumes', 'candidates', 'applications', 'candidate_persons'})
        metadata = MetaData()
        metadata.reflect(engine, only=names, resolve_fks=False)
        with engine.connect() as c:
            new_plan, result, changes = refresh(c, plan, spec, metadata, manifest)
    finally:
        engine.dispose()
    new_plan['plan_sha256'] = runner.digest(new_plan)
    args.output.write_text(json.dumps(new_plan, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'preflight': result, 'changes': changes, 'plan_sha256': new_plan['plan_sha256']}))


if __name__ == '__main__':
    try:
        main()
    except runner.PlanError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
