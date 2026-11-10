import sys
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap  # noqa: F401
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from rfone_data_store import models as m
from app import create_app
from store import Board, Ticket, now, release, save_ticket
from sync import run_cycle

VIEW, RELEASE, SECRET = 'v'*40, 'r'*40, 's'*40


class Clover:
    merchant_id = 'merchant'
    fail_lines = False
    lines = None
    def __init__(self):
        stamp = int((now()-timedelta(minutes=2)).timestamp()*1000)
        self.orders = [{'id':'order-1','title':'#3 - OUTSIDE','createdTime':stamp,
                        'modifiedTime':stamp,'state':'open'}]
        self.lines = [{'id':'line-1','name':'Pasta <script>alert(1)</script>',
                       'binName':'GUEST 1','unitQty':2000,'note':'No salt',
                       'modifications':{'elements':[{'id':'mod-1','name':'No cheese'}]}}]
        self.paths = []

    def get(self, path, params=None):
        self.paths.append(path)
        data = {'id':'merchant'}
        if path.endswith('/orders'):
            data = {'elements':self.orders}
        elif path.endswith('/line_items'):
            if self.fail_lines:
                return SimpleNamespace(ok=False, status_code=503, error='unavailable', data=None)
            data = {'elements':self.lines}
        return SimpleNamespace(ok=True, status_code=200, error=None, data=data)


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread':False})
        m.Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.factory() as db:
            db.add(m.SourceSystem(id=1,code='CLOVER',name='Clover'))
            db.add(m.Merchant(id=1,name='Restaurant'))
            db.flush()
            db.add(m.Location(id=1,merchant_id=1,source_system_id=1,source_location_id='merchant',
                              name='Restaurant',timezone='America/New_York'))
            db.add(m.Location(id=2,merchant_id=1,source_system_id=1,source_location_id='other',
                              name='Other',timezone='America/New_York'))
            db.flush()
            db.add(Board(location_id=1,since=now()-timedelta(hours=5),visible_count=6))
            db.add(Board(location_id=2,since=now()-timedelta(hours=5),visible_count=6))
            db.commit()
        self.app = create_app(self.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE,local=True)
        self.client = self.app.test_client()
        self.api = {'Authorization':'Bearer '+RELEASE}
        self.clover = Clover()

    def tearDown(self):
        self.engine.dispose()

    def sync(self):
        with self.factory() as db:
            return run_cycle(db,1,self.clover)

    def test_order_only_sync_and_guest_details(self):
        self.sync()
        data = self.client.get('/api/locations/1/orders',headers=self.api).json
        self.assertEqual(data['total'],1)
        line = data['orders'][0]['lines'][0]
        self.assertEqual((line['guest'],line['quantity'],line['modifiers']),('GUEST 1',2,['No cheese']))
        self.assertFalse(any('/payments' in p or '/shifts' in p or '/employees' in p for p in self.clover.paths))
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(m.SourceRecord)))),2)
            self.assertIsNone(db.scalars(select(m.IngestionRun).where(m.IngestionRun.lock_key.is_not(None))).first())

    def test_release_is_persistent_idempotent_and_freezes_archive(self):
        self.sync()
        path = '/api/locations/1/orders/order-1/release'
        self.assertFalse(self.client.post(path,headers=self.api,json={'released_by':'tablet'}).json['already_released'])
        self.assertTrue(self.client.post(path,headers=self.api,json={'released_by':'retry'}).json['already_released'])
        self.clover.lines[0]['name'] = 'Changed after release'
        self.sync()
        self.assertEqual(self.client.get('/api/locations/1/orders',headers=self.api).json['total'],0)
        with self.factory() as db:
            ticket = db.get(Ticket,(1,'order-1'))
            self.assertEqual(ticket.released_by,'tablet')
            self.assertNotEqual(ticket.payload['lines'][0]['name'],'Changed after release')

    def test_failed_read_does_not_advance_or_erase(self):
        self.sync()
        with self.factory() as db:
            last = db.get(Board,1).last_sync
        self.clover.fail_lines = True
        with self.assertRaises(Exception): self.sync()
        with self.factory() as db:
            self.assertEqual(db.get(Board,1).last_sync,last)
            self.assertIsNotNone(db.get(Board,1).sync_error)
            self.assertEqual(db.get(Ticket,(1,'order-1')).payload['lines'][0]['name'],self.clover.lines[0]['name'])
        self.clover.fail_lines = False
        self.assertTrue(self.sync())

    def test_removed_lines_disappear_from_live_snapshot(self):
        self.sync()
        self.clover.lines = []
        self.sync()
        self.assertEqual(self.client.get('/api/locations/1/orders',headers=self.api).json['orders'],[])

    def test_beverage_categories_and_exit(self):
        from kitchen_filter import kitchen_payload
        lines = [{'id':'a','name':'Chicken in wine sauce'}, {'id':'b','name':'Wine'},
                 {'id':'c','name':'Beer'}, {'id':'d','name':'Still Water'}]
        payload = kitchen_payload({'lines':lines},{'a':['Meat & Fish'],
            'b':['Wine Red - Bottle'],'c':['Beer'],'d':['Beverages']})
        self.assertEqual(payload['lines'],[{**lines[0],'service_timing':[],'allergy':False}])
        self.sync()
        with self.factory() as db:
            db.add(m.Item(id=1,location_id=1,name='Drink'))
            db.add(m.Category(id=1,location_id=1,name='Beverages'))
            db.flush()
            db.add(m.ItemCategory(item_id=1,category_id=1))
            db.scalars(select(m.OrderItem)).first().item_id=1
            db.commit()
        self.assertEqual(self.client.get('/api/locations/1/orders',headers=self.api).json['total'],0)
        with self.factory() as db:
            self.assertIsNotNone(db.scalars(select(m.OrderItem)).first())
        self.assertEqual(self.client.get('/exit',headers=self.api).status_code,200)
        self.assertIn('href="/exit"',self.client.get('/board/1',headers=self.api).get_data(as_text=True))

    def test_wrong_merchant_does_not_import(self):
        self.clover.merchant_id = 'wrong'
        with self.assertRaises(ValueError): self.sync()
        with self.factory() as db:
            self.assertIsNone(db.get(Board,1).last_sync)

    def test_only_when_serve_modifiers_define_timing(self):
        self.sync()
        with self.factory() as db:
            group=m.ModifierGroup(id=1,location_id=1,name='When Serve')
            db.add(group); db.flush()
            db.add(m.Modifier(id=1,location_id=1,modifier_group_id=1,name='First'))
            db.flush()
            mod=db.scalars(select(m.OrderItemModifier)).first()
            mod.modifier_id=1; mod.name_raw='First'; db.commit()
        data=self.client.get('/api/locations/1/orders',headers=self.api).json
        self.assertEqual(data['orders'][0]['lines'][0]['service_timing'],['First'])
        with self.factory() as db:
            db.get(m.ModifierGroup,1).name='Temperature'; db.commit()
        data=self.client.get('/api/locations/1/orders',headers=self.api).json
        self.assertEqual(data['orders'][0]['lines'][0]['service_timing'],[])

    def test_views_cannot_release_and_wrong_location_is_404(self):
        self.sync()
        path = '/api/locations/1/orders/order-1/release'
        self.assertEqual(self.client.post(path,headers={'Authorization':'Bearer '+VIEW},json={'released_by':'x'}).status_code,401)
        self.assertEqual(self.client.post('/api/locations/2/orders/order-1/release',headers=self.api,json={'released_by':'x'}).status_code,404)
        self.assertEqual(self.client.post(path,headers=self.api,json=[]).status_code,400)
        self.assertEqual(self.client.get('/api/locations/1/orders').status_code,401)

    def test_oldest_first_no_loss_beyond_visible_count(self):
        first = self.clover.orders[0]
        self.clover.orders = [{**first,'id':f'order-{i:02}','createdTime':first['createdTime']+i*1000} for i in reversed(range(10))]
        # Each line must have a distinct source identity, just as Clover supplies.
        original_get = self.clover.get
        def get(path,params=None):
            result = original_get(path,params)
            if path.endswith('/line_items'):
                result.data = {'elements':[{**self.clover.lines[0], 'id':path.split('/')[-2]+'-line'}]}
            return result
        self.clover.get = get
        self.sync()
        data = self.client.get('/api/locations/1/orders',headers=self.api).json
        self.assertEqual(data['total'],10)
        self.assertEqual(data['visible_count'],6)
        self.assertEqual(data['orders'][0]['order_id'],'order-00')
        self.client.post('/api/locations/1/orders/order-00/release',headers=self.api,json={'released_by':'tablet'})
        self.assertEqual(self.client.get('/api/locations/1/orders',headers=self.api).json['orders'][0]['order_id'],'order-01')
        self.assertEqual(self.client.post('/api/locations/1/settings',headers=self.api,json={'visible_count':6}).json['visible_count'],6)
        self.assertEqual(self.client.post('/api/locations/1/settings',headers=self.api,json={'visible_count':True}).status_code,400)

    def test_html_auth_localization_archive_escape_and_help(self):
        self.sync()
        self.assertEqual(self.client.get('/board/1').status_code,302)
        self.client.post('/login',data={'token':VIEW})
        page = self.client.get('/board/1').get_data(as_text=True)
        self.assertIn('Come funziona questa pagina',page)
        self.assertIn('rf-help-dialog',page)
        self.client.post('/api/locations/1/orders/order-1/release',headers=self.api,json={'released_by':'tablet'})
        archive = self.client.get('/archive/1').get_data(as_text=True)
        self.assertIn('&lt;script&gt;',archive)
        self.assertNotIn('<script>alert(1)</script>',archive)
        shared = create_app(self.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE)
        page = shared.test_client().get('/board/1',headers=self.api).get_data(as_text=True)
        self.assertIn('How this page works',page)
        self.assertIn("'sha256-", shared.test_client().get('/board/1',headers=self.api).headers['Content-Security-Policy'])

    def test_canonical_lock_skips_without_touching_cursors(self):
        from rfone_data_store.technical.connectors.clover import acquisition as a
        with self.factory() as db:
            lock = a._acquire_import_lock(db,location_id=1,source_system_id=1,period_start=now(),period_end=now(),mode='CORRECTION')
        self.assertFalse(self.sync())
        self.assertEqual(self.clover.paths,[])

    def settings_login(self):
        self.client.post('/login',data={'token':RELEASE})
        page=self.client.get('/settings/1')
        self.assertEqual(page.status_code,200)
        with self.client.session_transaction() as session:
            csrf=session['settings_csrf']
        return {'csrf_token':csrf,'revision':'0','font_family':'verdana','font_size':'18',
                'visible_count':'4','row_count':'2','layout':'cards'}

    def test_settings_save_persist_and_reach_display_feed(self):
        form=self.settings_login()
        response=self.client.post('/settings/1',data=form)
        self.assertEqual(response.status_code,302)
        self.assertIn('saved=1',response.location)
        # A separate application/session reads the persisted settings.
        other=create_app(self.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE,local=True).test_client()
        saved=other.get('/api/locations/1/orders',headers=self.api).json['display_settings']
        self.assertEqual((saved['font_family'],saved['font_size'],saved['visible_count'],saved['row_count'],saved['layout']),
                         ('verdana',18,4,2,'cards'))
        self.assertEqual(saved['revision'],1)
        # Existing column-only integration updates retain the other preferences.
        response=other.post('/api/locations/1/settings',headers=self.api,json={'visible_count':5})
        self.assertEqual(response.json['row_count'],2)
        self.assertEqual(response.json['font_size'],18)

    def test_settings_read_is_non_mutating_and_requires_management(self):
        from display_settings import DisplaySettings
        self.client.post('/login',data={'token':VIEW})
        self.assertEqual(self.client.get('/settings/1').status_code,302)
        self.assertEqual(self.client.post('/settings/1',data={}).status_code,302)
        self.settings_login()
        with self.factory() as db:
            self.assertIsNone(db.get(DisplaySettings,1))
        # A manager browser session can configure but cannot release via API.
        self.assertEqual(self.client.post('/api/locations/1/orders/order-1/release',json={'released_by':'x'}).status_code,401)

    def test_settings_csrf_invalid_values_and_conflicting_drafts(self):
        form=self.settings_login()
        self.assertEqual(self.client.post('/settings/1',data={**form,'csrf_token':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/settings/1',data={**form,'row_count':'0'}).status_code,400)
        self.assertEqual(self.client.post('/settings/1',data=form).status_code,302)
        conflict=self.client.post('/settings/1',data={**form,'font_size':'30'})
        self.assertEqual(conflict.status_code,409)
        self.assertIn('value="30"',conflict.get_data(as_text=True))
        saved=self.client.get('/api/locations/1/orders',headers=self.api).json['display_settings']
        self.assertEqual(saved['font_size'],18)
        for values in ({'row_count':4},{'font_size':0},{'font_family':'injected-css'},{'layout':'scroll'}):
            self.assertEqual(self.client.post('/api/locations/1/settings',headers=self.api,json=values).status_code,400)

    def test_shared_settings_page_defaults_to_english(self):
        shared=create_app(self.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE)
        page=shared.test_client().get('/settings/1',headers=self.api)
        self.assertEqual(page.status_code,200)
        text=page.get_data(as_text=True)
        self.assertIn('Save settings',text)
        self.assertIn('How this page works',text)
        self.assertNotIn('Salva impostazioni',text)

    def test_all_pages_can_use_english_in_local_mode(self):
        import re
        english=create_app(self.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE,
                           local=True,language='en').test_client()
        for path,label in [('/','Open kitchen display'),('/board/1','Exit kitchen display'),
                           ('/archive/1','Released orders'),('/settings/1','Save settings')]:
            response=english.get(path,headers=self.api)
            self.assertEqual(response.status_code,200,path)
            text=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>','',response.get_data(as_text=True),flags=re.S)
            self.assertIn('lang="en"',text,path)
            self.assertIn(label,text,path)
            for italian in ('Come funziona questa pagina','Impostazioni schermo','Ordini rilasciati','Apri schermo cucina'):
                self.assertNotIn(italian,text,path)

    # Shelbi's improvements (branch shelbi/kitchen-board-improvements).
    def orders_now(self):
        return self.client.get('/api/locations/1/orders',headers=self.api).json['orders']

    def release_now(self, order_id='order-1'):
        return self.client.post(f'/api/locations/1/orders/{order_id}/release',headers=self.api,json={'released_by':'pass'})

    def test_lines_added_after_release_become_an_addition_ticket(self):
        self.sync(); self.release_now()
        self.clover.lines.append({'id':'line-2','name':'Tiramisu','unitQty':1000,'modifications':{'elements':[]}})
        self.sync()
        orders=self.orders_now()
        self.assertEqual([o['order_id'] for o in orders],['order-1-add1'])
        self.assertEqual([l['name'] for l in orders[0]['lines']],['Tiramisu'])
        self.assertEqual((orders[0]['addition'],orders[0]['addition_to'],orders[0]['title']),(1,'order-1','#3 - OUTSIDE'))
        self.sync()  # a repeat read never duplicates the addition
        self.assertEqual(len(self.orders_now()),1)
        self.release_now('order-1-add1')
        self.clover.lines.append({'id':'line-3','name':'Espresso cake','unitQty':1000})
        self.sync()
        orders=self.orders_now()
        self.assertEqual([(o['order_id'],[l['name'] for l in o['lines']]) for o in orders],[('order-1-add2',['Espresso cake'])])
        with self.factory() as db:  # the released snapshot stays frozen
            self.assertEqual(len(db.get(Ticket,(1,'order-1')).payload['lines']),1)

    def test_changes_on_an_open_ticket_are_flagged(self):
        self.sync()
        self.assertNotIn('changes',self.orders_now()[0])
        self.clover.lines.append({'id':'line-2','name':'Gnocchi','unitQty':1000})
        self.clover.lines[0]['note']='No salt, extra sauce'
        self.sync()
        changes=self.orders_now()[0]['changes']
        self.assertEqual((changes['new'],changes['changed'],changes['removed']),(['line-2'],['line-1'],[]))
        del self.clover.lines[1]
        self.sync()
        changes=self.orders_now()[0]['changes']
        self.assertEqual((changes['new'],[r['name'] for r in changes['removed']]),([],['Gnocchi']))
        self.assertEqual(changes['changed'],['line-1'])

    def test_undo_release_within_the_window(self):
        self.sync(); self.release_now()
        path='/api/locations/1/orders/order-1/undo-release'
        self.assertEqual(self.client.post(path,headers={'Authorization':'Bearer '+VIEW},json={'undone_by':'x'}).status_code,401)
        self.assertEqual(self.client.post(path,headers=self.api,json={}).status_code,400)
        result=self.client.post(path,headers=self.api,json={'undone_by':'pass'}).json
        self.assertEqual(result,{'order_id':'order-1','released':False,'already_open':False})
        self.assertEqual([o['order_id'] for o in self.orders_now()],['order-1'])
        self.assertTrue(self.client.post(path,headers=self.api,json={'undone_by':'pass'}).json['already_open'])
        self.clover.lines[0]['name']='Pasta changed'
        self.sync()  # back on the board, it follows Clover again and keeps its history
        with self.factory() as db:
            ticket=db.get(Ticket,(1,'order-1'))
            self.assertEqual(ticket.payload['lines'][0]['name'],'Pasta changed')
            self.assertEqual(ticket.payload['release_history'][0]['released_by'],'pass')
        self.release_now()
        with self.factory() as db:
            db.get(Ticket,(1,'order-1')).released_at=now()-timedelta(minutes=16); db.commit()
        self.assertEqual(self.client.post(path,headers=self.api,json={'undone_by':'pass'}).status_code,409)
        self.assertEqual(self.client.post('/api/locations/1/orders/nope/undo-release',headers=self.api,json={'undone_by':'p'}).status_code,404)

    def test_undo_refused_once_an_addition_exists(self):
        self.sync(); self.release_now()
        self.clover.lines.append({'id':'line-2','name':'Tiramisu','unitQty':1000})
        self.sync()
        r=self.client.post('/api/locations/1/orders/order-1/undo-release',headers=self.api,json={'undone_by':'p'})
        self.assertEqual(r.status_code,409)

    def test_server_name_and_allergy_flags(self):
        self.clover.orders[0]['employee']={'id':'e1','name':'Anthony'}
        self.clover.lines[0]['note']='Guest has a nut allergy'
        self.clover.lines.append({'id':'line-2','name':'Salad','unitQty':1000,'modifications':{'elements':[{'name':'Gluten free'}]}})
        self.clover.lines.append({'id':'line-3','name':'Bread','unitQty':1000,'note':'Warm, nutmeg butter'})
        self.sync()
        order=self.orders_now()[0]
        self.assertEqual(order['server'],'Anthony')
        self.assertEqual([l['allergy'] for l in order['lines']],[True,True,False])
        self.assertTrue(order['allergy'])


    # Partial release: the kitchen releases any dishes; the rest stays on the board.
    def three_dishes(self):
        self.clover.lines = [{'id': 'p1', 'name': 'Carbonara', 'unitQty': 1000},
                             {'id': 'p2', 'name': 'Lasagna', 'unitQty': 1000},
                             {'id': 'p3', 'name': 'Ribeye', 'unitQty': 1000}]
        self.sync()

    def part(self, ids, order_id='order-1'):
        return self.client.post(f'/api/locations/1/orders/{order_id}/release', headers=self.api,
                                json={'released_by': 'pass', 'line_ids': ids})

    def test_partial_release_keeps_the_rest_open(self):
        self.three_dishes()
        r = self.part(['p1', 'p2']).json
        self.assertEqual((r['partial'], r['part_id'], r['remaining_line_ids']), (True, 'order-1-part1', ['p3']))
        order = self.orders_now()[0]
        self.assertEqual(([l['name'] for l in order['lines']], order['released_line_ids']), (['Ribeye'], ['p1', 'p2']))
        self.sync()  # Clover still lists all three: released dishes never come back
        self.assertEqual([l['name'] for l in self.orders_now()[0]['lines']], ['Ribeye'])
        self.assertTrue(self.part(['p1', 'p2']).json['already_released'])  # a retried request
        with self.factory() as db:
            part = db.get(Ticket, (1, 'order-1-part1'))
            self.assertEqual(([l['name'] for l in part.payload['lines']], part.released_by), (['Carbonara', 'Lasagna'], 'pass'))
        archive = self.client.get('/archive/1', headers=self.api).get_data(as_text=True)
        self.assertIn('Rilascio parziale 1', archive)  # local test app is Italian

    def test_releasing_the_last_dishes_releases_the_order(self):
        self.three_dishes()
        self.part(['p1'])
        r = self.part(['p2', 'p3']).json
        self.assertEqual((r['partial'], r['already_released']), (False, False))
        self.assertEqual(self.orders_now(), [])
        self.clover.lines.append({'id': 'p4', 'name': 'Tiramisu', 'unitQty': 1000})
        self.sync()  # an addition still comes back, and only the new dish
        self.assertEqual([(o['order_id'], [l['name'] for l in o['lines']]) for o in self.orders_now()],
                         [('order-1-add1', ['Tiramisu'])])

    def test_partial_release_rejects_dishes_not_on_the_ticket(self):
        self.three_dishes()
        self.assertEqual(self.part(['nope']).status_code, 409)
        self.assertEqual(self.part([]).status_code, 400)
        self.assertEqual(self.part('p1').status_code, 400)
        self.assertEqual(len(self.orders_now()[0]['lines']), 3)

    def test_undo_a_partial_release(self):
        self.three_dishes()
        self.part(['p1'])
        r = self.client.post('/api/locations/1/orders/order-1-part1/undo-release', headers=self.api,
                             json={'undone_by': 'pass'}).json
        self.assertEqual(r['returned_to'], 'order-1')
        order = self.orders_now()[0]
        self.assertEqual((sorted(l['name'] for l in order['lines']), order['released_line_ids']),
                         (['Carbonara', 'Lasagna', 'Ribeye'], []))
        self.sync()
        self.assertEqual(len(self.orders_now()[0]['lines']), 3)
        with self.factory() as db:
            self.assertIsNone(db.get(Ticket, (1, 'order-1-part1')))
        self.assertEqual(self.part(['p1']).json['part_id'], 'order-1-part2')  # numbering never reuses a part

    def test_part_undo_refused_after_the_rest_was_released(self):
        self.three_dishes()
        self.part(['p1']); self.release_now()
        r = self.client.post('/api/locations/1/orders/order-1-part1/undo-release', headers=self.api, json={'undone_by': 'p'})
        self.assertEqual(r.status_code, 409)

    def test_partial_release_of_an_addition(self):
        self.sync(); self.release_now()
        self.clover.lines += [{'id': 'd1', 'name': 'Tiramisu', 'unitQty': 1000}, {'id': 'd2', 'name': 'Cannoli', 'unitQty': 1000}]
        self.sync()
        self.part(['d1'], 'order-1-add1')
        self.sync()
        self.assertEqual([(o['order_id'], [l['name'] for l in o['lines']]) for o in self.orders_now()],
                         [('order-1-add1', ['Cannoli'])])


if __name__ == '__main__':
    unittest.main()
