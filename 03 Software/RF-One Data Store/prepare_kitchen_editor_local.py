"""Apply the additive local Kitchen editor migration without altering recipe facts."""
import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import build_opener,HTTPCookieProcessor
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from import_kitchen_excel import local_engine


def fingerprint(c):
    result={}
    for name,excluded in [('kitchen_recipes',["category_id","revision"]),('kitchen_recipe_components',['component_item_id']),('kitchen_recipe_steps',[]),('kitchen_configuration_items',[]),('suppliers',[])]:
        expr='to_jsonb(t)'+''.join("-'"+field+"'" for field in excluded)
        digest=hashlib.sha256();count=0
        for row in c.execute(sa.text(f'SELECT ({expr})::text FROM {name} t ORDER BY id')).scalars():digest.update(row.encode());count+=1
        result[name]=dict(count=count,sha256=digest.hexdigest())
    return result


def main():
    path=Path(__file__).parent/'migrations/versions/e8b920261110_kitchen_recipe_editor.py'
    spec=importlib.util.spec_from_file_location('recipe_editor_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=local_engine()
    with engine.begin() as c:
        c.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        before=fingerprint(c)
        current=c.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
        if current==[m.down_revision]:
            with Operations.context(MigrationContext.configure(c)):m.upgrade()
            c.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=m.revision,old=m.down_revision))
        elif current!=[m.revision]:raise RuntimeError(f'Unexpected revision {current}; no migration applied')
        assert fingerprint(c)==before
    engine.dispose()
    if '--verify-page' in sys.argv:
        client=build_opener(HTTPCookieProcessor(CookieJar()))
        html=client.open('http://127.0.0.1:5097/kitchen/recipes',timeout=20).read().decode()
        assert 'Recipes and Preparations' in html and html.count('data-kind=')==2
        assert 'id="recipe-form-dialog"' in html and 'id="recipe-composition-dialog"' in html
        assert 'id="recipe-form-help"' in html and 'id="recipe-composition-help"' in html
        options=json.loads(client.open('http://127.0.0.1:5097/kitchen/recipes/options',timeout=20).read())
        assert len(options['components'])==196 and len(options['categories'])==21
        print('PASS: live page has two sections, both editors, contextual modal help, 196 Components and 21 Categories')
    print(json.dumps(dict(revision=m.revision,preserved_counts={name:data['count'] for name,data in before.items()})))


if __name__=='__main__':main()
