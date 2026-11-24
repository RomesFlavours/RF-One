"""Read-through behavior, nested allergens and restaurant isolation; in-memory."""
import sqlalchemy as sa
from rfone_data_store.kitchen import recipes, components, steps, menu_cards, menu_links, photos
from rfone_data_store.visual_menu import read_card


def main():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE restaurants(id INTEGER PRIMARY KEY)')
        db.exec_driver_sql('CREATE TABLE acting_identities(id INTEGER PRIMARY KEY)')
        for table in (menu_cards, recipes, components, steps, photos, menu_links):
            table.create(db)
        import json
        for rid in (1,2):
            db.execute(menu_cards.insert().values(restaurant_id=rid,dish_key='dish',title='Dish',content_version=1,
                validation_status='pending',content_json=json.dumps({'restaurant_name':str(rid)})))
        db.execute(recipes.insert(), [dict(id=1,code='D',name='Dish',kind='dish'),dict(id=2,code='P',name='Pasta',kind='preparation')])
        db.execute(menu_links.insert().values(restaurant_id=1,dish_key='dish',recipe_id=1))
        db.execute(components.insert().values(recipe_id=1,position=1,preparation_id=2))
        db.execute(components.insert().values(recipe_id=1,position=2,ingredient_reference='F-Anchovy'))
        db.execute(components.insert(),[dict(recipe_id=2,position=1,ingredient_reference='F-Eggs No Cage'),dict(recipe_id=2,position=2,ingredient_reference='F-Flour Semola')])
        before = db.execute(sa.select(menu_cards.c.content_json)).all()
        first = read_card(db,1,'dish')
        assert {'Eggs','Wheat','Fish'} <= {a['name'] for a in first['allergens']}
        assert read_card(db,2,'dish')['recipe'] is None
        assert read_card(db,3,'dish') is None
        db.execute(components.update().where(components.c.ingredient_reference=='F-Anchovy').values(ingredient_reference='F-Milk'))
        second = read_card(db,1,'dish')
        assert 'Fish' not in {a['name'] for a in second['allergens']}
        assert 'Milk' in {a['name'] for a in second['allergens']}
        assert db.execute(sa.select(menu_cards.c.content_json)).all() == before
        db.execute(photos.insert().values(id=1,recipe_id=1,asset_uri='https://example.org/dish.jpg'))
        db.execute(menu_links.update().values(standard_photo_id=1))
        assert read_card(db,1,'dish')['photo_uri']=='https://example.org/dish.jpg'
        db.execute(photos.update().values(asset_uri='https://example.org/new-dish.jpg'))
        assert read_card(db,1,'dish')['photo_uri']=='https://example.org/new-dish.jpg'
        db.execute(components.insert().values(recipe_id=2,position=3,preparation_id=1))
        assert any('circular' in i for i in read_card(db,1,'dish')['issues'])
        db.execute(components.insert().values(recipe_id=1,position=3,preparation_reference='Unknown sauce'))
        assert any('Unresolved' in i for i in read_card(db,1,'dish')['issues'])
        # 24 Nov 2026: pine nuts are a nut warning; editor preparation codes never reach the card.
        db.execute(components.delete().where(components.c.preparation_reference=='Unknown sauce'))
        db.execute(components.delete().where(components.c.recipe_id==2, components.c.preparation_id==1))
        key = '0123456789abcdef0123456789abcdef'
        db.execute(recipes.insert().values(id=3,code='PR-'+key,name='Zucchini Baked',kind='preparation'))
        db.execute(components.insert().values(recipe_id=1,position=4,preparation_id=3,preparation_reference='PR-'+key+'-Zucchini Baked'))
        db.execute(components.insert().values(recipe_id=3,position=1,ingredient_reference='Pesto Genovese (pine nuts)'))
        card = read_card(db,1,'dish')
        assert 'Tree nuts (pine nuts)' in {a['name'] for a in card['allergens']}
        assert 'Zucchini Baked' in card['components'] and not any(c.startswith('PR-') for c in card['components'])
        assert any(p['name'] == 'Zucchini Baked' for p in card['preparations'])
    engine.dispose()
    print('PASS: live changes, nested allergens, cycle detection, unresolved preparations, restaurant isolation, no recipe copies, pine nuts, editor codes')


if __name__ == '__main__':
    main()
