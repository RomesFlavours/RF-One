"""Menu CRUD, references, location isolation and security in disposable SQLite."""
from pathlib import Path
from uuid import uuid4
import json,sys
import sqlalchemy as sa
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_recipe_editor import build_app
from rfone_data_store.kitchen import recipes
from rfone_data_store.kitchen_configuration import items,save as save_configuration,ConfigurationError
from rfone_data_store.kitchen_menus import menus,entries

def main():
    app,engine=build_app();client=app.test_client();base='/kitchen/menus'
    with engine.begin() as db:
        menus.create(db);entries.create(db)
        db.exec_driver_sql("INSERT INTO locations VALUES (1,'Winter Park')")
        db.execute(items.insert(),dict(id=10,section='MENU_AREA',name='Pasta',normalized_name='pasta'))
        db.execute(recipes.insert(),[dict(id=10,code='D10',name='Pasta dish',kind='dish',category_id=1),dict(id=11,code='Pr11',name='Sauce',kind='preparation',category_id=None)])
    page=client.get(base);assert page.status_code==200 and 'menu-dialog' in page.text and 'data-how-works' in page.text
    assert 'id="menu-location-field" hidden' in page.text
    def save(data):return client.post(base+'/save',data=dict(csrf_token='test-csrf',payload=json.dumps(data)))
    draft=dict(draft_key=str(uuid4()),name='Dinner',entries=[dict(area_id=10,label='Pasta section'),dict(area_id=10,recipe_id=10,label='')])
    result=save(draft);assert result.status_code==200,result.text
    menu=result.json['menu'];mid=menu['id'];assert menu['location_id']==1
    assert menu['entries'][0]['recipe_id'] is None and menu['entries'][1]['label']=='Pasta dish'
    assert save(draft).json['menu']['id']==mid
    assert client.post(base+'/save',data=dict(payload=json.dumps(draft))).status_code==400
    with engine.begin() as db:
        db.exec_driver_sql("INSERT INTO locations VALUES (2,'Mount Dora')")
        db.execute(items.insert(),dict(id=12,section='MENU_AREA',name='Dessert',normalized_name='dessert'))
    assert 'id="menu-location-field" hidden' not in client.get(base).text
    with Session(engine) as db:
        save_configuration(db,'MENU_AREA',item_id=10,name='Pasta',location_id=2)
        db.commit()
    shared=dict(draft,draft_key=str(uuid4()),location_id=2)
    assert save(shared).status_code==200
    for changes in [dict(location_id=999),dict(entries=[dict(area_id=12,recipe_id=10,label='Wrong Category')]),dict(entries=[dict(area_id=10,recipe_id=11,label='Preparation')]),dict(entries=[dict(area_id=10,recipe_id=999,label='Missing recipe')]),dict(entries=[dict(area_id=10,label='')])]:
        bad=dict(draft,draft_key=str(uuid4()),location_id=1,**{})
        bad.update(changes);assert save(bad).status_code==400,changes
    edit=dict(id=mid,revision=menu['revision'],name='Evening',location_id=1,entries=[dict(menu['entries'][1]),dict(area_id=10,label='New label')])
    edited=save(edit);assert edited.status_code==200,edited.text
    saved=edited.json['menu'];assert len(saved['entries'])==2 and saved['entries'][0]['id']==menu['entries'][1]['id']
    assert save(edit).status_code==409
    with engine.begin() as db:db.execute(items.update().where(items.c.id==10).values(archived=True))
    keep=dict(id=mid,revision=saved['revision'],name='Evening',location_id=1,entries=saved['entries'])
    kept=save(keep);assert kept.status_code==200,kept.text
    bad=dict(keep,revision=kept.json['menu']['revision'],entries=[dict(area_id=10,label='New archived area')]);assert save(bad).status_code==400
    payload=dict(revision=kept.json['menu']['revision'])
    archived=client.post(f'{base}/{mid}/archive',data=dict(csrf_token='test-csrf',payload=json.dumps(payload)))
    assert archived.status_code==200 and archived.json['menu']['archived'] and len(archived.json['menu']['entries'])==2
    assert save(dict(keep,revision=archived.json['menu']['revision'])).status_code==400
    with engine.begin() as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(recipes))==2
        db.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
        db.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','RECIPES')")
    assert client.get(base).status_code==403 and save(draft).status_code==403
    assert client.post(f'{base}/{mid}/archive',data=dict(csrf_token='test-csrf',payload='{}')).status_code==403
    print('PASS: menu create/retry/edit/order/archive, labels vs recipes, single/multiple locations, shared areas and recipe Category filtering, invalid/preparation recipes, archived areas, stale saves, CSRF and permissions; recipe records preserved')

if __name__=='__main__':main()
