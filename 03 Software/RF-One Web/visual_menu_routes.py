"""Authenticated live Visual Menu, reading Kitchen for every page/API request."""
from pathlib import Path
import sys
from urllib.parse import urlsplit
import json
from flask import abort, jsonify, make_response, render_template, send_file, url_for, request, redirect
from sqlalchemy import select, update
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'RF-One Data Store'))
from rfone_data_store.kitchen import menu_cards
from rfone_data_store.visual_menu import read_card
from kitchen_media_response import serve_kitchen_image


def register_visual_menu_routes(app, *, SessionFactory, load_current_account, require_csrf):
    from visual_menu_access import role_for

    def entry():
        value = request.args.get('from','training')
        if value not in ('training','myrf'):
            abort(400)
        return value

    def context(restaurant_id, dish_key):
        with SessionFactory() as db:
            account = load_current_account(db)
            role = role_for(db, account, entry())
            card = read_card(db, restaurant_id, dish_key)
            if card is None:
                abort(404)
            peers = db.execute(select(menu_cards.c.restaurant_id, menu_cards.c.title)
                               .where(menu_cards.c.dish_key == dish_key,
                                      menu_cards.c.restaurant_id != restaurant_id)).mappings().all()
        return card, role, peers

    @app.get('/visual-menu')
    def visual_menu_home():
        with SessionFactory() as db:
            role = role_for(db,load_current_account(db),entry())
            rows = db.execute(select(menu_cards).order_by(menu_cards.c.restaurant_id,menu_cards.c.title)).mappings().all()
            cards = [dict(restaurant_id=r['restaurant_id'],dish_key=r['dish_key'],title=r['title'],
                          restaurant_name=json.loads(r['content_json'])['restaurant_name']) for r in rows]
        response=make_response(render_template('visual_menu_home.html',cards=cards,role=role,entry=entry(),ui=lambda s:s))
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/myrf/visual-menu')
    def myrf_visual_menu():
        with SessionFactory() as db:
            role_for(db,load_current_account(db),'myrf')
        return redirect(url_for('visual_menu_home', **{'from':'myrf'}))

    @app.get('/training/visual-menu')
    def training_visual_menu():
        with SessionFactory() as db:
            role_for(db,load_current_account(db),'training')
        return redirect(url_for('visual_menu_home', **{'from':'training'}))

    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>')
    def visual_menu_card(restaurant_id, dish_key):
        card, role, peers = context(restaurant_id, dish_key)
        photo = card['photo_uri']
        if photo and urlsplit(photo).scheme not in ('https', 'http'):
            photo = url_for('visual_menu_photo', restaurant_id=restaurant_id, dish_key=dish_key,**{'from':entry()})
        response = make_response(render_template('visual_menu_card.html', card=card,
            photo_url=photo, peers=peers,role=role,entry=entry(),ui=lambda s:s))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>/data')
    def visual_menu_data(restaurant_id, dish_key):
        card, _, _ = context(restaurant_id, dish_key)
        response = jsonify(card)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/visual-menu/<int:restaurant_id>/<dish_key>/photo')
    def visual_menu_photo(restaurant_id, dish_key):
        card, _, _ = context(restaurant_id, dish_key)
        if card['photo_uri'] and urlsplit(card['photo_uri']).scheme=='s3':
            return serve_kitchen_image(card['photo_uri'])
        abort(404)

    @app.post('/visual-menu/<int:restaurant_id>/<dish_key>/phrases')
    def visual_menu_phrases(restaurant_id,dish_key):
        require_csrf()
        with SessionFactory() as db:
            if role_for(db,load_current_account(db),entry()) != 'trainer':
                abort(403)
            row = db.execute(select(menu_cards).where(menu_cards.c.restaurant_id==restaurant_id,
                menu_cards.c.dish_key==dish_key)).mappings().first()
            if row is None: abort(404)
            try: version=int(request.form.get('version',''))
            except ValueError: abort(400)
            content=json.loads(row['content_json'])
            for field in ('description_phrases','sales_phrases'):
                value=request.form.get(field,'').strip()
                if len(value)>4000: abort(400)
                content[field]=[line.strip() for line in value.splitlines() if line.strip()]
            changed=db.execute(update(menu_cards).where(menu_cards.c.restaurant_id==restaurant_id,
                menu_cards.c.dish_key==dish_key,menu_cards.c.content_version==version)
                .values(content_json=json.dumps(content,ensure_ascii=False),content_version=version+1))
            if changed.rowcount != 1:
                db.rollback()
                card,role,peers=context(restaurant_id,dish_key)
                photo=url_for('visual_menu_photo',restaurant_id=restaurant_id,dish_key=dish_key)
                return render_template('visual_menu_card.html',card=card,role=role,peers=peers,
                    photo_url=photo,entry=entry(),ui=lambda s:s,phrase_draft=request.form,
                    phrase_error='This card changed while you were editing. Your draft is preserved. Review the current phrases above before saving again.'),409
            db.commit()
        return redirect(url_for('visual_menu_card',restaurant_id=restaurant_id,dish_key=dish_key)+'#phrases')
