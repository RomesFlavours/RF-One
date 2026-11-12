"""Local-only schema extension and the two explicitly requested Recipe Type values."""
import importlib.util
import json
import sys
from pathlib import Path
from urllib.request import build_opener,HTTPCookieProcessor
from http.cookiejar import CookieJar
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from import_kitchen_excel import local_engine
from rfone_data_store.kitchen_configuration import items, save, normalize


def main():
    path=Path(__file__).parent/'migrations/versions/e7a820261110_kitchen_recipe_types.py'
    spec=importlib.util.spec_from_file_location('recipe_types_migration',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=local_engine()
    protected=('kitchen_recipes','kitchen_recipe_components','kitchen_recipe_steps','suppliers')
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
            db.execute(sa.text('LOCK TABLE kitchen_configuration_items IN ACCESS EXCLUSIVE MODE'))
            before={t:db.scalar(sa.text(f'SELECT count(*) FROM {t}')) for t in protected}
            old=[dict(r) for r in db.execute(sa.select(items).where(items.c.section!='RECIPE_TYPE').order_by(items.c.id)).mappings()]
            current=db.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
            if current==[m.down_revision]:
                with Operations.context(MigrationContext.configure(db.connection())):m.upgrade()
                db.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=m.revision,old=m.down_revision))
            elif current!=[m.revision]:
                raise RuntimeError(f'Unexpected revision: {current}; no change applied')
            for name in ('Ricetta','Preparazione'):
                existing=db.scalar(sa.select(items.c.id).where(items.c.section=='RECIPE_TYPE',items.c.normalized_name==normalize(name)))
                if existing is None:save(db,'RECIPE_TYPE',name=name)
            after=[dict(r) for r in db.execute(sa.select(items).where(items.c.section!='RECIPE_TYPE').order_by(items.c.id)).mappings()]
            assert old==after
            assert before=={t:db.scalar(sa.text(f'SELECT count(*) FROM {t}')) for t in protected}
        actual=db.execute(sa.select(items.c.name,items.c.archived).where(items.c.section=='RECIPE_TYPE').order_by(items.c.id)).all()
        assert {'Ricetta','Preparazione'}<={r.name for r in actual}
    engine.dispose()
    if '--verify-page' in sys.argv:
        response=build_opener(HTTPCookieProcessor(CookieJar())).open('http://127.0.0.1:5097/kitchen/configuration',timeout=20)
        html=response.read().decode('utf-8')
        assert html.count('data-config-section=')==6
        assert 'data-config-section="RECIPE_TYPE"' in html and 'value="Ricetta"' in html and 'value="Preparazione"' in html
        assert 'Configuration contains six lists' in html
        print('PASS: live local Configuration shows the sixth section, both values and updated How Works')
    print(json.dumps(dict(revision=m.revision,recipe_types=[dict(name=r.name,archived=r.archived) for r in actual],protected_counts=before),ensure_ascii=False))


if __name__=='__main__':main()
