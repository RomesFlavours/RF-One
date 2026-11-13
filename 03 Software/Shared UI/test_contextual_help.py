"""Real shared Help rendering and Edge interaction; no RF-One DB or providers."""
from pathlib import Path
import json
import threading
import unittest
from flask import Flask, render_template, render_template_string, request
from jinja2 import FileSystemLoader
from werkzeug.serving import make_server, WSGIRequestHandler

ROOT=Path(__file__).resolve().parents[2]
REGISTRY=json.loads((ROOT/'03 Software/Shared UI/how_works_registry.json').read_text(encoding='utf-8'))['apps']
APPS=['RF-One Web','Selection','Tips']
TARGETS=[(app,target.split('#')[0][5:-5],target.split('#')[1])
    for app in APPS for target in REGISTRY[app]['pages'].values() if isinstance(target,str)]
WRAPPER="""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
<form><label>Draft <input id="draft" value="Unsaved draft"></label></form>
{% include '_how_works.html' %}</body></html>"""

class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args):pass

class ContextualHelpTests(unittest.TestCase):
    def app(self, name, local=False):
        app=Flask(__name__,template_folder=str(ROOT/REGISTRY[name]['templates']))
        app.config['RFONE_LOCAL_OPERATOR']='rfone' if local else None
        return app

    def test_component_copies_and_all_registered_targets_render_in_both_languages(self):
        component=(ROOT/'03 Software/Shared UI/help/_how_works.html').read_bytes()
        for name in APPS:
            self.assertEqual((ROOT/REGISTRY[name]['templates']/'_how_works.html').read_bytes(),component)
        for name,section,anchor in TARGETS:
            for local in [False,True]:
                with self.subTest(app=name,section=section,local=local):
                    app=self.app(name,local)
                    with app.test_request_context('/'):
                        result=render_template_string(WRAPPER,help_section=section)
                    self.assertEqual(result.count('<dialog '),1)
                    self.assertIn(f'data-how-works="{section}"',result)
                    self.assertIn(f'id="{anchor}"',result)
                    self.assertIn('Come funziona questa pagina' if local else 'How this page works',result)
                    self.assertIn('aria-label="Chiudi"' if local else 'aria-label="Close"',result)

    def test_registered_templates_compile(self):
        for name in APPS:
            app=self.app(name)
            for page in REGISTRY[name]['pages']:
                with self.subTest(app=name,page=page):
                    app.jinja_env.parse((ROOT/REGISTRY[name]['templates']/page).read_text(encoding='utf-8'))

    def test_edge_cardholder_modal_help_preserves_assignment(self):
        from playwright.sync_api import sync_playwright, expect
        from types import SimpleNamespace
        template_root=ROOT/REGISTRY['RF-One Web']['templates']
        app=Flask(__name__,template_folder=str(template_root),static_folder=str(template_root.parent/'static'))
        app.secret_key='isolated-help-test'
        app.config['RFONE_LOCAL_OPERATOR']='rfone'
        app.jinja_env.globals.update(csrf_token=lambda:'isolated-test',
            url_for=lambda endpoint,**kw:'/static/'+kw['filename'] if endpoint=='static' else '/unused/'+endpoint)
        app.jinja_env.filters['local_dt']=lambda value,*args:value
        instrument=SimpleNamespace(id=1,display_name='Synthetic card',institution='Test bank',
            instrument_type='CREDIT_CARD',last_four='1234',external_account_identifier=None,
            legal_entity_id=None,currency='USD',linked_instrument_id=None,status='ACTIVE')
        @app.get('/')
        def instrument_page():
            return render_template('bank_instrument_edit.html',instrument=instrument,
                instruments=[],legal_entities=[],current_cardholder=None,current_settlement=None,
                cardholder_candidates=[],cardholder_history=[],settlement_history=[])
        server=make_server('127.0.0.1',0,app,request_handler=QuietHandler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(viewport={'width':390,'height':900})
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
                page=context.new_page();page.goto(base)
                page.locator('#cardholder-open').click()
                expect(page.locator('#cardholder-modal')).to_be_visible(timeout=3000)
                page.locator('#cardholder-name').fill('Unsaved holder')
                page.get_by_role('button',name='Aiuto assegnazione intestatario').click()
                expect(page.locator('#bank-cardholder-assignment')).to_be_visible()
                page.keyboard.press('Escape')
                self.assertFalse(page.locator('#rf-help').evaluate('(el)=>el.open'))
                expect(page.locator('#cardholder-modal')).to_be_visible()
                self.assertEqual(page.locator('#cardholder-name').input_value(),'Unsaved holder')
                page.get_by_role('button',name='Aiuto assegnazione intestatario').click()
                page.locator('#rf-help').get_by_role('button',name='Chiudi').click()
                expect(page.locator('#cardholder-modal')).to_be_visible()
                self.assertEqual(page.locator('#cardholder-name').input_value(),'Unsaved holder')
                page.locator('#cardholder-modal').get_by_role('button',name='Cancel',exact=True).click()
                expect(page.locator('#cardholder-modal')).to_be_hidden()
                context.close();browser.close()
        finally:
            server.shutdown();worker.join();server.server_close()

    def test_edge_desktop_mobile_help_preserves_draft(self):
        from playwright.sync_api import sync_playwright
        app=Flask(__name__)
        @app.get('/help/<int:index>')
        def guide(index):
            name,section,anchor=TARGETS[index]
            app.jinja_loader=FileSystemLoader(str(ROOT/REGISTRY[name]['templates']))
            app.jinja_env.cache.clear()
            app.config['RFONE_LOCAL_OPERATOR']='rfone' if request.args.get('local')=='1' else None
            return render_template_string(WRAPPER,help_section=section)
        server=make_server('127.0.0.1',0,app,request_handler=QuietHandler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context()
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
                page=context.new_page()
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    for index,(_,section,anchor) in enumerate(TARGETS):
                        with self.subTest(width=width,section=section):
                            local=width==390
                            page.goto(base+f'/help/{index}?local={int(local)}')
                            page.locator('#draft').fill('Keep this draft')
                            page.get_by_role('button',name='Come funziona questa pagina' if local else 'How this page works').click()
                            self.assertTrue(page.locator('#rf-help').evaluate('(el)=>el.open'))
                            self.assertTrue(page.locator('#'+anchor).is_visible())
                            page.get_by_role('button',name='Chiudi' if local else 'Close',exact=True).click()
                            self.assertEqual(page.locator('#draft').input_value(),'Keep this draft')
                            page.locator('[data-how-works]').click();page.keyboard.press('Escape')
                            self.assertFalse(page.locator('#rf-help').evaluate('(el)=>el.open'))
                context.close();browser.close()
        finally:
            server.shutdown();worker.join();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
