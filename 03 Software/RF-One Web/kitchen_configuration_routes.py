"""Kitchen Configuration: existing account gate, inline forms and shared services."""
from flask import abort, make_response, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from rfone_data_store import kitchen_configuration as config
from rfone_data_store.models import Restaurant, Location


def register_configuration_routes(app, *, gate, SessionFactory, load_current_account, allowed_tabs, require_csrf):
    def tabs(db):
        account = load_current_account(db)
        permitted = allowed_tabs(db, account) if account else []
        if not any(t[0]=='CONFIGURATION' for t in permitted):
            abort(403)
        return permitted

    def render(db, *, error=None, section=None, submitted=None, edit_id=None):
        response = make_response(render_template('kitchen_configuration.html',
            kitchen_tabs=tabs(db), active_tab='CONFIGURATION', ui=lambda value:value,
            sections=config.SECTIONS, configuration=config.lists(db),
            restaurants=db.execute(select(Restaurant.id,Restaurant.name).order_by(Restaurant.name)).mappings().all(),
            locations=db.execute(select(Location.id,Location.name).order_by(Location.name)).mappings().all(),
            expanded_section=section or request.args.get('section'), error=error,
            submitted=submitted or {}, edit_id=edit_id), 400 if error else 200)
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/kitchen/configuration')
    @gate
    def kitchen_configuration():
        with SessionFactory() as db:
            return render(db)

    @app.post('/kitchen/configuration/<section>/<action>')
    @gate
    def kitchen_configuration_action(section,action):
        if section not in dict(config.SECTIONS) or action not in ('save','archive'):
            abort(404)
        with SessionFactory() as db:
            tabs(db)
            if require_csrf is None:
                abort(400)
            require_csrf()
            submitted=request.form.to_dict()
            try:
                item_id=int(request.form['item_id']) if request.form.get('item_id') else None
                restaurant_id=int(request.form['restaurant_id']) if request.form.get('restaurant_id') else None
                location_id=int(request.form['location_id']) if request.form.get('location_id') else None
            except (ValueError,KeyError):
                return render(db,error='Choose a valid item, restaurant or location.',section=section,submitted=submitted)
            try:
                if action=='archive':
                    if item_id is None:
                        raise config.ConfigurationError('Choose an item to archive.')
                    config.archive(db,section,item_id)
                else:
                    item_id=config.save(db,section,name=request.form.get('name'),
                        item_id=item_id,restaurant_id=restaurant_id,location_id=location_id)
                db.commit()
            except (config.ConfigurationError,IntegrityError) as exc:
                db.rollback()
                message=str(exc) if isinstance(exc,config.ConfigurationError) else 'This name already exists in this section.'
                return render(db,error=message,section=section,submitted=submitted,edit_id=item_id)
        return redirect(url_for('kitchen_configuration',section=section,_anchor=f'config-{section}'),code=303)
