"""Disposable in-memory UI fixture. Never reads credentials or calls Clover."""
from test_board import BoardTest, VIEW, RELEASE, SECRET
from app import create_app

fixture = BoardTest()
fixture.setUp()
fixture.app=create_app(fixture.factory,secret=SECRET,view_token=VIEW,release_token=RELEASE,local=True,language='en')
first = fixture.clover.orders[0]
fixture.clover.orders = [{**first, 'id':f'preview-{i}', 'title':f'#{i+3} - OUTSIDE',
                          'createdTime':first['createdTime']+i*1000} for i in range(10)]
original_get = fixture.clover.get
def get(path, params=None):
    result = original_get(path, params)
    if path.endswith('/line_items'):
        names = [('','Prosciutto & Cantaloupe'),('','Campari & Goat Cheese - Appetizer'),
                 ('GUEST 1','Still Water 500ml - Glass Bottle'),('GUEST 1','Pinot Grigio - Tenuta del Morer.'),
                 ('GUEST 2','Grillo - Casa di Grazia.')]
        result.data = {'elements':[{'id':path.split('/')[-2]+str(j),'name':name,'binName':guest}
                                    for j,(guest,name) in enumerate(names)]}
    return result
fixture.clover.get = get
fixture.sync()
from flask import redirect, session
@fixture.app.get('/preview')
def preview():
    # Only this disposable fixture bypasses the login, never the real application.
    session['board_view'] = True
    return redirect('/board/1')
print('Disposable Kitchen Board preview, screen token: '+VIEW, flush=True)
fixture.app.run(host='127.0.0.1',port=5091,debug=False)
