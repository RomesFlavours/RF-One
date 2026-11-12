"""Authenticated Visual Menu reads only the active Kitchen menu of each location."""
from urllib.parse import urlsplit
from flask import abort,jsonify,make_response,render_template,url_for,request,redirect
from sqlalchemy.exc import IntegrityError
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
                if current is None:return no_store(make_response(jsonify(error=message,draft=values),409))
                peers=reader.peers(db,current)
                for peer in peers:peer['url']=url_for('visual_menu_entry',location_id=peer['location_id'],entry_id=peer['entry_id'],**{'from':entry()})
                return no_store(make_response(render_card(current,role,peers,phrase_draft=request.form,phrase_error=message),409))
            except ValueError as exc:abort(400,description=str(exc))
        return redirect(url_for('visual_menu_entry',location_id=location_id,entry_id=entry_id,**{'from':entry()})+'#phrases')

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
