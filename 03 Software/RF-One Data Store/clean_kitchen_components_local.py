"""PO-approved Components cleanup; recipe facts and other lists are protected."""
import argparse
from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

import sqlalchemy as sa
from import_kitchen_excel import local_engine
from rfone_data_store.kitchen_configuration import items, clean_name, normalize

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/kitchen-configuration'


def key(value):
    return normalize(clean_name(value)) if isinstance(value,str) and value.strip() else None


def plan(rows, originals, references):
    decisions=[]
    destinations=defaultdict(list)
    for row in rows:
        source=originals.get(row['id'])
        if source is None:
            raise ValueError(f'Component {row["id"]} has no original import mapping; review before modifying')
        original=source['name']
        target=clean_name(original[2:])
        if row['name'] not in (original,target):
            raise ValueError(f'Component changed since import: {row["id"]}; no overwrite')
        uses=references.get(key(original),[])
        keep=original.startswith('F-') or bool(uses)
        decision=dict(id=row['id'],original=original,current=row['name'],name=target,
                      action=('keep' if row['name']==target else 'rename') if keep else 'remove',
                      reason='F- component' if original.startswith('F-') else ('Used in recipe' if uses else 'Not used in recipes'),
                      recipe_ids=sorted(set(uses)))
        decisions.append(decision)
        if keep:
            destinations[key(target)].append(row['id'])
    collisions={name:ids for name,ids in destinations.items() if len(ids)>1}
    if collisions:
        raise ValueError(f'Removing prefixes would create duplicate names: {collisions}')
    return decisions


def protected(db):
    tables={
        'kitchen_recipes': 'id', 'kitchen_recipe_components':'id','kitchen_recipe_steps':'id',
        'kitchen_recipe_photos':'id', 'kitchen_visual_menu_links':'restaurant_id,dish_key',
        'restaurant_menu_cards':'restaurant_id,dish_key','suppliers':'id',
    }
    result={}
    for table,order in tables.items():
        digest=hashlib.sha256();count=0
        for value in db.execute(sa.text(f'SELECT to_jsonb(t)::text FROM {table} t ORDER BY {order}')).scalars():
            digest.update(value.encode());digest.update(b'\n');count+=1
        result[table]=dict(count=count,sha256=digest.hexdigest())
    data=db.execute(sa.select(items).where(items.c.section!='COMPONENT').order_by(items.c.id)).mappings().all()
    result['other_configuration_lists']=hashlib.sha256(json.dumps([dict(r) for r in data],default=str,sort_keys=True).encode()).hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--persist',action='store_true');args=parser.parse_args()
    audit=json.loads((OUT/'excel-import-both-committed.json').read_text(encoding='utf-8'))
    originals={r['id']:r for r in audit['mappings'] if r['section']=='COMPONENT'}
    engine=local_engine()
    with engine.begin() as db:
        db.execute(sa.text('LOCK TABLE kitchen_configuration_items IN SHARE ROW EXCLUSIVE MODE'))
        # Freeze recipe evidence for the duration of the decision and verification.
        db.execute(sa.text('LOCK TABLE kitchen_recipes,kitchen_recipe_components IN SHARE MODE'))
        rows=[dict(r) for r in db.execute(sa.select(items).where(items.c.section=='COMPONENT').order_by(items.c.id)).mappings()]
        references=defaultdict(list)
        for rid,ingredient,preparation in db.execute(sa.text('SELECT recipe_id,ingredient_reference,preparation_reference FROM kitchen_recipe_components')):
            for value in (ingredient,preparation):
                if key(value):references[key(value)].append(rid)
        # Original E/F cells also retain evidence from any non-food/work rows excluded from typed ingredients.
        for rid,payload in db.execute(sa.text('SELECT id,source_payload FROM kitchen_recipes')):
            if isinstance(payload,dict):
                for source_row in payload.get('rows',{}).values():
                    for address,cell in source_row.items():
                        if re.fullmatch(r'[EF]\d+',address):
                            for value in (cell.get('original'),cell.get('cached')):
                                if key(value):references[key(value)].append(rid)
        decisions=plan(rows,originals,references)
        before=protected(db)
        result=dict(before=len(rows),retained=sum(d['action']!='remove' for d in decisions),
            renamed=sum(d['action']=='rename' for d in decisions),removed=sum(d['action']=='remove' for d in decisions),
            retained_non_food=[d for d in decisions if not d['original'].startswith('F-') and d['action']!='remove'],
            decisions=decisions,persisted=args.persist)
        OUT.mkdir(parents=True,exist_ok=True)
        if args.persist:
            referenced=db.execute(sa.text("SELECT conrelid::regclass::text FROM pg_constraint WHERE contype='f' AND confrelid='kitchen_configuration_items'::regclass")).scalars().all()
            if referenced:
                raise RuntimeError(f'Configuration items now have external references: {referenced}; no deletion applied')
            backup_name='components-before-cleanup-'+hashlib.sha256(json.dumps(rows,default=str,sort_keys=True).encode()).hexdigest()[:12]+'.json'
            backup=OUT/backup_name
            if not backup.exists():
                backup.write_text(json.dumps(dict(purpose='Restore Components configuration before PO-approved prefix/filter cleanup',
                    table='kitchen_configuration_items',section='COMPONENT',rows=rows),default=str,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            result['backup']=str(backup)
            for d in decisions:
                if d['action']=='remove':
                    db.execute(items.delete().where(items.c.id==d['id'],items.c.section=='COMPONENT'))
                elif d['action']=='rename':
                    db.execute(items.update().where(items.c.id==d['id'],items.c.section=='COMPONENT')
                               .values(name=d['name'],normalized_name=key(d['name']),updated_at=sa.func.now()))
            assert protected(db)==before,'Protected recipe or other list data changed; transaction rolled back'
        result['protected_tables']=before
    if args.persist:
        with engine.connect() as db:
            after=[dict(r) for r in db.execute(sa.select(items).where(items.c.section=='COMPONENT')).mappings()]
            expected={d['id']:d['name'] for d in decisions if d['action']!='remove'}
            assert {r['id']:r['name'] for r in after}==expected
            assert protected(db)==before
            result['verified_after_commit']=True
    engine.dispose()
    (OUT/('components-cleanup-committed.json' if args.persist else 'components-cleanup-preview.json')).write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('decisions','protected_tables')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
