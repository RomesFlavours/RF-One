"""Real HTTP/editor invariants in isolated SQLite memory; no local database writes."""
import copy
import json
import sys
from pathlib import Path
from uuid import uuid4
from flask import abort,request
import sqlalchemy as sa
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_http import make_app
from rfone_data_store import kitchen_configuration as cfg
from rfone_data_store.kitchen import recipes,components,steps,photos,menu_cards,menu_links


def build_app():
    def csrf():
        if request.form.get('csrf_token')!='test-csrf':abort(400)
    app,engine=make_app(require_csrf=csrf)
    app.context_processor(lambda:{'csrf_token':lambda:'test-csrf'})
    with engine.begin() as c:
        c.exec_driver_sql('PRAGMA foreign_keys=ON')
        c.exec_driver_sql('CREATE TABLE acting_identities(id INTEGER PRIMARY KEY)')
        c.exec_driver_sql('CREATE TABLE restaurants(id INTEGER PRIMARY KEY)')
        c.exec_driver_sql('CREATE TABLE locations(id INTEGER PRIMARY KEY, name TEXT)')
        for table in (cfg.items,recipes,components,steps,photos,menu_cards,menu_links):table.create(c)
        c.execute(cfg.items.insert(),[dict(id=1,section='CATEGORY',name='Pasta',normalized_name='pasta'),dict(id=2,section='COMPONENT',name='Oil',normalized_name='oil')])
    return app,engine


def main():
    app,engine=build_app()
    client=app.test_client();base='/kitchen/recipes'
    html=client.get(base).text
    assert html.count('data-kind=')==2 and 'recipe-form-dialog' in html and 'recipe-composition-help' in html
    def meta(**data):return client.post(base+'/save',data=dict(csrf_token='test-csrf',**data))
    def save(rid,data):return client.post(f'{base}/{rid}/composition',data=dict(csrf_token='test-csrf',payload=json.dumps(data)))
    draft=str(uuid4());new=meta(name='Dish',kind='dish',category_id='1',draft_key=draft,actual_work_minutes='8')
    assert new.status_code==200,new.text
    rid=new.json['recipe']['id']
    assert meta(name='Dish',kind='dish',category_id='1',draft_key=draft).json['recipe']['id']==rid
    prep=meta(name='Base',kind='preparation',draft_key=str(uuid4())).json['recipe']['id']
    assert meta(name='Wrong category',kind='dish',category_id='2',draft_key=str(uuid4())).status_code==400
    assert client.post(base+'/save',data=dict(name='No CSRF')).status_code==400
    data=dict(revision=1,work_minutes='8',rows=[dict(component='id:2',grams='100',instructions='Pan'),dict(component='id:2',grams='150',instructions='Repeat'),dict(preparation='id:'+str(prep),grams='200',instructions='Mix'),dict(instructions='Cook')])
    saved=save(rid,data);assert saved.status_code==200,saved.text
    invalid=copy.deepcopy(saved.json);invalid['revision']=invalid['recipe']['revision']
    invalid['rows'][0]['preparation']='id:'+str(prep)
    rejected=save(rid,invalid);assert rejected.status_code==400 and 'never both' in rejected.json['error']
    assert client.get(f'{base}/{rid}/data').json['recipe']['revision']==saved.json['recipe']['revision']
    assert len(saved.json['rows'])==4 and saved.json['work_minutes']=='8.0000'
    with engine.connect() as c:
        assert c.scalar(sa.select(recipes.c.ingredient_weight_g).where(recipes.c.id==rid))==450
        assert c.scalar(sa.select(sa.func.count()).select_from(components))==3
    stale=save(rid,data);assert stale.status_code==409
    changed=copy.deepcopy(saved.json);changed['revision']=changed['recipe']['revision'];changed['rows'][0]['grams']='110'
    updated=save(rid,changed);assert updated.status_code==200,updated.text
    assert updated.json['rows'][0]['id']==saved.json['rows'][0]['id']
    same=copy.deepcopy(updated.json);same['revision']=same['recipe']['revision'];assert save(rid,same).json['recipe']['revision']==same['revision']
    bad=copy.deepcopy(same);bad['rows'][0]['grams']='-1';assert save(rid,bad).status_code==400
    bad=copy.deepcopy(same);bad['rows'].append(copy.deepcopy(bad['rows'][0]));assert save(rid,bad).status_code==400
    deleted=copy.deepcopy(same);deleted['rows'].pop(1)
    done=save(rid,deleted);assert done.status_code==200,done.text
    with engine.connect() as c:assert c.scalar(sa.select(recipes.c.ingredient_weight_g).where(recipes.c.id==rid))==310
    # A -> B, then reject B -> A and direct self-use.
    other=meta(name='Other base',kind='preparation',draft_key=str(uuid4())).json['recipe']['id']
    assert save(prep,dict(revision=1,rows=[dict(preparation='id:'+str(other),grams='10')])).status_code==200
    assert save(other,dict(revision=1,rows=[dict(preparation='id:'+str(prep),grams='10')])).status_code==400
    assert save(other,dict(revision=1,rows=[dict(preparation='id:'+str(other),grams='10')])).status_code==400
    # Imported unresolved reference + duplicated step + standalone instruction survive a no-op save.
    with engine.begin() as c:
        legacy=c.execute(recipes.insert().values(code='LEGACY',name='Imported',kind='dish',total_cost=12).returning(recipes.c.id)).scalar_one()
        c.execute(components.insert().values(recipe_id=legacy,position=1,ingredient_reference='Unknown original',quantity=5,notes='Original',source_row=20,cost=2))
        c.execute(steps.insert(),[dict(recipe_id=legacy,position=1,instruction='Original',source_row=20),dict(recipe_id=legacy,position=2,instruction='Finish',source_row=21)])
    data=client.get(f'{base}/{legacy}/data').json
    assert len(data['rows'])==2 and data['rows'][0]['component']=='legacy'
    data['revision']=data['recipe']['revision'];assert save(legacy,data).status_code==200
    with engine.connect() as c:assert c.scalar(sa.select(recipes.c.total_cost).where(recipes.c.id==legacy))==12
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
        c.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','DASHBOARD')")
    assert all(client.get(url).status_code==403 for url in [base,base+'/options',f'{base}/{rid}/data'])
    assert save(rid,same).status_code==403 and meta(name='Denied').status_code==403
    engine.dispose()
    print('PASS: page/modals, create retry, Category validation, repeated lines, add/edit/remove, grams vs minutes, stale saves, no-op preservation, imported steps, cycles, CSRF and read/write permissions')


if __name__=='__main__':
    if '--serve' in sys.argv:
        port=int(sys.argv[sys.argv.index('--port')+1]) if '--port' in sys.argv else 5098
        app,engine=build_app()
        if '--upload-dir' in sys.argv:app.config['KITCHEN_PLATING_UPLOAD_DIR']=sys.argv[sys.argv.index('--upload-dir')+1]
        app.run(host='127.0.0.1',port=port,threaded=False,use_reloader=False)
    else:main()
