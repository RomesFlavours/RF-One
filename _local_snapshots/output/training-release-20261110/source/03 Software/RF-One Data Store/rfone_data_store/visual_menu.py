"""Read-through Kitchen projection. No recipe facts or inferred allergens persist."""
import json
import re
import sqlalchemy as sa
from .kitchen import menu_cards, recipes, components, steps, photos, menu_links

ALLERGEN_TERMS = {
    'Eggs': r'\beggs?\b|\buova\b|\btuorlo\b|\balbume\b',
    'Wheat': r'\bwheat\b|\bsemol[ai]\b|\bfrumento\b|\bgrano\b',
    'Fish': r'\banchov\w*|\bacciug\w*|\bsalmon\w*|\btuna\b|\bbranzino\b|\bcod\b',
    'Crustaceans': r'\bshrimps?\b|\bprawns?\b|\bgamber\w*|\blobster\b|\bcrab\b',
    'Tree nuts (pistachio)': r'\bpistac\w*',
    'Tree nuts (other)': r'\balmond\w*|\bwalnuts?\b|\bcashews?\b|\bhazelnut\w*|\bpecans?\b',
    'Peanuts': r'\bpeanuts?\b|\barachid\w*',
    'Milk': r'\bmilk\b|\bbutter\b|\bcheese\b|\bcream\b|\bmozzarella\b|\bricotta\b|\bmascarpone\b|\bgrana\b|\bparmigian\w*|\bpecorino\b|\bgorgonzola\b',
    'Soy': r'\bsoy\w*|\bsoia\b|\btofu\b',
    'Sesame': r'\bsesam\w*|\btahini\b',
    'Molluscs': r'\bclams?\b|\bmussels?\b|\boysters?\b|\bcalamari\b|\bsquid\b|\bvongol\w*',
    'Mustard': r'\bmustard\b|\bdijon\b|\bsenape\b',
    'Celery': r'\bcelery\b|\bsedano\b',
    'Lupin': r'\blupin\w*',
}


def read_card(db, restaurant_id, dish_key):
    """Resolve the exact restaurant link on every request; never fall back to text matching."""
    row = db.execute(sa.select(menu_cards.c.title, menu_cards.c.content_json,
                              menu_links.c.recipe_id, menu_links.c.standard_photo_id)
                     .select_from(menu_cards.outerjoin(menu_links, sa.and_(
                         menu_cards.c.restaurant_id == menu_links.c.restaurant_id,
                         menu_cards.c.dish_key == menu_links.c.dish_key)))
                     .where(menu_cards.c.restaurant_id == restaurant_id,
                            menu_cards.c.dish_key == dish_key)).mappings().first()
    if not row:
        return None
    editorial = json.loads(row['content_json'])
    result = dict(title=row['title'], restaurant_name=editorial['restaurant_name'],
                  restaurant_id=restaurant_id, dish_key=dish_key, recipe=None,
                  ingredients=[], components=[], preparations=[], allergens=[], issues=[], steps=[], photo_uri=None)
    result['description_phrases']=editorial.get('description_phrases',[])
    result['sales_phrases']=editorial.get('sales_phrases',[])
    result['content_version']=db.execute(sa.select(menu_cards.c.content_version).where(
        menu_cards.c.restaurant_id==restaurant_id,menu_cards.c.dish_key==dish_key)).scalar_one()
    if row['recipe_id'] is None:
        result['issues'].append('This dish has not been linked to a recipe yet.')
        return result
    recipe = db.execute(sa.select(recipes).where(recipes.c.id == row['recipe_id'])).mappings().one()
    fields = ['name','description','dietary_class','dietary_evidence','appearance','aroma','taste',
              'texture','serving_temperature','organoleptic_notes','plating_instructions',
              'portion_count','portion_weight_g','ingredient_weight_g','cooked_yield_g',
              'actual_work_minutes','kcal','protein_g','carbohydrate_g','fat_g','cholesterol_mg',
              'nutrition_basis','validation_status']
    result['recipe'] = {f: recipe[f] for f in fields}
    evidence = {}

    def walk(recipe_id, trail):
        if recipe_id in trail:
            result['issues'].append('A circular preparation reference needs correction.')
            return
        if len(trail) >= 30:
            result['issues'].append('Preparation nesting exceeds the supported depth.')
            return
        lines = db.execute(sa.select(components).where(components.c.recipe_id == recipe_id)
                           .order_by(components.c.position)).mappings().all()
        if not lines:
            result['issues'].append('A recipe or preparation has no ingredient breakdown.')
        for line in lines:
            label = line['ingredient_reference'] or line['preparation_reference'] or 'Unnamed component'
            label = re.sub(r'^(?:F-|Pr\d+-)', '', label).strip()
            if not trail and label not in result['components']:
                result['components'].append(label)
            if line['preparation_id'] is not None:
                result['preparations'].append(dict(name=label, quantity=line['quantity'], unit=line['unit']))
                walk(line['preparation_id'], trail + (recipe_id,))
            elif line['preparation_reference']:
                result['issues'].append('Unresolved preparation: '+label)
            else:
                result['ingredients'].append(dict(name=label, quantity=line['quantity'], unit=line['unit'],
                                                 nested=bool(trail), notes=line['notes']))
                for allergen, pattern in ALLERGEN_TERMS.items():
                    if re.search(pattern, label, re.I):
                        evidence.setdefault(allergen, set()).add(label)
                if re.search(r'\bflour\b|\bpasta\b|\bbread\b|\bpesto\b|\bsauce\b|\bstock\b|\bchocolate\b', label, re.I):
                    result['issues'].append('Confirm the full ingredient specification for '+label+'.')

    walk(recipe['id'], ())
    result['allergens'] = [dict(name=k, ingredients=sorted(v), status='inferred') for k,v in sorted(evidence.items())]
    result['issues'] = list(dict.fromkeys(result['issues']))
    result['steps'] = db.execute(sa.select(steps.c.instruction).where(steps.c.recipe_id == recipe['id'])
                                .order_by(steps.c.position)).scalars().all()
    if row['standard_photo_id'] is not None:
        result['photo_uri'] = db.execute(sa.select(photos.c.asset_uri).where(
            photos.c.id == row['standard_photo_id'], photos.c.recipe_id == recipe['id'])).scalar_one_or_none()
    return result
