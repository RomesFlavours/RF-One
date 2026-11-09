"""Kitchen visibility is based on Clover categories, never product-name guesses."""
from sqlalchemy import select
from rfone_data_store import models as m


def is_beverage(categories):
    for category in categories:
        name = ' '.join(category.casefold().replace('-', ' ').split())
        if name in {'drink', 'drinks', 'beverage', 'beverages', 'beer', 'beers',
                    'wine', 'wines', 'cocktail', 'cocktails', 'spirits',
                    'coffee milk tea'} or name.startswith('wine '):
            return True
    return False


def categories_by_line(db, location_id, order_ids):
    rows = db.execute(select(m.OrderItem.source_line_item_id, m.Category.name)
        .join(m.Order, m.Order.id == m.OrderItem.order_id)
        .join(m.ItemCategory, m.ItemCategory.item_id == m.OrderItem.item_id)
        .join(m.Category, m.Category.id == m.ItemCategory.category_id)
        .where(m.Order.location_id == location_id, m.Order.source_order_id.in_(order_ids)))
    result = {}
    for line_id, category in rows:
        result.setdefault(line_id, []).append(category)
    return result


def timing_by_line(db, location_id, order_ids):
    rows=db.execute(select(m.OrderItem.source_line_item_id, m.OrderItemModifier.name_raw)
        .join(m.Order, m.Order.id==m.OrderItem.order_id)
        .join(m.OrderItemModifier,m.OrderItemModifier.order_item_id==m.OrderItem.id)
        .join(m.Modifier,m.Modifier.id==m.OrderItemModifier.modifier_id)
        .join(m.ModifierGroup,m.ModifierGroup.id==m.Modifier.modifier_group_id)
        .where(m.Order.location_id==location_id,m.Order.source_order_id.in_(order_ids),
               m.ModifierGroup.name=='When Serve'))
    result={}
    for line_id,name in rows:
        if name and name not in result.setdefault(line_id,[]): result[line_id].append(name)
    return result


def kitchen_payload(payload, category_lookup, timing_lookup=None):
    return {**payload, 'lines': [{**line, 'service_timing':
        (timing_lookup or {}).get(line.get('id'),line.get('service_timing',[]))}
        for line in payload.get('lines', [])
        if not is_beverage(category_lookup.get(line.get('id'), line.get('categories', [])))]}
