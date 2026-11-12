"""Activation replaces only the current location's active menu; isolated SQLite."""
from pathlib import Path
from uuid import uuid4
import sys,json
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_recipe_editor import build_app
from rfone_data_store.kitchen_menus import menus,entries,active_for_location

def main():
    app,engine=build_app();client=app.test_client();base='/kitchen/menus'
    with engine.begin() as db:
        menus.create(db);entries.create(db)
        db.exec_driver_sql("INSERT INTO locations VALUES (1,'WP'),(2,'MD')")
    def post(path,payload):return client.post(base+path,data=dict(csrf_token='test-csrf',payload=json.dumps(payload)))
    def create(name,location):
        response=post('/save',dict(name=name,location_id=location,draft_key=str(uuid4()),entries=[]))
        assert response.status_code==200,response.text
        assert not response.json['menu']['active'];return response.json['menu']
    def activate(menu):return post(f"/{menu['id']}/activate",dict(revision=menu['revision']))
    a=create('WP first',1);b=create('WP second',1);c=create('MD',2)
    ar=activate(a);assert ar.status_code==200 and ar.json['menu']['active'];a=ar.json['menu']
    cr=activate(c);assert cr.status_code==200;c=cr.json['menu']
    br=activate(b);assert br.status_code==200;b=br.json['menu']
    states={m['id']:m for m in br.json['menus']}
    assert not states[a['id']]['active'] and states[b['id']]['active'] and states[c['id']]['active']
    assert activate(a).status_code==409
    # The database also rejects callers bypassing the service.
    try:
        with engine.begin() as db:db.execute(menus.update().where(menus.c.id==a['id']).values(active=True))
    except IntegrityError:pass
    else:raise AssertionError('Database allowed two active menus at one location')
    try:
        with engine.begin() as db:db.execute(menus.update().where(menus.c.id==b['id']).values(archived=True))
    except IntegrityError:pass
    else:raise AssertionError('Database allowed an active archived menu')
    archived=post(f"/{b['id']}/archive",dict(revision=b['revision']));assert archived.status_code==200
    assert not archived.json['menu']['active']
    assert activate(archived.json['menu']).status_code==400
    with Session(engine) as db:
        assert active_for_location(db,1) is None and active_for_location(db,2)['id']==c['id']
    a=states[a['id']];a=activate(a).json['menu']
    moved=post('/save',dict(id=a['id'],revision=a['revision'],name=a['name'],location_id=2,entries=[]))
    assert moved.status_code==200 and not moved.json['menu']['active']
    assert next(m for m in moved.json['menus'] if m['id']==c['id'])['active']
    assert client.post(f"{base}/{a['id']}/activate",data=dict(payload='{}')).status_code==400
    with engine.begin() as db:
        db.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
        db.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','RECIPES')")
    assert activate(c).status_code==403
    print('PASS: drafts, activation replacement, independent WP/MD, stale saves, unique DB constraint, archived exclusion, archive clearing, active-menu reader, move-to-draft, CSRF and permissions')

if __name__=='__main__':main()
