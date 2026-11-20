"""Configuration CRUD and account/CSRF boundaries, in disposable SQLite memory."""
import sys
from pathlib import Path
from flask import abort, request
import sqlalchemy as sa
from sqlalchemy.orm import Session

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_http import make_app
from rfone_data_store import kitchen_configuration as config, models as m
from rfone_data_store.kitchen_menus import menus,entries


def main():
    def csrf():
        if request.form.get('csrf_token') != 'test-csrf':
            abort(400)
    app, engine=make_app(require_csrf=csrf)
    app.context_processor(lambda:{'csrf_token':lambda:'test-csrf'})
    with engine.begin() as c:
        c.exec_driver_sql('PRAGMA foreign_keys=ON')
        c.exec_driver_sql('CREATE TABLE legal_entities (id INTEGER PRIMARY KEY)')
        c.exec_driver_sql('CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
        c.exec_driver_sql("INSERT INTO locations VALUES (1,'Winter Park')")
        for table in (m.Restaurant.__table__,m.Supplier.__table__,m.SupplierAlias.__table__,config.items):
            table.create(c)
        menus.create(c);entries.create(c)
        c.execute(m.Restaurant.__table__.insert(),[dict(id=1,name='Winter Park'),dict(id=2,name='Mount Dora')])
    client=app.test_client()
    path='/kitchen/configuration'
    response=client.get(path)
    assert response.status_code==200 and response.text.count('data-config-section=')==6
    assert 'href="/kitchen/configuration"' in client.get('/kitchen/dashboard').text
    assert not any('open' in tag.split('>')[0] for tag in response.text.split('<details')[1:])
    assert 'data-how-works' in response.text and 'id="kitchen-configuration"' in response.text
    assert 'id="location-MENU_AREA"' not in response.text and 'class="config-row-location"' not in response.text
    def post(section,action,**data):
        return client.post(f'{path}/{section}/{action}',data=dict(csrf_token='test-csrf',**data))
    for section in config.REFERENCE_SECTIONS:
        assert post(section,'save',name='Dinner').status_code==303
        with engine.connect() as c:
            item_id=c.scalar(sa.select(config.items.c.id).where(config.items.c.section==section))
        assert post(section,'save',name=' dinner ').status_code==400
        assert post(section,'save',name='Evening',item_id=item_id).status_code==303
        assert post(section,'archive',item_id=item_id).status_code==303
        assert post(section,'save',name='evening').status_code==400
        with engine.connect() as c:
            row=c.execute(sa.select(config.items).where(config.items.c.id==item_id)).mappings().one()
            assert row['archived'] and row['name']=='Evening'
            if section=='MENU_AREA':assert row['location_id'] is None
    with engine.begin() as c:c.exec_driver_sql("INSERT INTO locations VALUES (2,'Mount Dora')")
    assert 'id="location-MENU_AREA"' not in client.get(path).text
    assert post('MENU_AREA','save',name='Shared Area').status_code==303
    assert post('MENU_AREA','save',name=' shared area ',location_id=2).status_code==400
    before=client.get(path).text
    assert post('MENU_TYPE','save',name='   ').status_code==400
    assert post('MENU_TYPE','save',name='X'*256).status_code==400
    assert client.post(f'{path}/MENU_TYPE/save',data={'name':'No CSRF'}).status_code==400
    assert post('SUPPLIER','save',name='Supplier').status_code==400
    assert post('SUPPLIER','save',name='Supplier',restaurant_id=1).status_code==303
    assert post('SUPPLIER','save',name='supplier',restaurant_id=1).status_code==400
    assert post('SUPPLIER','save',name='Supplier',restaurant_id=2).status_code==303
    with Session(engine) as db:
        supplier_id=db.scalar(sa.select(m.Supplier.id).where(m.Supplier.restaurant_id==1))
    assert post('SUPPLIER','save',name='Renamed',item_id=supplier_id).status_code==303
    assert post('SUPPLIER','save',name='Supplier',restaurant_id=1).status_code==400
    assert post('SUPPLIER','archive',item_id=supplier_id).status_code==303
    with Session(engine) as db:
        assert db.get(m.Supplier,supplier_id).status=='INACTIVE'
        assert db.scalar(sa.select(m.SupplierAlias.alias_name).where(m.SupplierAlias.supplier_id==supplier_id))=='Supplier'
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
        c.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','DASHBOARD')")
    assert client.get(path).status_code==403
    assert post('MENU_TYPE','save',name='Denied').status_code==403
    assert post('MENU_TYPE','archive',item_id=1).status_code==403
    assert '/kitchen/configuration' not in client.get('/kitchen/dashboard').text
    with engine.begin() as c:
        c.exec_driver_sql("UPDATE rfone_account_domain_item_access SET item_code='CONFIGURATION'")
    assert client.get('/kitchen').location.endswith(path)
    assert client.get(path).status_code==200
    assert client.get('/kitchen/recipes').status_code==403
    engine.dispose()
    print('PASS: configuration CRUD; shared menu areas, location-independent names, archived duplicates; Supplier reuse; CSRF and permissions')


if __name__=='__main__':
    main()
