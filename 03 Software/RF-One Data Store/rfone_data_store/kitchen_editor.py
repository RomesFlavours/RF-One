"""Transactional recipe/category and composition editing; source evidence stays intact."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from uuid import UUID
import re
import sqlalchemy as sa
from . import kitchen_configuration as cfg
from .kitchen import recipes, components, steps, photos

NUTRIENTS=('kcal','protein_g','carbohydrate_g','fat_g','cholesterol_mg')
DERIVED=('total_cost','cost_per_kg')+NUTRIENTS
LINE_DERIVED=('cost','cost_per_kg')+NUTRIENTS


class EditorError(ValueError):pass
class StaleRecipe(EditorError):pass


def is_work_time(value):
    return 'actualworktime' in re.sub(r'[^a-z0-9]','',str(value or '').casefold())


def integer(value):
    if value in (None,''):return None
    try:
        result=int(value)
        if str(result)!=str(value) or result<1:raise ValueError()
        return result
    except (ValueError,TypeError):raise EditorError('Invalid record selection.')


def amount(value,minutes=False):
    if value in (None,''):return None
    try:
        result=Decimal(str(value))
        limit=Decimal('10000000000' if minutes else '1000000000000')
        if not result.is_finite() or result<0 or result>=limit or result.as_tuple().exponent<(-4 if minutes else -6):raise ValueError()
        return result
    except (ValueError,InvalidOperation):raise EditorError('Enter a non-negative number with at most '+('4' if minutes else '6')+' decimal places.')


def record(db,rid,lock=False):
    query=sa.select(recipes).where(recipes.c.id==rid)
    if lock:query=query.with_for_update()
    row=db.execute(query).mappings().first()
    if row is None:raise EditorError('This recipe no longer exists.')
    return dict(row)


def options(db):
    rows=[dict(r) for r in db.execute(sa.select(cfg.items).where(cfg.items.c.section.in_(['CATEGORY','COMPONENT'])).order_by(cfg.items.c.name)).mappings()]
    return dict(categories=[dict(id=r['id'],name=r['name'],archived=r['archived']) for r in rows if r['section']=='CATEGORY'],
        components=[dict(id=r['id'],name=r['name'],archived=r['archived']) for r in rows if r['section']=='COMPONENT' and not is_work_time(r['name'])],
        preparations=[dict(r) for r in db.execute(sa.select(recipes.c.id,recipes.c.code,recipes.c.name).where(recipes.c.kind=='preparation').order_by(recipes.c.name)).mappings() if not is_work_time(r['name'])])


def missing_source_composition():
    return sa.and_(recipes.c.source_sheet=='DishPrep-List',
        ~sa.exists().where(components.c.recipe_id==recipes.c.id))


def summary(db,rid):
    r=record(db,rid)
    category=db.scalar(sa.select(cfg.items.c.name).where(cfg.items.c.id==r['category_id'])) if r['category_id'] else None
    has_photo=bool(db.scalar(sa.select(sa.exists().where(photos.c.recipe_id==rid))))
    missing_composition=bool(db.scalar(sa.select(missing_source_composition()).where(recipes.c.id==rid)))
    return dict(id=r['id'],name=r['name'],kind=r['kind'],category_id=r['category_id'],category=category,revision=r['revision'],has_photo=has_photo,missing_source_composition=missing_composition,
        actual_work_minutes=str(r['actual_work_minutes']) if r['actual_work_minutes'] is not None else '',
        elapsed_preparation_minutes=str(r['elapsed_preparation_minutes']) if r['elapsed_preparation_minutes'] is not None else '')


def listing(db):
    query=sa.select(recipes.c.id,recipes.c.name,recipes.c.kind,recipes.c.category_id,cfg.items.c.name.label('category'),sa.exists().where(photos.c.recipe_id==recipes.c.id).label('has_photo'),missing_source_composition().label('missing_source_composition')).outerjoin(cfg.items,recipes.c.category_id==cfg.items.c.id).order_by(sa.func.lower(recipes.c.name),recipes.c.id)
    return [dict(r) for r in db.execute(query).mappings() if not is_work_time(r['name'])]


def save_metadata(db,data):
    rid=integer(data.get('id'));category=integer(data.get('category_id'))
    name=(data.get('name') or '').strip()
    if not name or len(name)>1000:raise EditorError('Enter a recipe name between 1 and 1,000 characters.')
    existing=record(db,rid,True) if rid else None
    if existing and integer(data.get('revision'))!=existing['revision']:raise StaleRecipe('This recipe changed after you opened it. Close and reopen it before saving.')
    if is_work_time(name):raise EditorError('Actual Work Time belongs in the recipe preparation-time fields, not in Recipes or Preparations.')
    times={field:amount(data[field],True) if field in data else existing[field] if existing else None
           for field in ('actual_work_minutes','elapsed_preparation_minutes')}
    if category:
        choice=db.execute(sa.select(cfg.items).where(cfg.items.c.id==category,cfg.items.c.section=='CATEGORY')).mappings().first()
        if not choice or choice['archived'] and (not existing or existing['category_id']!=category):raise EditorError('Choose an active Category from Configuration.')
    if existing:
        values=dict(name=name,category_id=category,revision=existing['revision']+1,validation_status='pending',validated_at=None,validated_by_id=None,**times)
        if times['actual_work_minutes']!=existing['actual_work_minutes']:values.update(total_cost=None,cost_per_kg=None)
        db.execute(recipes.update().where(recipes.c.id==rid).values(**values))
    else:
        kind=data.get('kind')
        if kind not in ('dish','preparation'):raise EditorError('Choose Recipes or Preparations.')
        try:draft=UUID(data.get('draft_key','')).hex
        except (ValueError,AttributeError):raise EditorError('Reopen the new recipe form and try again.')
        code=('D-' if kind=='dish' else 'PR-')+draft
        prior=db.execute(sa.select(recipes).where(recipes.c.code==code)).mappings().first()
        if prior:
            if prior['name']!=name or prior['category_id']!=category:raise StaleRecipe('This draft was already saved. Close and reopen its record.')
            if any(field in data and prior[field]!=times[field] for field in times):raise StaleRecipe('This draft was already saved with different preparation times. Close and reopen its record.')
            rid=prior['id']
        else:
            rid=db.execute(recipes.insert().values(code=code,name=name,kind=kind,category_id=category,**times).returning(recipes.c.id)).scalar_one()
    return summary(db,rid)


def normalized_reference(value):
    text=cfg.clean_name(value)
    if len(text)>2 and text[1]=='-':text=text[2:]
    return cfg.normalize(text)


def composition(db,rid):
    r=record(db,rid);choices=options(db)
    masters={cfg.normalize(x['name']):x['id'] for x in choices['components']}
    source_steps=[dict(s) for s in db.execute(sa.select(steps).where(steps.c.recipe_id==rid)).mappings()]
    step_by_source={s['source_row']:s for s in source_steps if s['source_row'] is not None}
    used=set();lines=[]
    for c in db.execute(sa.select(components).where(components.c.recipe_id==rid).order_by(components.c.position)).mappings():
        duplicate=step_by_source.get(c['source_row']) if c['source_row'] is not None else None
        if duplicate:used.add(duplicate['id'])
        master=c['component_item_id'] or (masters.get(normalized_reference(c['ingredient_reference'])) if c['ingredient_reference'] else None)
        lines.append(dict(id=c['id'],step_id=duplicate['id'] if duplicate else None,
            component=('id:'+str(master)) if master else ('legacy' if c['ingredient_reference'] else ''),
            component_label=c['ingredient_reference'] or '',preparation=('id:'+str(c['preparation_id'])) if c['preparation_id'] else ('legacy' if c['preparation_reference'] else ''),
            preparation_label=c['preparation_reference'] or '',grams=str(c['quantity']) if c['quantity'] is not None else '',
            instructions=c['notes'] or (duplicate['instruction'] if duplicate else ''),position=c['position']))
    for s in source_steps:
        if s['id'] not in used:lines.append(dict(id=None,step_id=s['id'],component='',component_label='',preparation='',preparation_label='',grams='',instructions=s['instruction'],position=s['position']))
    return dict(recipe=summary(db,rid),rows=sorted(lines,key=lambda x:x['position']),
                work_minutes=str(r['actual_work_minutes']) if r['actual_work_minutes'] is not None else '',**choices)


def resolve(db,value,kind,current=None):
    if not value:return None,None
    if value=='legacy':
        if not current:raise EditorError('Choose an item from the list.')
        if is_work_time(current):raise EditorError('Set preparation times in Edit; Actual Work Time is not a component.')
        return None,current
    if not isinstance(value,str) or not value.startswith('id:'):raise EditorError('Invalid item selection.')
    identifier=integer(value[3:])
    if kind=='component':
        row=db.execute(sa.select(cfg.items).where(cfg.items.c.id==identifier,cfg.items.c.section=='COMPONENT')).mappings().first()
        same=bool(row and current and normalized_reference(current)==cfg.normalize(row['name']))
        if row and is_work_time(row['name']):raise EditorError('Actual Work Time is not a component. Use Edit.')
        if not row or row['archived'] and not same:raise EditorError('Choose an active component from Configuration.')
        return identifier,current if same else row['name']
    row=db.execute(sa.select(recipes).where(recipes.c.id==identifier,recipes.c.kind=='preparation')).mappings().first()
    if not row:raise EditorError('Choose a valid preparation.')
    if is_work_time(row['name']):raise EditorError('Actual Work Time is not a preparation. Use Edit.')
    return identifier,row['code']+'-'+row['name']


def save_composition(db,rid,data):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    r=record(db,rid,True)
    if integer(data.get('revision'))!=r['revision']:raise StaleRecipe('This recipe changed after you opened it. Close and reopen it before saving.')
    incoming=data.get('rows')
    if not isinstance(incoming,list) or len(incoming)>500:raise EditorError('A recipe may contain at most 500 rows.')
    old={x['id']:dict(x) for x in db.execute(sa.select(components).where(components.c.recipe_id==rid)).mappings()}
    old_steps={x['id']:dict(x) for x in db.execute(sa.select(steps).where(steps.c.recipe_id==rid)).mappings()}
    draft=[];seen=set();seen_steps=set()
    for line in incoming:
        if not isinstance(line,dict):raise EditorError('Invalid composition row.')
        cid=integer(line.get('id'));sid=integer(line.get('step_id'))
        if cid and (cid not in old or cid in seen):raise EditorError('A component row is duplicated or belongs to another recipe.')
        if sid and (sid not in old_steps or sid in seen_steps):raise EditorError('An instruction row is duplicated or belongs to another recipe.')
        if cid:seen.add(cid)
        if sid:seen_steps.add(sid)
        current=old.get(cid,{})
        if line.get('component') and line.get('preparation'):
            raise EditorError('Each row must contain either a component or a preparation, never both. Clear one selection.')
        if cid and sid and (current.get('source_row') is None or current['source_row']!=old_steps[sid]['source_row']):raise EditorError('Invalid component/instruction pairing.')
        master,ingredient=resolve(db,line.get('component'),'component',current.get('ingredient_reference'))
        prep,prep_ref=resolve(db,line.get('preparation'),'preparation',current.get('preparation_reference'))
        if prep and prep==current.get('preparation_id'):prep_ref=current['preparation_reference']
        grams=amount(line.get('grams'));note=str(line.get('instructions') or '')
        if len(note)>20000:raise EditorError('Instructions are too long.')
        if not ingredient and not prep_ref and grams is not None:raise EditorError('Choose a component or preparation for the grams entered.')
        if not ingredient and not prep_ref and not note.strip():continue
        draft.append(dict(id=cid,step_id=sid,component_item_id=master,ingredient_reference=ingredient,
                          preparation_id=prep,preparation_reference=prep_ref,quantity=grams,notes=note or None))
    work=r['actual_work_minutes']
    if 'work_minutes' in data and amount(data['work_minutes'],True)!=work:
        raise EditorError('Change preparation times in the recipe Edit dialog, not Components.')
    graph=defaultdict(set)
    for parent,child in db.execute(sa.select(components.c.recipe_id,components.c.preparation_id).where(components.c.preparation_id.is_not(None),components.c.recipe_id!=rid)):
        graph[parent].add(child)
    graph[rid]={d['preparation_id'] for d in draft if d['preparation_id']}
    pending=list(graph[rid]);visited=set()
    while pending:
        node=pending.pop()
        if node==rid:raise EditorError('A preparation cannot contain itself, directly or through another preparation.')
        if node not in visited:visited.add(node);pending.extend(graph[node])
    before=composition(db,rid)
    comparison=lambda lines:[(x.get('id'),x.get('step_id'),x.get('ingredient_reference'),x.get('preparation_reference'),x.get('quantity'),x.get('notes')) for x in lines]
    original=[]
    for line in before['rows']:
        c=old.get(line['id'],{})
        original.append(dict(id=line['id'],step_id=line['step_id'],ingredient_reference=c.get('ingredient_reference'),preparation_reference=c.get('preparation_reference'),quantity=c.get('quantity'),notes=line['instructions'] or None))
    if comparison(original)==comparison(draft) and work==r['actual_work_minutes']:return composition(db,rid)
    # Reserve positive positions to avoid transient unique conflicts while keeping IDs.
    offset=max([x['position'] for x in list(old.values())+list(old_steps.values())]+[0])+len(draft)+10
    db.execute(components.update().where(components.c.recipe_id==rid).values(position=components.c.position+offset))
    db.execute(steps.update().where(steps.c.recipe_id==rid).values(position=steps.c.position+offset))
    kept=set();kept_steps=set()
    food_before=[(x['ingredient_reference'],x['preparation_reference'],x['quantity']) for x in old.values()]
    food_after=[]
    for pos,d in enumerate(draft,1):
        cid=d['id'];sid=d['step_id']
        source_row=old.get(cid,{}).get('source_row') or (old_steps.get(sid,{}).get('source_row') if not cid else None)
        is_food=bool(d['ingredient_reference'] or d['preparation_reference'])
        if is_food:
            food_after.append((d['ingredient_reference'],d['preparation_reference'],d['quantity']))
            values={k:d[k] for k in ('component_item_id','ingredient_reference','preparation_id','preparation_reference','quantity','notes')}
            values.update(position=pos,unit='g')
            if not cid or any(old[cid].get(k)!=values[k] for k in ('ingredient_reference','preparation_reference','quantity')):
                values.update({k:None for k in LINE_DERIVED})
            if cid:db.execute(components.update().where(components.c.id==cid).values(**values))
            else:cid=db.execute(components.insert().values(recipe_id=rid,source_row=source_row,**values).returning(components.c.id)).scalar_one()
            kept.add(cid)
        if d['notes'] and (not is_food or sid and source_row is not None):
            values=dict(position=pos,instruction=d['notes'])
            if sid:db.execute(steps.update().where(steps.c.id==sid).values(**values))
            else:sid=db.execute(steps.insert().values(recipe_id=rid,**values).returning(steps.c.id)).scalar_one()
            kept_steps.add(sid)
    db.execute(components.delete().where(components.c.recipe_id==rid,components.c.id.not_in(kept)))
    db.execute(steps.delete().where(steps.c.recipe_id==rid,steps.c.id.not_in(kept_steps)))
    weight=None if any(q is None for _,_,q in food_after) else sum((q for _,_,q in food_after),Decimal(0))
    values=dict(ingredient_weight_g=weight,actual_work_minutes=work,revision=r['revision']+1,validation_status='pending',validated_at=None,validated_by_id=None)
    if food_before!=food_after:values.update({k:None for k in DERIVED})
    elif work!=r['actual_work_minutes']:values.update(total_cost=None,cost_per_kg=None)
    db.execute(recipes.update().where(recipes.c.id==rid).values(**values))
    return composition(db,rid)
