"""Inspect the live Registry schema; never migrate or change AWS resources.

Run from a network already authorized to reach RDS. Credentials stay in memory.
The PostgreSQL connection enforces read-only transactions from its startup packet.
"""
import argparse
import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import psycopg2
from botocore.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='default')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    store = root / '03 Software/RF-One Data Store'
    sys.path.insert(0, str(store))
    from rfone_data_store import models as m
    from rfone_data_store import student_registry as registry, people_registry as people
    aws = boto3.Session(profile_name=args.profile, region_name='us-east-1')
    cfg = Config(connect_timeout=5, read_timeout=15, retries={'max_attempts': 0})
    identity = aws.client('sts', config=cfg).get_caller_identity()
    if identity['Account'] != '418674484214':
        raise RuntimeError('Unexpected AWS account; no database access attempted.')
    rds = aws.client('rds', config=cfg).describe_db_instances(DBInstanceIdentifier='rfone-dev')['DBInstances'][0]
    credentials = make_url(aws.client('secretsmanager', config=cfg).get_secret_value(
        SecretId='rfone-tips/database-url')['SecretString'])
    if credentials.host != rds['Endpoint']['Address'] or credentials.database != 'rfone':
        raise RuntimeError('Deployed application secret points to an unexpected database.')
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'database': 'rfone-dev/rfone', 'engine_version': rds['EngineVersion'],
              'aws_mutations': False, 'schema_verified': False}
    engine = create_engine('postgresql+psycopg2://', creator=lambda: psycopg2.connect(
        host=rds['Endpoint']['Address'], port=rds['Endpoint']['Port'], dbname='rfone',
        user=credentials.username, password=credentials.password, sslmode='require', connect_timeout=8,
        options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=2000',
        application_name='rfone-training-registry-readonly-audit'))
    try:
        with engine.connect() as c:
            c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            assert c.scalar(text('SHOW transaction_read_only')) == 'on'
            report['transaction_read_only'] = True
            versions = list(c.scalars(text('SELECT version_num FROM alembic_version')))
            report['revisions'] = versions
            parents = {}
            for path in (store / 'migrations/versions').glob('*.py'):
                tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                values = {}
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id in ('revision', 'down_revision'):
                                values[target.id] = ast.literal_eval(node.value)
                if 'revision' in values:
                    parents[values['revision']] = values.get('down_revision')
            report['revision_known'] = len(versions) == 1 and versions[0] in parents
            if versions == ['t9a120261110']:
                report['pending_registry_path'] = ['k9b120261112', 't9b120261112']
            elif versions == ['k9b120261112']:
                report['pending_registry_path'] = ['t9b120261112']
            else:
                report['pending_registry_path'] = None
            i = inspect(c)
            present = set(i.get_table_names())
            errors = []
            if 'employees' not in present or not any(x['name'] == 'id' and str(x['type'].compile(dialect=c.dialect)) == 'INTEGER' for x in i.get_columns('employees')):
                errors.append('Missing/incompatible employees.id prerequisite')
            else:
                report['employee_prerequisite_pk'] = i.get_pk_constraint('employees')['constrained_columns']
                if report['employee_prerequisite_pk'] != ['id']:
                    errors.append('employees.id is not the expected referenced primary key')
            if 'kitchen_recipes' not in present:
                errors.append('Missing kitchen_recipes prerequisite for k9b')
            else:
                kitchen_columns = {x['name']: x for x in i.get_columns('kitchen_recipes')}
                report['elapsed_preparation_column_exists'] = 'elapsed_preparation_minutes' in kitchen_columns
                if versions == ['t9a120261110'] and report['elapsed_preparation_column_exists']:
                    errors.append('k9b column exists before its revision; explicit drift review required')
            # ORM reads select all mapped columns. Check every required name/type.
            models = (m.CandidatePerson, m.RFOneAccount, m.TrainingAccount,
                      people.PersonAccountLink, people.PersonEmployeeLink,
                      registry.PersonQualification, registry.TrainingPersonLink)
            report['tables'] = {}
            added = {'person_account_links', 'person_employee_links', 'person_qualifications', 'training_person_links'}
            for model in models:
                table = model.__table__
                if table.name not in present:
                    report['tables'][table.name] = {'exists': False, 'migration_creates': table.name in added}
                    if table.name not in added:
                        errors.append('Missing prerequisite table: ' + table.name)
                    continue
                columns = {x['name']: x for x in i.get_columns(table.name)}
                report['tables'][table.name] = {
                    'exists': True,
                    'columns': [{'name': x['name'], 'type': str(x['type'].compile(dialect=c.dialect)), 'nullable': x['nullable']} for x in columns.values()],
                    'pk': i.get_pk_constraint(table.name),
                    'unique': i.get_unique_constraints(table.name),
                    'foreign_keys': i.get_foreign_keys(table.name)}
                for col in table.columns:
                    actual = columns.get(col.name)
                    if actual is None:
                        errors.append(f'{table.name}: missing column {col.name}')
                    elif str(actual['type'].compile(dialect=c.dialect)).upper() != str(col.type.compile(dialect=c.dialect)).upper():
                        errors.append(f'{table.name}.{col.name}: type differs from frozen model')
                if table.name in added:
                    expected_pk = set(table.primary_key.columns.keys())
                    if set(i.get_pk_constraint(table.name)['constrained_columns']) != expected_pk:
                        errors.append(table.name + ': incompatible primary key')
                    for col in table.columns:
                        if col.name in columns and columns[col.name]['nullable'] != col.nullable:
                            errors.append(f'{table.name}.{col.name}: incompatible nullability')
                    actual_fk = {(tuple(x['constrained_columns']), x['referred_table'], tuple(x['referred_columns'])) for x in i.get_foreign_keys(table.name)}
                    for fk in table.foreign_key_constraints:
                        expected = (tuple(x.parent.name for x in fk.elements), next(iter(fk.elements)).column.table.name, tuple(x.column.name for x in fk.elements))
                        if expected not in actual_fk:
                            errors.append(table.name + ': missing expected foreign key')
                    actual_unique = {tuple(x['column_names']) for x in i.get_unique_constraints(table.name)}
                    from sqlalchemy import UniqueConstraint
                    for constraint in table.constraints:
                        if isinstance(constraint, UniqueConstraint) and tuple(constraint.columns.keys()) not in actual_unique:
                            errors.append(table.name + ': missing expected unique constraint')
            protected = ('rfone_accounts', 'rfone_account_domain_access', 'rfone_account_domain_item_access',
                         'rfone_training_identity_links', 'candidate_persons', 'training_accounts',
                         'training_student_profiles', 'training_needs', 'training_assignments',
                         'training_attempts', 'training_overall_attempts', 'training_course_revisions',
                         'training_course_assignment_revisions', 'training_course_files', *sorted(added))
            report['protected_fingerprints'] = {}
            for name in protected:
                if name not in present:
                    continue
                digest = hashlib.sha256(); count = 0
                for value in c.scalars(text('SELECT to_jsonb(t)::text FROM "' + name + '" t ORDER BY to_jsonb(t)::text COLLATE "C"')):
                    data = value.encode(); digest.update(len(data).to_bytes(8, 'big')); digest.update(data); count += 1
                report['protected_fingerprints'][name] = {'rows': count, 'sha256': digest.hexdigest()}
            report['errors'] = errors
            report['schema_verified'] = report['revision_known'] and not errors
            report['requires_revision_path_review'] = True
            c.rollback()
    except Exception as exc:
        # Never stringify a driver exception: it may contain connection details.
        report['access_error_type'] = type(exc).__name__
        original = getattr(exc, 'orig', exc)
        report['sqlstate'] = getattr(original, 'pgcode', None)
        detail = str(original).lower()
        report['access_error_category'] = next((label for match, label in (
            ('password authentication failed', 'authentication_failed'),
            ('timeout expired', 'connection_timeout'),
            ('connection timed out', 'connection_timeout'),
            ('read-only transaction', 'read_only_guard_rejected_operation'),
            ('does not exist', 'missing_database_object'),
            ('ssl', 'tls_error')) if match in detail), 'unclassified_driver_error')
        report['access_error'] = 'Database read-only inspection could not complete; no mutation attempted.'
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, default=str, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('schema_verified', 'aws_mutations', 'access_error_type', 'errors') if k in report}))
    return 0 if report['schema_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
