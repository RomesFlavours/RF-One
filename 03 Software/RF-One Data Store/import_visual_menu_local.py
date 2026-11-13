"""Explicit local-only migration and first import of the approved two cards.

Uses the existing local PostgreSQL connection configuration. Prepares the
compatible migration tree in tmp without changing another working checkout.
No remote host is allowed; existing cards are never overwritten.
"""
from pathlib import Path
import json
import os
import shutil
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(os.environ['LOCALAPPDATA']) / 'RF-One/AWS-Copy/20261025T130037Z/local-connection.json'
COMPATIBLE = Path('C:/Users/servi/OneDrive/Documents/ChatGPT/RF1 Sviluppo/tips-engine/03 Software/RF-One Data Store')


def main():
    if '--training-course' in sys.argv:
        from import_kitchen_excel import local_engine
        engine=local_engine()
        with engine.begin() as db:
            db.execute(text("INSERT INTO training_pills(slug,title,learning_objectives,content_version) VALUES ('visual-menu','Visual Menu',:objectives,1) ON CONFLICT(slug) DO NOTHING"),
                dict(objectives='Recognize dishes, understand ingredients and allergen guidance, and learn approved presentation and sales phrases. Live read-only consultation; no quiz or certification.'))
            assert db.scalar(text("SELECT count(*) FROM training_pills WHERE slug='visual-menu'"))==1
        engine.dispose()
        print('PASS: Visual Menu is available in the Training catalog and assignment picker; recipe data remains live.')
        return
    if '--verify-kitchen' in sys.argv:
        from import_kitchen_excel import local_engine
        from rfone_data_store.visual_menu import read_card
        engine = local_engine()
        with engine.connect() as db:
            db.execute(text('SET TRANSACTION READ ONLY'))
            exported = []
            for rid in (1,2):
                live = read_card(db,rid,'shrimp-pistacchio')
                assert live['recipe'] and Path(live['photo_uri']).is_file()
                payload = json.loads(db.execute(text("SELECT content_json FROM restaurant_menu_cards WHERE restaurant_id=:id AND dish_key='shrimp-pistacchio'"),dict(id=rid)).scalar_one())
                assert not any(k in payload for k in ('ingredients','allergens','training','presentation'))
                exported.append(payload)
                print(rid, live['title'], [a['name'] for a in live['allergens']], 'Kitchen photograph OK')
            assert not (ROOT/'output/visual-menu/shrimp-pistacchio.jpg').exists()
            (ROOT/'output/visual-menu/cards.json').write_text(json.dumps(exported,ensure_ascii=False,indent=2),encoding='utf-8')
        engine.dispose()
        return
    if '--transfer-kitchen-photo' in sys.argv:
        return transfer_kitchen_photo()
    if '--link-kitchen' in sys.argv:
        return link_kitchen()
    d = json.loads(CONFIG.read_text())
    assert d['host'] == '127.0.0.1' and d['port'] == 55436
    url = URL.create('postgresql+psycopg2', username=d['user'], password=d['password'],
                     host=d['host'], port=d['port'], database=d['database'])
    engine = create_engine(url)
    with engine.connect() as db:
        versions = db.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        assert versions in [['e2c320261109'], ['e3c420261109']], versions
        restaurants = db.execute(text('SELECT id,name FROM restaurants')).all()
        wp = [r.id for r in restaurants if r.name == "Rome's Flavours - WP"]
        md = [r.id for r in restaurants if r.name == "Rome's Flavours - MD"]
        assert len(wp) == 1 and len(md) <= 1, 'Restaurant mapping is ambiguous'
    if versions == ['e2c320261109']:
        stage = ROOT / 'tmp/visual-menu-migration'
        stage.mkdir(parents=True, exist_ok=True)
        shutil.copytree(COMPATIBLE / 'migrations', stage / 'migrations', dirs_exist_ok=True)
        migration = Path(__file__).parent / 'migrations/versions/e3c420261109_visual_menu_cards.py'
        shutil.copyfile(migration, stage / 'migrations/versions' / migration.name)
        # Use compatible metadata/imports, the same canonical Alembic environment.
        sys.path.insert(0, str(COMPATIBLE))
        cfg = Config(str(COMPATIBLE / 'alembic.ini'))
        cfg.set_main_option('script_location', str(stage / 'migrations'))
        os.environ['ALEMBIC_DATABASE_URL_OVERRIDE'] = url.render_as_string(hide_password=False)
        try:
            command.upgrade(cfg, 'e3c420261109')
        finally:
            os.environ.pop('ALEMBIC_DATABASE_URL_OVERRIDE', None)
    seed = json.loads((ROOT / 'output/visual-menu/cards.json').read_text(encoding='utf-8'))
    with engine.begin() as db:
        if '--update-content' in sys.argv and db.scalar(text("SELECT to_regclass('kitchen_visual_menu_links')")):
            if db.scalar(text('SELECT count(*) FROM kitchen_visual_menu_links')):
                raise RuntimeError('Kitchen-linked cards must use the live reader; do not restore copied recipe content.')
        if not md:
            md = [db.execute(text("INSERT INTO restaurants(name,status,default_currency,default_timezone) VALUES (:name,'ACTIVE','USD','America/New_York') RETURNING id"),
                             {'name': "Rome's Flavours - MD"}).scalar_one()]
        ids = {'winter-park': wp[0], 'mount-dora': md[0]}
        for card in seed:
            if '--update-content' in sys.argv:
                current = db.execute(text('SELECT content_version,validation_status FROM restaurant_menu_cards WHERE restaurant_id=:rid AND dish_key=:key FOR UPDATE'),
                                     dict(rid=ids[card['restaurant_key']], key=card['dish_key'])).one()
                assert current.validation_status == 'pending' and current.content_version in (1, 2)
                db.execute(text('UPDATE restaurant_menu_cards SET content_version=:version,content_json=:payload WHERE restaurant_id=:rid AND dish_key=:key'),
                           dict(rid=ids[card['restaurant_key']], key=card['dish_key'], version=card['content_version'], payload=json.dumps(card, ensure_ascii=False)))
                continue
            db.execute(text('INSERT INTO restaurant_menu_cards(restaurant_id,dish_key,title,content_version,validation_status,content_json) VALUES (:rid,:key,:title,1,\'pending\',:payload) ON CONFLICT(restaurant_id,dish_key) DO NOTHING'),
                       dict(rid=ids[card['restaurant_key']], key=card['dish_key'], title=card['title'], payload=json.dumps(card, ensure_ascii=False)))
        rows = db.execute(text('SELECT restaurant_id,dish_key,content_json FROM restaurant_menu_cards WHERE dish_key=\'shrimp-pistacchio\' ORDER BY restaurant_id')).all()
        assert len(rows) == 2
        for row in rows:
            card = json.loads(row.content_json)
            assert row.restaurant_id == ids[card['restaurant_key']]
            if '--update-content' in sys.argv:
                expected = next(c for c in seed if c['restaurant_key'] == card['restaurant_key'])
                assert card == expected
        result = {'database': 'existing local PostgreSQL', 'revision': 'e3c420261109',
                  'restaurant_ids': ids, 'card_count': len(rows), 'validation_status': 'pending'}
    (ROOT / 'output/visual-menu/import-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


def transfer_kitchen_photo():
    import hashlib
    from import_kitchen_excel import local_engine
    source = ROOT/'output/visual-menu/shrimp-pistacchio.jpg'
    target = ROOT/'03 Software/RF-One Data Store/data/kitchen/photos/D125/shrimp-pistacchio.jpg'
    target.parent.mkdir(parents=True,exist_ok=True)
    if source.is_file():
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Kitchen already has a different image at the target path')
        shutil.copyfile(source,target)
    elif target.is_file():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
    else:
        raise RuntimeError('Dish photograph not found')
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    engine = local_engine()
    with engine.begin() as db:
        recipe_id = db.execute(text("SELECT id FROM kitchen_recipes WHERE code='D125' AND trim(name)='Shrimp & Pistacchio'")).scalar_one()
        existing = db.execute(text('SELECT id FROM kitchen_recipe_photos WHERE recipe_id=:recipe AND sha256=:digest'),dict(recipe=recipe_id,digest=digest)).scalars().all()
        assert len(existing) <= 1
        photo_id = existing[0] if existing else db.execute(text('INSERT INTO kitchen_recipe_photos(recipe_id,asset_uri,sha256,mime_type,caption,alt_text,source) VALUES (:recipe,:uri,:digest,\'image/jpeg\',:caption,:alt,:source) RETURNING id'),
            dict(recipe=recipe_id,uri=str(target),digest=digest,caption='Reference photograph; current plating requires confirmation',alt='Fettuccine with shrimp and pistachio',source='Existing Visual Menu reference photograph; kitchen validation pending')).scalar_one()
        db.execute(text("UPDATE kitchen_visual_menu_links SET standard_photo_id=:photo WHERE recipe_id=:recipe AND dish_key='shrimp-pistacchio' AND restaurant_id IN (1,2)"),dict(photo=photo_id,recipe=recipe_id))
        assert db.scalar(text('SELECT count(*) FROM kitchen_visual_menu_links WHERE recipe_id=:recipe AND standard_photo_id=:photo'),dict(recipe=recipe_id,photo=photo_id)) == 2
    # Remove the Menu-owned asset only after the Kitchen record and both links commit.
    if source.exists():
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        source.unlink()
    engine.dispose()
    print('PASS: photograph transferred to Kitchen recipe D125; two Menu links select the same Kitchen photograph; Menu-owned image removed.')


def link_kitchen():
    from import_kitchen_excel import local_engine
    from rfone_data_store.visual_menu import read_card
    engine = local_engine()
    with engine.begin() as db:
        matches = db.execute(text("SELECT id FROM kitchen_recipes WHERE code='D125' AND trim(name)='Shrimp & Pistacchio'")).scalars().all()
        assert len(matches) == 1, 'Expected one exact Kitchen recipe'
        for rid, restaurant_key in [(1,'winter-park'),(2,'mount-dora')]:
            row = db.execute(text("SELECT content_json,content_version FROM restaurant_menu_cards WHERE restaurant_id=:rid AND dish_key='shrimp-pistacchio' FOR UPDATE"),dict(rid=rid)).one()
            old = json.loads(row.content_json)
            assert old['restaurant_key'] == restaurant_key
            db.execute(text("INSERT INTO kitchen_visual_menu_links(restaurant_id,dish_key,recipe_id) VALUES (:rid,'shrimp-pistacchio',:recipe) ON CONFLICT(restaurant_id,dish_key) DO NOTHING"),dict(rid=rid,recipe=matches[0]))
            linked = db.execute(text("SELECT recipe_id FROM kitchen_visual_menu_links WHERE restaurant_id=:rid AND dish_key='shrimp-pistacchio'"),dict(rid=rid)).scalar_one()
            assert linked == matches[0], 'A different recipe was already linked'
            keep = {k:v for k,v in old.items() if k in ('restaurant_key','restaurant_name','dish_key','title','menu_source','photo_source','photo_source_page','photo_validation_status','source_sha256','description_phrases','sales_phrases')}
            if old != keep:
                db.execute(text("UPDATE restaurant_menu_cards SET content_json=:payload,content_version=content_version+1 WHERE restaurant_id=:rid AND dish_key='shrimp-pistacchio'"),dict(rid=rid,payload=json.dumps(keep,ensure_ascii=False)))
            live = read_card(db,rid,'shrimp-pistacchio')
            assert live['recipe'] and len(live['ingredients']) > 0
            assert {'Eggs','Fish','Crustaceans','Tree nuts (pistachio)','Wheat'} <= {a['name'] for a in live['allergens']}
        print('PASS: both restaurant cards read shared Kitchen recipe D125; five allergen groups inferred; no Kitchen fields persisted in Visual Menu.')
    engine.dispose()


if __name__ == '__main__':
    main()
