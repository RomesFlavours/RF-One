"""Explicit additive schema/content publication; never runs at application startup."""
from pathlib import Path
import hashlib,importlib.util,json,os,sys
from sqlalchemy import create_engine,select,text,func
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from rfone_data_store import models as m
from rfone_data_store.training import courses,service


def fingerprint(connection,table):
    rows=connection.execute(text('SELECT to_jsonb(t)::text FROM '+table+' t ORDER BY to_jsonb(t)::text COLLATE "C"')).scalars()
    digest=hashlib.sha256();count=0
    for value in rows:
        data=value.encode();digest.update(len(data).to_bytes(8,'big'));digest.update(data);count+=1
    return dict(rows=count,sha256=digest.hexdigest())


def publish(engine):
    path=Path(__file__).resolve().parents[1]/'RF-One Data Store/migrations/versions/t9a120261110_publish_training_aws.py'
    if not path.exists():path=Path(__file__).resolve().parents[1]/'03 Software/RF-One Data Store/migrations/versions/t9a120261110_publish_training_aws.py'
    spec=importlib.util.spec_from_file_location('training_release_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    protected=('rfone_accounts','rfone_account_domain_access','rfone_training_identity_links','training_accounts','training_assignments','training_questions','training_attempts','training_overall_attempts')
    with engine.begin() as connection:
        connection.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions=connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions not in ([migration.down_revision],[migration.revision]):
            raise RuntimeError('Unexpected AWS schema: '+repr(versions))
        before={name:fingerprint(connection,name) for name in protected}
        with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
        with Session(bind=connection,join_transaction_mode='create_savepoint') as db:
            # These reads verify compatibility with the deployed shared identity schema.
            db.execute(select(m.RFOneAccount).limit(0));db.execute(select(m.RFOneAccountDomainAccess).limit(0))
            db.execute(select(m.TrainingAccount).limit(0))
            db.execute(text('LOCK TABLE training_pills IN SHARE ROW EXCLUSIVE MODE'))
            visual=db.scalar(select(m.TrainingPill).where(m.TrainingPill.slug=='visual-menu'))
            if visual is None:
                visual=m.TrainingPill(slug='visual-menu',title='Visual Menu',learning_objectives='Learn each restaurant’s dishes, ingredients, allergens and presentation using the Visual Menu.',content_version=1)
                db.add(visual);db.flush()
            courses.initialize_visual_menu(db)
            db.execute(text('INSERT INTO training_retired_pills(pill_id) SELECT id FROM training_pills WHERE slug<>:slug ON CONFLICT(pill_id) DO NOTHING'),dict(slug='visual-menu'))
            db.execute(text('DELETE FROM training_retired_pills WHERE pill_id=:id'),dict(id=visual.id))
            available=[p.slug for p in service.list_all_pills(db)]
            if available!=['visual-menu']:raise RuntimeError('Unexpected initial course catalog.')
            db.commit()
        after={name:fingerprint(connection,name) for name in protected}
        if before!=after:raise RuntimeError('Protected account/history data changed; publication rolled back.')
        if versions==[migration.down_revision]:
            connection.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
        count=connection.scalar(text('SELECT count(*) FROM training_retired_pills'))
    return dict(revision=migration.revision,available_courses=['Visual Menu'],withdrawn_dish_entries=count,protected_data_unchanged=True,protected_fingerprints=after)


if __name__=='__main__':
    engine=create_engine(os.environ['RFONE_DATABASE_URL'])
    print('TRAINING_PUBLISH='+json.dumps(publish(engine)),flush=True)
    engine.dispose()
