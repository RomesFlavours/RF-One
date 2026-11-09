"""Export the actual Board template/assets with sample data for offline review."""
import json
import re
import subprocess
import tempfile
import sys
from html import escape
from pathlib import Path
from test_board import BoardTest
from store import Board
from rfone_data_store import models as m
from kitchen_filter import kitchen_payload

fixture = BoardTest()
fixture.setUp()
fixture.sync()
client = fixture.app.test_client()
with client.session_transaction() as session:
    session['board_view'] = True
html = client.get('/board/1').get_data(as_text=True)
data = client.get('/api/locations/1/orders', headers=fixture.api).json
first = data['orders'][0]
names = [('', 'Prosciutto & Cantaloupe'),('', 'Campari & Goat Cheese - Appetizer'),
         ('GUEST 1', 'Still Water 500ml - Glass Bottle'),('GUEST 1', 'Pinot Grigio - Tenuta del Morer.'),
         ('GUEST 2', 'Grillo - Casa di Grazia.'),('GUEST 2', 'Grillo - Casa di Grazia.')]
data['orders'] = [{**first, 'order_id':f'demo-{i}', 'title':f'#{i+3} - '+('OUTSIDE' if i%2==0 else 'INSIDE'),
                   'local_time':f'19:{10+i:02}',
                   'lines':[{'name':name, 'guest':guest,'quantity':None,'note':None,'modifiers':[],
                             'categories':['Appetizers' if index<2 else 'Beverages' if index==2 else 'Wine White - Glass']}
                            for index,(guest,name) in enumerate(names)]}
                  for i in range(10)]
data['orders'] = [kitchen_payload(order,{}) for order in data['orders']]
data['orders'][0]['lines'] *= 3
data.update(total=10, visible_count=6, stale=False, sync_error=False)
real = len(sys.argv)>1
if real:
    data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
data['visible_count']=5
with fixture.factory() as db:
    db.get(Board,1).visible_count=data['visible_count']
    if data.get('merchant_name'): db.get(m.Location,1).name=data['merchant_name']
    db.delete(db.get(Board,2))
    db.commit()
root = Path(__file__).resolve().parents[1]
css = (root/'static/board.css').read_text(encoding='utf-8')
rail_js = (root/'static/rail.js').read_text(encoding='utf-8')
js = (root/'static/board.js').read_text(encoding='utf-8')
js = re.sub(r'await fetch\([^\n]+\);',
            'await Promise.resolve({status:200,ok:true,json:async()=>('+json.dumps(data)+')});', js)
with tempfile.NamedTemporaryFile(mode='w', suffix='.js', encoding='utf-8', delete=False) as script:
    script.write(js)
try:
    subprocess.run(['node', '--check', script.name], check=True, capture_output=True)
finally:
    Path(script.name).unlink()
# Include the tickets in the HTML itself too: this visual review must never
# depend on an asynchronous request or JavaScript to show its sample tickets.
cards = []
for order in data['orders'][:data['visible_count']]:
    parts = ['<article class="ticket" data-order-id="'+escape(order['order_id'])+'">',
             '<span class="kicker">ORDINE</span><h2>'+escape(order['title'])+'</h2>',
             '<time>'+escape(order['local_time'])+'</time>']
    guest = ''
    for line in order['lines']:
        if line['guest'] != guest:
            guest = line['guest']
            parts.append('<h3 class="guest">'+escape(guest)+'</h3>')
        parts.append('<div class="line"><p>'+escape(line['name'])+'</p></div>')
    parts.append('</article>')
    cards.append(''.join(parts))
html = re.sub(r'(<div id="tickets"[^>]*>)(</div>)',lambda match:match[1]+''.join(cards)+match[2],html)
html = html.replace('Caricamento ordini…','Anteprima · ordini di esempio')
html = html.replace('<span id="queue-count"></span>','<span id="queue-count">10 da rilasciare</span>')
html = html.replace('<p id="overflow"></p>','<p id="overflow">Gli ordini lunghi proseguono a destra.</p>')
html = re.sub(r'<link rel="stylesheet"[^>]+>',lambda _: '<style>'+css+'</style>',html)
html = re.sub(r'<script src="[^"]*board.js"[^>]*></script>', lambda _: '<script>'+js+'</script>',html)
html = re.sub(r'<script src="[^"]*rail.js"[^>]*></script>', lambda _: '<script>'+rail_js+'</script>',html)
html = html.replace('Collegato · aggiornamento automatico','Anteprima · ordini di esempio')
html = html.replace('<div class="toolbar">','<p style="margin:0;color:#704600">ANTEPRIMA — ORDINI DI ESEMPIO</p><div class="toolbar">')
# Keep navigation within this one offline review file.
html = re.sub(r'href="/(?:archive/1|)"', 'href="#"',html)
output = root/'preview.html'
html = html.replace('href="/exit"','href="preview-exit.html"').replace('id="board"','id="board" data-offline-preview="1"')
output.write_text(html,encoding='utf-8')
exit_html = client.get('/exit').get_data(as_text=True)
exit_html = re.sub(r'<link rel="stylesheet"[^>]+>',lambda _: '<style>'+css+'</style>',exit_html)
exit_html = exit_html.replace('href="/board/1"','href="preview.html"').replace('href="/"','href="preview-exit.html"')
exit_html = exit_html.replace('href="/settings/1"','href="preview-settings.html"')
(root/'preview-exit.html').write_text(exit_html,encoding='utf-8')
with client.session_transaction() as session:
    session['board_manage']=True
settings_html=client.get('/settings/1').get_data(as_text=True)
for name in ('board.css','css/rf-one.css','settings.css'):
    settings_html=settings_html.replace('<link rel="stylesheet" href="/static/'+name+'">',
        '<style>'+(root/'static'/name).read_text(encoding='utf-8')+'</style>')
settings_html=settings_html.replace('<script src="/static/settings.js" defer></script>',
    '<script>'+(root/'static/settings.js').read_text(encoding='utf-8')+'</script>')
settings_html=settings_html.replace('id="display-settings-form"','id="display-settings-form" data-local-preview="1"')
settings_html=settings_html.replace('src="/board/1?preview=1"','src="preview.html?draft=1"')
settings_html=settings_html.replace('href="/board/1"','href="preview.html"').replace('href="/exit"','href="preview-exit.html"')
settings_html=settings_html.replace('Il salvataggio aggiorna gli schermi di questa sede.',
    'Anteprima locale: le scelte vengono salvate per questa prova nel browser.')
(root/'preview-settings.html').write_text(settings_html,encoding='utf-8')
assert 'await fetch(' not in html
assert 'board.js"' not in html
assert html.count('<article class="ticket"') == min(5,len(data['orders']))
print(output)
fixture.tearDown()
