"""Independent module, trainer editing, assigned trainee and MyRF read-only."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'RF-One Data Store'))
from test_kitchen_http import make_app
from flask import abort, request
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from rfone_data_store.kitchen import menu_cards, recipes, components, steps, photos, menu_links
from rfone_data_store.kitchen_configuration import items
from rfone_data_store.kitchen_menus import menus,entries
from rfone_data_store.models import RestaurantLocation
from visual_menu_routes import register_visual_menu_routes


def main():
    app,engine=make_app()
    app.config['VM_ROLE']='trainer'
    def account(db):return SimpleNamespace(id=1,status='ACTIVE',username='tester',is_admin=False)
    def csrf():
        if request.form.get('csrf_token')!='test':abort(400)
    register_visual_menu_routes(app,SessionFactory=sessionmaker(engine),load_current_account=account,require_csrf=csrf)
    app.context_processor(lambda:{'csrf_token':lambda:'test'})
    with engine.begin() as db:
        for sql in ('CREATE TABLE restaurants(id INTEGER PRIMARY KEY,name TEXT)',
                    'CREATE TABLE locations(id INTEGER PRIMARY KEY,name TEXT)',
                    'CREATE TABLE acting_identities(id INTEGER PRIMARY KEY)',
                    'CREATE TABLE training_pills(id INTEGER PRIMARY KEY,slug TEXT)',
                    'CREATE TABLE training_needs(id INTEGER PRIMARY KEY,student_account_id INTEGER)',
                    'CREATE TABLE training_assignments(id INTEGER PRIMARY KEY,need_id INTEGER,pill_id INTEGER)'):
            db.exec_driver_sql(sql)
        for table in (items,RestaurantLocation.__table__,menu_cards,recipes,components,steps,photos,menu_links,menus,entries):table.create(db)
        db.exec_driver_sql("INSERT INTO restaurants VALUES (1,'WP'),(2,'MD')")
        for rid in (1,2):
            db.execute(menu_cards.insert().values(restaurant_id=rid,dish_key='shrimp-pistacchio',title='Shrimp & Pistacchio',content_version=1,validation_status='pending',content_json=json.dumps({'restaurant_name':str(rid)})))
        db.execute(recipes.insert().values(id=1,code='D125',name='Shrimp & Pistacchio',kind='dish'))
        db.execute(photos.insert().values(id=1,recipe_id=1,asset_uri='https://example.org/dish.jpg'))
        db.execute(components.insert().values(recipe_id=1,position=1,ingredient_reference='F-Anchovy'))
        db.execute(menu_links.insert().values(restaurant_id=1,dish_key='shrimp-pistacchio',recipe_id=1,standard_photo_id=1))
        db.exec_driver_sql("INSERT INTO training_pills VALUES (1,'visual-menu')")
        db.exec_driver_sql("INSERT INTO locations VALUES (1,'WP'),(2,'MD')")
        db.execute(RestaurantLocation.__table__.insert(),[dict(restaurant_id=1,location_id=1,is_primary=True),dict(restaurant_id=2,location_id=2,is_primary=True)])
        db.execute(items.insert().values(id=10,section='MENU_AREA',name='Pasta',normalized_name='pasta'))
        db.execute(menus.insert(),[dict(id=1,name='WP active',location_id=1,draft_key='a',active=True),dict(id=2,name='MD active',location_id=2,draft_key='b',active=True),dict(id=3,name='WP draft',location_id=1,draft_key='c',active=False)])
        db.execute(entries.insert(),[dict(id=1,menu_id=1,area_id=10,recipe_id=1,label='WP dish',position=1),dict(id=2,menu_id=2,area_id=10,recipe_id=1,label='MD dish',position=1),dict(id=3,menu_id=1,area_id=10,recipe_id=None,label='Daily label',position=2),dict(id=4,menu_id=3,area_id=10,recipe_id=1,label='Draft dish',position=1)])

    def authorization(db,a):
        role=app.config['VM_ROLE']
        return SimpleNamespace(training_account=SimpleNamespace(id=5,role=role) if role else None)
    with patch('training_integration.check_training_authorization',authorization):
        c=app.test_client();path='/visual-menu/locations/1/entries/1'
        home=c.get('/visual-menu')
        assert 'WP active' in home.text and 'MD active' in home.text and 'Daily label' in home.text
        assert 'WP draft' not in home.text and 'Draft dish' not in home.text
        assert c.get('/visual-menu/1/shrimp-pistacchio').status_code==302
        assert c.get('/visual-menu/locations/1/entries/3').status_code==404
        assert c.get('/visual-menu/locations/1/entries/4').status_code==404
        assert c.get('/visual-menu/locations/2/entries/1').status_code==404
        page=c.get(path)
        assert page.status_code==200 and 'Fish' in page.text and '<h1>Visual Menu</h1>' in page.text
        assert '/kitchen' not in page.text and 'Save phrases' not in page.text
        assert 'As a trainer' not in c.get('/visual-menu').text
        assert c.get('/training/visual-menu').location.startswith('/visual-menu?')
        manage='/visual-menu/manage/1/recipes/1'
        assert c.get('/visual-menu/manage').status_code==200
        assert c.get(manage).json['card']['title']=='Shrimp & Pistacchio'
        headings=['id="vm-components"','id="vm-allergens"','id="vm-nutrition"','id="vm-description"','id="vm-characteristics"','id="vm-sales"']
        assert [page.text.index(h) for h in headings]==sorted(page.text.index(h) for h in headings)
        assert 'vm-photo' in page.text and page.text.index('vm-photo')<page.text.index('id="vm-components"')
        assert '<li>Anchovy</li>' in page.text and '<li>Fish</li>' in page.text
        with engine.connect() as db:
            assert db.scalar(sa.select(sa.func.count()).select_from(menu_cards))==2
            assert db.scalar(sa.select(sa.func.count()).select_from(menu_links))==1

        assert 'preparation batch' not in page.text
        payload=dict(csrf_token='test',version=1,description_phrases='Fresh pasta.',sales_phrases='Try our shrimp and pistachio.')
        assert c.post(path+'/phrases',data=payload).status_code==302
        assert c.post(path+'/phrases',data=payload).status_code==409
        assert c.post(path+'/phrases',data={**payload,'csrf_token':'bad'}).status_code==400
        with engine.connect() as db:
            other=json.loads(db.scalar(sa.select(menu_cards.c.content_json).where(menu_cards.c.restaurant_id==2)))
            assert 'sales_phrases' not in other
        with engine.begin() as db:db.execute(components.update().values(ingredient_reference='F-Eggs'))
        assert c.get(path+'/data').json['allergens'][0]['name']=='Eggs'

        fresh='/visual-menu/locations/2/entries/2'
        assert c.post(fresh+'/phrases',data={**payload,'version':0}).status_code==302
        assert c.get(fresh+'/data').json['sales_phrases']==['Try our shrimp and pistachio.']
        with engine.connect() as db:
            new=json.loads(db.scalar(sa.select(menu_cards.c.content_json).where(menu_cards.c.restaurant_id==2,menu_cards.c.dish_key=='recipe-1')))
            assert set(new)=={'description_phrases','sales_phrases'}
        with engine.begin() as db:
            db.execute(menus.update().where(menus.c.id==1).values(active=False))
            db.execute(menus.update().where(menus.c.id==3).values(active=True))
        assert c.get(path).status_code==404 and c.get(path+'/photo').status_code==404
        assert c.get(path+'/data').status_code==404
        assert 'WP draft' in c.get('/visual-menu').text and 'WP active' not in c.get('/visual-menu').text
        with engine.begin() as db:
            db.execute(menus.update().where(menus.c.id==3).values(active=False))
            db.execute(menus.update().where(menus.c.id==1).values(active=True))
        assert c.get(path+'/data').json['description_phrases']==['Fresh pasta.']

        managed=c.get(manage).json['card']
        response=c.post(manage,data={**payload,'version':managed['content_version'],'sales_phrases':'Trainer-managed sales phrase.'})
        assert response.status_code==200,response.text
        assert c.get(path+'/data').json['sales_phrases']==['Trainer-managed sales phrase.']
        assert c.post(manage,data={**payload,'version':managed['content_version']}).status_code==409
        assert c.post(manage,data={**payload,'version':999,'csrf_token':'bad'}).status_code==400
        with engine.begin() as db:
            db.execute(recipes.insert(),[dict(id=2,code='Pr2',name='Preparation',kind='preparation'),dict(id=3,code='D3',name='Future dish',kind='dish')])
        assert c.get('/visual-menu/manage/1/recipes/2').status_code==404
        future='/visual-menu/manage/1/recipes/3'
        assert c.post(future,data={**payload,'version':0}).status_code==200
        assert c.get(future).json['card']['description_phrases']==['Fresh pasta.']
        assert 'Future dish' in c.get('/visual-menu/manage').text
        assert 'Future dish' not in c.get('/visual-menu/manage?restaurant_id=1').text
        assert 'Future dish' in c.get('/visual-menu/manage?restaurant_id=1&menu_id=kitchen').text
        assert c.get('/visual-menu/manage?restaurant_id=1&menu_id=2').status_code==404
        assert c.get('/visual-menu/manage?restaurant_id=1&menu_id=3').status_code==200
        assert c.get('/visual-menu/manage?menu_id=1').status_code==400

        assert 'Future dish' not in c.get('/visual-menu').text
        app.config['VM_ROLE']='student'
        assert c.get(path).status_code==403
        with engine.begin() as db:
            db.exec_driver_sql('INSERT INTO training_needs VALUES (1,5)')
            db.exec_driver_sql('INSERT INTO training_assignments VALUES (1,1,1)')
        page=c.get(path)
        assert page.status_code==200 and 'Save phrases' not in page.text
        assert c.post(path+'/phrases',data=payload).status_code==403
        assert c.get('/training/visual-menu').location.startswith('/visual-menu?')
        assert c.get('/visual-menu/manage').status_code==403
        assert c.get(manage).status_code==403
        assert c.get(manage+'/photo').status_code==403
        assert c.post(manage,data=payload).status_code==403

        app.config['VM_ROLE']=None
        with engine.begin() as db:db.exec_driver_sql("INSERT INTO rfone_account_domain_access VALUES (1,'MYRF',1,'ALL')")
        page=c.get(path+'?from=myrf')
        assert page.status_code==200 and 'Save phrases' not in page.text
        assert c.post(path+'/phrases?from=myrf',data=payload).status_code==403
        assert c.get('/visual-menu/manage?from=myrf').status_code==403
        assert c.get(manage+'?from=myrf').status_code==403
        assert c.post(manage+'?from=myrf',data=payload).status_code==403

        assert c.get(path).status_code==403
        assert c.get('/myrf/visual-menu').status_code==302
        assert c.get('/visual-menu/3/shrimp-pistacchio?from=myrf').status_code==404
    engine.dispose()
    print('PASS: active-only grouping/labels/membership, no writes on reads, live Kitchen projection, legacy phrase preservation, new phrase-only storage, switch/archive guards, separate trainer management including future dishes, CSRF/conflict, role-aware course redirects, assigned trainee and MyRF read-only/management denial, no Kitchen grant dependency')


if __name__=='__main__':main()
