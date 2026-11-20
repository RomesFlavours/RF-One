"""Explicit one-time Kitchen content publication inside the AWS VPC, never app startup."""
import importlib.util,json,os,sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
ROOT=Path('/app');sys.path.insert(0,str(ROOT/'RF-One Data Store'))
from rfone_data_store.kitchen_configuration import items,normalize,clean_name
from rfone_data_store.kitchen import recipes,components,steps,photos
from rfone_data_store.models import Restaurant,Supplier,SupplierAlias
from rfone_data_store.purchasing.repository import get_or_create_supplier,rename_supplier_canonical,add_supplier_alias


def typed(table,row):
    result={}
    for key,value in row.items():
        column=table.c[key]
        if value is not None and isinstance(column.type,sa.DateTime) and isinstance(value,str):value=datetime.fromisoformat(value)
        elif value is not None and isinstance(column.type,sa.Numeric):value=Decimal(str(value))
        result[key]=value
    return result


def main():
    seed=json.loads((ROOT/'release/kitchen-content.json').read_text())
    assert seed['scope']=='User-approved Kitchen content publication'
    engine=sa.create_engine(os.environ['RFONE_DATABASE_URL'])
    mpath=ROOT/'RF-One Data Store/migrations/versions/k9a020261110_publish_kitchen_aws.py'
    spec=importlib.util.spec_from_file_location('kitchen_aws_migration',mpath);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    result=dict(release=seed['release_id'],counts={},supplier_created=0,supplier_reused=0,pending_directory=[])
    with Session(engine) as db:
        with db.begin():
            db.execute(sa.text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
            revisions=db.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
            if revisions==[m.down_revision]:
                with Operations.context(MigrationContext.configure(db.connection())):m.upgrade()
                db.execute(sa.text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=m.revision,old=m.down_revision))
            elif revisions!=[m.revision]:raise RuntimeError('Unexpected production revision; no migration/content change applied: '+repr(revisions))
            for table in (items,recipes,components,steps,photos):
                expected=[typed(table,r) for r in seed['tables'][table.name]]
                current=[dict(r) for r in db.execute(sa.select(table).order_by(table.c.id)).mappings()]
                if current:
                    if len(current)!=len(expected):raise RuntimeError('Existing Kitchen content differs; refusing overwrite: '+table.name)
                    by_id={r['id']:r for r in current}
                    if any(row['id'] not in by_id or any(by_id[row['id']][key]!=value for key,value in row.items()) for row in expected):
                        raise RuntimeError('Existing Kitchen content changed; refusing overwrite: '+table.name)
                elif expected:db.execute(table.insert(),expected)
                maximum=max([r['id'] for r in expected]+[0])
                if maximum:db.execute(sa.text("SELECT setval(pg_get_serial_sequence(:table,'id'),:maximum,true)"),dict(table=table.name,maximum=maximum))
                result['counts'][table.name]=len(expected)
            restaurants={r.name:r.id for r in db.scalars(sa.select(Restaurant)).all()}
            for supplier in seed['suppliers']:
                rid=restaurants.get(supplier['restaurant_name'])
                if rid is None:
                    result['pending_directory'].append(dict(restaurant=supplier['restaurant_name'],supplier=supplier['name']));continue
                names={normalize(clean_name(n)) for n in [supplier['name'],*supplier.get('aliases',[])]}
                candidates=set()
                for sid,name in db.execute(sa.select(Supplier.id,Supplier.name).where(Supplier.restaurant_id==rid)):
                    if normalize(clean_name(name)) in names:candidates.add(sid)
                for sid,alias in db.execute(sa.select(SupplierAlias.supplier_id,SupplierAlias.alias_name).join(Supplier).where(Supplier.restaurant_id==rid)):
                    if normalize(clean_name(alias)) in names:candidates.add(sid)
                if len(candidates)>1:raise RuntimeError('Ambiguous existing supplier; refusing to create/merge: '+supplier['name'])
                if candidates:
                    sid=candidates.pop();result['supplier_reused']+=1
                    if supplier['name']=='To Verify':rename_supplier_canonical(db,sid,'To Verify',source='Kitchen English publication')
                else:
                    row=get_or_create_supplier(db,rid,supplier['name']);row.status=supplier['status'];sid=row.id;result['supplier_created']+=1
                for alias in supplier.get('aliases',[]):add_supplier_alias(db,sid,alias,source='Kitchen source publication')
    with engine.connect() as db:
        for table in (items,recipes,components,steps,photos):
            assert db.scalar(sa.select(sa.func.count()).select_from(table))==result['counts'][table.name]
        result['revision']=db.execute(sa.text('SELECT version_num FROM alembic_version')).scalar_one()
    engine.dispose();result['verified_after_commit']=True
    print('KITCHEN_PUBLISH='+json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
