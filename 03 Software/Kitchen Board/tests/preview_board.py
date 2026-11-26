"""Disposable in-memory UI fixture. Never reads credentials or calls Clover."""
import os
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
        # Sent to the kitchen (Clover 'printed'), like a real ticket the board shows.
        result.data = {'elements':[{'id':path.split('/')[-2]+str(j),'name':name,'binName':guest,'printed':True}
                                    for j,(guest,name) in enumerate(names)]}
        if os.environ.get('PREVIEW_LONG_FIRST') and path.split('/')[-2] == 'preview-0':
            # A first order far too long for one screen: it must still show, never a blank board.
            result.data['elements'] += [{'id':f'long{k}','name':f'Dish {k} '+'with a long note '*6,
                                         'binName':f'GUEST {k%9}','printed':True} for k in range(120)]
    return result
fixture.clover.get = get
fixture.sync()
from flask import redirect, session
@fixture.app.get('/preview')
def preview():
    # Only this disposable fixture bypasses the login, never the real application.
    session['board_view'] = True
    return redirect('/board/1')
@fixture.app.get('/preview-pass')
def preview_pass():
    # The pass tablet's view in the same disposable fixture.
    session['board_view'] = True; session['board_manage'] = True
    return redirect('/pass/1')
print('Disposable Kitchen Board preview, screen token: '+VIEW, flush=True)
fixture.app.run(host='127.0.0.1',port=5091,debug=False)
