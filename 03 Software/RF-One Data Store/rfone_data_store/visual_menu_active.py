"""Live active-menu membership and recipe data; only trainer phrases are persisted."""
import json
import sqlalchemy as sa
from .models import Location,RestaurantLocation,Restaurant
from .kitchen import recipes,menu_cards,menu_links
from .kitchen_configuration import items
from .kitchen_menus import menus,entries,active_for_location
from .kitchen_plating import current_photo
from .visual_menu import populate_recipe

def open_restaurant_links():
    return sa.and_(RestaurantLocation.valid_to.is_(None),
        sa.or_(RestaurantLocation.valid_from.is_(None),RestaurantLocation.valid_from<=sa.func.now()))

def editorial_record(db,restaurant_id,recipe_id):
    key='recipe-'+str(recipe_id)
    return db.execute(sa.select(menu_cards).join(menu_links,sa.and_(menu_links.c.restaurant_id==menu_cards.c.restaurant_id,menu_links.c.dish_key==menu_cards.c.dish_key))
        .where(menu_cards.c.restaurant_id==restaurant_id,menu_links.c.recipe_id==recipe_id)
        .order_by((menu_cards.c.dish_key==key).desc(),menu_cards.c.dish_key).limit(1)).mappings().first()

def read_editorial(db,restaurant_id,recipe_id):
    restaurant=db.scalar(sa.select(Restaurant.name).where(Restaurant.id==restaurant_id))
    recipe=db.execute(sa.select(recipes.c.id,recipes.c.name).where(recipes.c.id==recipe_id,recipes.c.kind=='dish')).mappings().first()
    if restaurant is None or recipe is None:return None
    row=editorial_record(db,restaurant_id,recipe_id);content=json.loads(row['content_json']) if row else {}
    photo=current_photo(db,recipe_id)
    return dict(restaurant_id=restaurant_id,restaurant_name=restaurant,recipe_id=recipe_id,title=recipe['name'],
        dish_key=row['dish_key'] if row else 'recipe-'+str(recipe_id),content_version=row['content_version'] if row else 0,
        description_phrases=content.get('description_phrases',[]),sales_phrases=content.get('sales_phrases',[]),
        photo_uri=photo['asset_uri'] if photo else None)

def management_menus(db,restaurant_id):
    return [dict(row) for row in db.execute(sa.select(menus).join(RestaurantLocation,RestaurantLocation.location_id==menus.c.location_id)
        .where(RestaurantLocation.restaurant_id==restaurant_id,open_restaurant_links()).distinct()
        .order_by(menus.c.archived,menus.c.name,menus.c.id)).mappings()]

def menu_recipe_ids(db,menu_ids):
    return set(db.scalars(sa.select(entries.c.recipe_id).where(entries.c.menu_id.in_(menu_ids),entries.c.recipe_id.is_not(None))))

def editorial_listing(db,restaurant_id,recipe_ids=None):
    category=items.alias('category');result=[]
    query=sa.select(recipes.c.id,recipes.c.name,category.c.name.label('category')).outerjoin(category,category.c.id==recipes.c.category_id).where(recipes.c.kind=='dish').order_by(recipes.c.name)
    if recipe_ids is not None:query=query.where(recipes.c.id.in_(recipe_ids))
    for row in db.execute(query).mappings():
        editorial=editorial_record(db,restaurant_id,row['id']) if restaurant_id is not None else None;content=json.loads(editorial['content_json']) if editorial else {}
        result.append(dict(row,description_count=len(content.get('description_phrases',[])) if restaurant_id is not None else None,sales_count=len(content.get('sales_phrases',[])) if restaurant_id is not None else None))
    return result

def read_home(db):
    result=[]
    for location in db.execute(sa.select(Location.id,Location.name).order_by(Location.name)).mappings():
        menu=active_for_location(db,location['id']);groups={}
        if menu:
            for entry in menu['entries']:
                if entry['area_id'] not in groups:groups[entry['area_id']]=dict(id=entry['area_id'],name=entry['area_name'],entries=[])
                photo=current_photo(db,entry['recipe_id']) if entry['recipe_id'] else None
                groups[entry['area_id']]['entries'].append(dict(id=entry['id'],label=entry['label'],recipe_id=entry['recipe_id'],
                    photo_uri=photo['asset_uri'] if photo else None))
        result.append(dict(location_id=location['id'],name=location['name'],menu_name=menu['name'] if menu else None,areas=list(groups.values())))
    return result

def read_entry(db,location_id,entry_id):
    row=db.execute(sa.select(entries,menus.c.name.label('menu_name'),Location.name.label('location_name'),items.c.name.label('area_name'))
        .join(menus,menus.c.id==entries.c.menu_id).join(Location,Location.id==menus.c.location_id)
        .join(items,items.c.id==entries.c.area_id).join(recipes,recipes.c.id==entries.c.recipe_id)
        .where(entries.c.id==entry_id,menus.c.location_id==location_id,menus.c.active.is_(True),menus.c.archived.is_(False),recipes.c.kind=='dish')).mappings().first()
    if row is None:return None
    restaurant_ids=set(db.scalars(sa.select(RestaurantLocation.restaurant_id).where(RestaurantLocation.location_id==location_id,open_restaurant_links())))
    restaurant_id=next(iter(restaurant_ids)) if len(restaurant_ids)==1 else None
    key='recipe-'+str(row['recipe_id']);editorial=None
    if restaurant_id is not None:
        editorial=editorial_record(db,restaurant_id,row['recipe_id'])
    content=json.loads(editorial['content_json']) if editorial else {}
    result=dict(title=row['label'],restaurant_name=row['location_name'],restaurant_id=restaurant_id,
        location_id=location_id,entry_id=entry_id,recipe_id=row['recipe_id'],menu_name=row['menu_name'],area_name=row['area_name'],
        dish_key=editorial['dish_key'] if editorial else key,content_version=editorial['content_version'] if editorial else 0,
        description_phrases=content.get('description_phrases',[]),sales_phrases=content.get('sales_phrases',[]),
        recipe=None,ingredients=[],components=[],preparations=[],allergens=[],issues=[],steps=[],photo_uri=None)
    photo=current_photo(db,row['recipe_id'])
    return populate_recipe(db,result,row['recipe_id'],photo['id'] if photo else None)

def peers(db,card):
    rows=db.execute(sa.select(entries.c.id,menus.c.location_id,Location.name)
        .join(menus,menus.c.id==entries.c.menu_id).join(Location,Location.id==menus.c.location_id)
        .where(entries.c.recipe_id==card['recipe_id'],menus.c.active.is_(True),menus.c.archived.is_(False),menus.c.location_id!=card['location_id'])
        .order_by(Location.name,entries.c.position)).mappings()
    seen=set();result=[]
    for row in rows:
        if row['location_id'] not in seen:result.append(dict(location_id=row['location_id'],entry_id=row['id'],name=row['name']));seen.add(row['location_id'])
    return result

def legacy_entry(db,restaurant_id,dish_key):
    return db.execute(sa.select(menus.c.location_id,entries.c.id.label('entry_id'))
        .select_from(menu_links.join(RestaurantLocation,RestaurantLocation.restaurant_id==menu_links.c.restaurant_id)
            .join(menus,menus.c.location_id==RestaurantLocation.location_id).join(entries,sa.and_(entries.c.menu_id==menus.c.id,entries.c.recipe_id==menu_links.c.recipe_id)))
        .where(menu_links.c.restaurant_id==restaurant_id,menu_links.c.dish_key==dish_key,open_restaurant_links(),menus.c.active.is_(True),menus.c.archived.is_(False))
        .order_by(entries.c.position).limit(1)).mappings().first()

class PhraseConflict(ValueError):pass

def save_phrases(db,card,version,values):
    if card['restaurant_id'] is None:raise ValueError('Presentation phrases are unavailable for this location.')
    # Serialize against activation/archive so a stale active-menu link cannot be edited.
    if db.get_bind().dialect.name=='postgresql':db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    current=read_entry(db,card['location_id'],card['entry_id'])
    if current is None:raise PhraseConflict('The active menu changed. Reopen Visual Menu before saving.')
    return save_editorial(db,current['restaurant_id'],current['recipe_id'],version,values)

def save_editorial(db,restaurant_id,recipe_id,version,values):
    if db.get_bind().dialect.name=='postgresql':db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    current=read_editorial(db,restaurant_id,recipe_id)
    if current is None:raise ValueError('Choose an existing restaurant and dish recipe.')
    if current['content_version']!=version:raise PhraseConflict('This card changed while you were editing. Your draft is preserved. Review the current phrases before saving again.')
    content={field:values[field] for field in ('description_phrases','sales_phrases')}
    if version==0:
        db.execute(menu_cards.insert().values(restaurant_id=current['restaurant_id'],dish_key=current['dish_key'],title='Presentation phrases',content_version=1,validation_status='pending',content_json=json.dumps(content,ensure_ascii=False)))
        db.execute(menu_links.insert().values(restaurant_id=current['restaurant_id'],dish_key=current['dish_key'],recipe_id=current['recipe_id']))
    else:
        old=db.scalar(sa.select(menu_cards.c.content_json).where(menu_cards.c.restaurant_id==current['restaurant_id'],menu_cards.c.dish_key==current['dish_key']))
        merged=json.loads(old);merged.update(content)
        changed=db.execute(menu_cards.update().where(menu_cards.c.restaurant_id==current['restaurant_id'],menu_cards.c.dish_key==current['dish_key'],menu_cards.c.content_version==version)
            .values(content_json=json.dumps(merged,ensure_ascii=False),content_version=version+1))
        if changed.rowcount!=1:raise PhraseConflict('This card changed while you were editing. Your draft is preserved.')
