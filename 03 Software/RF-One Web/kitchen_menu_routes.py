"""Kitchen Menu page with the standard account gate and protected mutations."""
import json
from flask import abort,jsonify,make_response,render_template,request
from sqlalchemy.exc import IntegrityError
from rfone_data_store import kitchen_menus as service

def register_menu_routes(app,*,gate,SessionFactory,load_current_account,allowed_tabs,require_csrf):
    def access(db):
        account=load_current_account(db);tabs=allowed_tabs(db,account) if account else []
        if not any(t[0]=='MENU' for t in tabs):abort(403)
        return tabs
    def response(data,status=200):
        result=jsonify(data);result.status_code=status;result.headers['Cache-Control']='no-store';return result
    @app.get('/kitchen/menus')
    @gate
    def kitchen_menus():
        with SessionFactory() as db:
            tabs=access(db);data=dict(menus=service.listing(db),**service.options(db))
        result=make_response(render_template('kitchen_menus.html',kitchen_tabs=tabs,active_tab='MENU',ui=lambda s:s,menu_data=data))
        result.headers['Cache-Control']='no-store';return result
    @app.post('/kitchen/menus/save')
    @app.post('/kitchen/menus/<int:menu_id>/archive')
    @app.post('/kitchen/menus/<int:menu_id>/activate')
    @gate
    def kitchen_menu_save(menu_id=None):
        with SessionFactory() as db:
            access(db)
            if require_csrf is None:abort(400)
            require_csrf()
            try:
                data=json.loads(request.form.get('payload','{}'))
                if not isinstance(data,dict):raise service.MenuError('Invalid menu.')
                if not menu_id:saved=service.save(db,data)
                elif request.endpoint=='kitchen_menu_save' and request.path.endswith('/activate'):
                    saved=service.activate(db,menu_id,data.get('revision'))
                else:saved=service.archive(db,menu_id,data.get('revision'))
                db.commit();return response(dict(menu=saved,menus=service.listing(db)))
            except (ValueError,IntegrityError) as exc:
                db.rollback()
                message=str(exc) if isinstance(exc,service.MenuError) else 'Could not save this menu. Close and reopen it before retrying.'
                return response(dict(error=message),409 if isinstance(exc,(service.StaleMenu,IntegrityError)) else 400)
