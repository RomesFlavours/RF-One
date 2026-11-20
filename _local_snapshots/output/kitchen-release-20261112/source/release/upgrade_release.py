"""Explicit transactional Kitchen upgrade/check; never invoked during app startup."""
from pathlib import Path
import importlib.util,json,os,sys
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
ROOT=Path('/app');sys.path.insert(0,str(ROOT/'RF-One Data Store'))
path=ROOT/'RF-One Data Store/migrations/versions/k9g120261112_kitchen_aws_release.py'
spec=importlib.util.spec_from_file_location('kitchen_release_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)

def fingerprints(db):
    tables=db.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version' ORDER BY tablename")).scalars().all()
    # Hash original columns only: new nullable fields must not change old facts.
    result={}
    for table in tables:
        if table in ('kitchen_menus','kitchen_menu_entries'):continue
        exclude=" - 'elapsed_preparation_minutes'" if table=='kitchen_recipes' else " - 'location_id'" if table=='kitchen_configuration_items' else ''
        if table.startswith('kitchen_') or table.startswith('rfone_account') or table in ('locations','restaurants','suppliers','supplier_aliases') or 'profile' in table:
            result[table]=db.execute(sa.text('SELECT count(*),md5(COALESCE(string_agg(value,\'\' ORDER BY value),\'\')) FROM (SELECT (to_jsonb(t)'+exclude+')::text AS value FROM "'+table+'" t) q')).one()._asdict()
    return result

def main():
    check='--check' in sys.argv
    engine=sa.create_engine(os.environ['RFONE_DATABASE_URL'],isolation_level='REPEATABLE READ')
    with engine.connect() as db:
        transaction=db.begin()
        try:
            db.execute(sa.text("SET LOCAL lock_timeout='15s'"));db.execute(sa.text("SET LOCAL statement_timeout='90s'"))
            db.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
            versions=db.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
            assert versions in ([migration.down_revision],[migration.revision]),'Unexpected AWS revision: '+repr(versions)
            before=fingerprints(db)
            if versions==[migration.down_revision]:
                with Operations.context(MigrationContext.configure(db)):migration.upgrade()
                db.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
            from rfone_data_store.kitchen import recipes,components,steps,photos,menu_links
            from rfone_data_store.kitchen_configuration import items
            from rfone_data_store.kitchen_menus import menus,entries
            for table in (recipes,components,steps,photos,menu_links,items,menus,entries):db.execute(sa.select(table).limit(0))
            assert fingerprints(db)==before,'Existing Kitchen/identity/directory facts changed'
            # PostgreSQL constraints must agree with the actual runtime models.
            indexes=sa.inspect(db).get_indexes('kitchen_menus');assert any(i['name']=='uq_kitchen_active_menu_location' and i['unique'] for i in indexes)
            # Render the exact production app with an already-authorized account.
            # All requests are GETs; its sessions share this test transaction.
            sys.path.insert(0,str(ROOT/'RF-One Web'))
            import db as web_db
            from sqlalchemy.orm import sessionmaker
            web_db.SessionFactory=sessionmaker(bind=db)
            from kitchen_cloud import app
            from rfone_data_store import models as models,rfone_web_session as shared
            from kitchen_routes import allowed_tabs
            with web_db.SessionFactory() as session:
                candidates=session.scalars(sa.select(models.RFOneAccount).where(models.RFOneAccount.status=='ACTIVE')).all()
                account=next((a for a in candidates if len(allowed_tabs(session,a))==4),None)
                assert account is not None,'No existing account authorized for all Kitchen tabs; no grants created'
                aid,version=account.id,account.session_version
            app.config['TESTING']=True
            client=app.test_client()
            with client.session_transaction() as state:
                state[shared.SESSION_ACCOUNT_KEY]=aid;state[shared.SESSION_VERSION_KEY]=version
            pages={}
            for path in ('/kitchen/dashboard','/kitchen/recipes','/kitchen/configuration','/kitchen/menus'):
                response=client.get(path,base_url='https://localhost');assert response.status_code==200,(path,response.status_code)
                assert b'data-how-works' in response.data;pages[path]=response.status_code
            assert fingerprints(db)==before,'Read-only page checks changed persistent facts'
            if check:transaction.rollback()
            else:transaction.commit()
            print('KITCHEN_RESULT='+json.dumps(dict(mode='rolled_back_check' if check else 'committed',revision=migration.revision,preserved=before,pages=pages,verified=True),default=str),flush=True)
        except BaseException:
            transaction.rollback();raise
    engine.dispose()

if __name__=='__main__':main()
