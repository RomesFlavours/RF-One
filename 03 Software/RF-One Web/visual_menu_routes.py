"""Authenticated Visual Menu reads only the active Kitchen menu of each location."""
from urllib.parse import urlsplit
from flask import abort,jsonify,make_response,render_template,url_for,request,redirect
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from rfone_data_store.models import Restaurant
from rfone_data_store import visual_menu_active as reader
from kitchen_media_response import serve_kitchen_image


def register_visual_menu_routes(app, *, SessionFactory, load_current_account, require_csrf):
    from visual_menu_access import role_for
    def entry():
        value=request.args.get('from','training')
        if value not in ('training','myrf'):abort(400)
        return value
    def no_store(response):
        response.headers['Cache-Control']='no-store';return response
    def trainer_access(db):
        if role_for(db,load_current_account(db),entry())!='trainer':abort(403)
    def phrase_values():
        values={}
        for field in ('description_phrases','sales_phrases'):
            value=request.form.get(field,'').strip()
            if len(value)>4000:abort(400)
            values[field]=[line.strip() for line in value.splitlines() if line.strip()]
        return values
    def manager_card(card):
        photo=card.pop('photo_uri')
        card['photo_url']=photo if photo and urlsplit(photo).scheme in ('http','https') else url_for('visual_menu_manage_photo',restaurant_id=card['restaurant_id'],recipe_id=card['recipe_id']) if photo else None
        return card

    @app.get('/visual-menu/manage')
    def visual_menu_manage():
        with SessionFactory() as db:
            trainer_access(db)
            restaurants=db.execute(select(Restaurant.id,Restaurant.name).order_by(Restaurant.id)).mappings().all()
            try:restaurant_id=int(request.args['restaurant_id']) if request.args.get('restaurant_id') else None
            except ValueError:abort(400)
            if restaurant_id is not None and restaurant_id not in {r['id'] for r in restaurants}:abort(404)
            available_menus=reader.management_menus(db,restaurant_id) if restaurant_id is not None else []
            menu_filter=request.args.get('menu_id') or ('all' if restaurant_id is not None else 'kitchen')
            recipe_ids=None
            if menu_filter!='kitchen':
                if restaurant_id is None:abort(400)
                ids={menu['id'] for menu in available_menus}
                if menu_filter=='all':recipe_ids=reader.menu_recipe_ids(db,ids)
                else:
                    try:menu_id=int(menu_filter)
                    except ValueError:abort(400)
                    if menu_id not in ids:abort(404)
                    recipe_ids=reader.menu_recipe_ids(db,[menu_id])
            rows=reader.editorial_listing(db,restaurant_id,recipe_ids)
        return no_store(make_response(render_template('visual_menu_manage.html',restaurants=restaurants,restaurant_id=restaurant_id,
            available_menus=available_menus,menu_filter=menu_filter,rows=rows,role='trainer',entry='training',ui=lambda s:s)))

    @app.route('/visual-menu/manage/<int:restaurant_id>/recipes/<int:recipe_id>',methods=['GET','POST'])
    def visual_menu_manage_card(restaurant_id,recipe_id):
        with SessionFactory() as db:
            trainer_access(db)
            card=reader.read_editorial(db,restaurant_id,recipe_id)
            if card is None:abort(404)
            if request.method=='POST':
                require_csrf()
                try:version=int(request.form.get('version',''))
                except ValueError:abort(400)
                values=phrase_values()
                try:
                    reader.save_editorial(db,restaurant_id,recipe_id,version,values);db.commit()
                except (reader.PhraseConflict,IntegrityError):
                    db.rollback()
                    return no_store(make_response(jsonify(error='This card changed. Your draft is preserved. Close and reopen the card to review the current phrases before saving.',draft=values),409))
                except ValueError as exc:abort(400,description=str(exc))
                card=reader.read_editorial(db,restaurant_id,recipe_id)
            return no_store(jsonify(card=manager_card(card)))

    @app.get('/visual-menu/manage/<int:restaurant_id>/recipes/<int:recipe_id>/photo')
    def visual_menu_manage_photo(restaurant_id,recipe_id):
        with SessionFactory() as db:
            trainer_access(db);card=reader.read_editorial(db,restaurant_id,recipe_id)
            if card is None or not card['photo_uri']:abort(404)
        if urlsplit(card['photo_uri']).scheme in ('http','https'):return no_store(redirect(card['photo_uri']))
        return serve_kitchen_image(card['photo_uri'])
    def context(location_id,entry_id):
        with SessionFactory() as db:
            role=role_for(db,load_current_account(db),entry())
            card=reader.read_entry(db,location_id,entry_id)
            if card is None:abort(404)
            peers=reader.peers(db,card)
        for peer in peers:peer['url']=url_for('visual_menu_entry',location_id=peer['location_id'],entry_id=peer['entry_id'],**{'from':entry()})
        return card,role,peers
    def render_card(card,role,peers,**extra):
        photo=card['photo_uri']
        if photo and urlsplit(photo).scheme not in ('http','https'):
            photo=url_for('visual_menu_entry_photo',location_id=card['location_id'],entry_id=card['entry_id'],**{'from':entry()})
        return render_template('visual_menu_card.html',card=card,role=role,peers=peers,entry=entry(),ui=lambda s:s,
            photo_url=photo,phrase_action=url_for('visual_menu_entry_phrases',location_id=card['location_id'],entry_id=card['entry_id'],**{'from':entry()}),**extra)

    @app.get('/visual-menu')
    def visual_menu_home():
        with SessionFactory() as db:
            role=role_for(db,load_current_account(db),entry());locations=reader.read_home(db)
        for location in locations:
            for area in location['areas']:
                for dish in area['entries']:
                    if dish['recipe_id']:
                        args=dict(location_id=location['location_id'],entry_id=dish['id'],**{'from':entry()})
                        dish['url']=url_for('visual_menu_entry',**args)
                        photo=dish['photo_uri']
                        dish['photo_url']=photo if photo and urlsplit(photo).scheme in ('http','https') else url_for('visual_menu_entry_photo',**args) if photo else None
        return no_store(make_response(render_template('visual_menu_home.html',locations=locations,role=role,entry=entry(),ui=lambda s:s)))

    @app.get('/myrf/visual-menu')
    def myrf_visual_menu():
        with SessionFactory() as db:role_for(db,load_current_account(db),'myrf')
        return redirect(url_for('visual_menu_home',**{'from':'myrf'}))

    @app.get('/training/visual-menu')
    def training_visual_menu():
        with SessionFactory() as db:role_for(db,load_current_account(db),'training')
        return redirect(url_for('visual_menu_home',**{'from':'training'}))

    @app.get('/visual-menu/locations/<int:location_id>/entries/<int:entry_id>')
    def visual_menu_entry(location_id,entry_id):
        card,role,peers=context(location_id,entry_id)
        return no_store(make_response(render_card(card,role,peers)))

    @app.get('/visual-menu/locations/<int:location_id>/entries/<int:entry_id>/data')
    def visual_menu_entry_data(location_id,entry_id):
        card,_,_=context(location_id,entry_id);return no_store(jsonify(card))

    @app.get('/visual-menu/locations/<int:location_id>/entries/<int:entry_id>/photo')
    def visual_menu_entry_photo(location_id,entry_id):
        card,_,_=context(location_id,entry_id);photo=card['photo_uri']
        if not photo:abort(404)
        if urlsplit(photo).scheme in ('http','https'):return no_store(redirect(photo))
        return serve_kitchen_image(photo)

    @app.post('/visual-menu/locations/<int:location_id>/entries/<int:entry_id>/phrases')
    def visual_menu_entry_phrases(location_id,entry_id):
        require_csrf()
        with SessionFactory() as db:
            role=role_for(db,load_current_account(db),entry())
            if role!='trainer':abort(403)
            card=reader.read_entry(db,location_id,entry_id)
            if card is None:abort(404)
            try:version=int(request.form.get('version',''))
            except ValueError:abort(400)
            values={}
            for field in ('description_phrases','sales_phrases'):
                value=request.form.get(field,'').strip()
                if len(value)>4000:abort(400)
                values[field]=[line.strip() for line in value.splitlines() if line.strip()]
            try:
                reader.save_phrases(db,card,version,values);db.commit()
            except (reader.PhraseConflict,IntegrityError):
                db.rollback();current=reader.read_entry(db,location_id,entry_id)
                message='This card or active menu changed while you were editing. Your draft is preserved. Review before saving again.'
                return no_store(make_response(jsonify(error=message,draft=values),409))
            except ValueError as exc:abort(400,description=str(exc))
        return redirect(url_for('visual_menu_manage',restaurant_id=card['restaurant_id']))

    def legacy_location(restaurant_id,dish_key):
        with SessionFactory() as db:
            role_for(db,load_current_account(db),entry());target=reader.legacy_entry(db,restaurant_id,dish_key)
            if target is None:abort(404)
            return dict(location_id=target['location_id'],entry_id=target['entry_id'],**{'from':entry()})

    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>')
    def visual_menu_card(restaurant_id,dish_key):
        return no_store(redirect(url_for('visual_menu_entry',**legacy_location(restaurant_id,dish_key))))
    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>/data')
    def visual_menu_data(restaurant_id,dish_key):
        target=legacy_location(restaurant_id,dish_key);return visual_menu_entry_data(target['location_id'],target['entry_id'])
    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>/photo')
    def visual_menu_photo(restaurant_id,dish_key):
        target=legacy_location(restaurant_id,dish_key);return visual_menu_entry_photo(target['location_id'],target['entry_id'])
    @app.post('/visual-menu/<int:restaurant_id>/<dish_key>/phrases')
    def visual_menu_phrases(restaurant_id,dish_key):
        require_csrf();target=legacy_location(restaurant_id,dish_key)
        return visual_menu_entry_phrases(target['location_id'],target['entry_id'])
