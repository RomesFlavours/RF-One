"""Populate Kitchen configuration from explicit BasicData list columns, local only."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor

import openpyxl
import sqlalchemy as sa
from sqlalchemy.orm import Session
from import_kitchen_excel import local_engine
from rfone_data_store import kitchen_configuration as config
from rfone_data_store.models import Restaurant, Supplier, SupplierAlias

SOURCE_COLUMNS = {'MENU_TYPE':(8,'Menu Tipo'), 'MENU_AREA':(7,'Menu Area'),
                  'CATEGORY':(9,'Category'), 'COMPONENT':(1,'Food'), 'SUPPLIER':(5,'Supplier')}


def extract(path):
    result={key:{} for key in SOURCE_COLUMNS}
    book=openpyxl.load_workbook(path,data_only=False)
    try:
        sheet=book['BasicData']
        for section,(column,header) in SOURCE_COLUMNS.items():
            if sheet.cell(1,column).value != header:
                raise ValueError(f'Unexpected source header for {section}')
            for row in range(3,sheet.max_row+1):
                cell=sheet.cell(row,column)
                if cell.value is None or isinstance(cell.value,str) and not cell.value.strip():
                    continue
                if not isinstance(cell.value,str) or cell.data_type in ('f','e'):
                    raise ValueError(f'List name must be explicit text: {cell.coordinate}')
                name=config.clean_name(cell.value)
                key=config.normalize(name)
                entry=result[section].setdefault(key,dict(name=name,cells=[]))
                entry['cells'].append(dict(cell=cell.coordinate,original=cell.value))
    finally:
        book.close()
    return result


def import_lists(db, extracted, *, restaurant_ids=(), persist=False):
    existing={}
    for row in db.execute(sa.select(config.items)).mappings():
        existing[(row['section'],row['normalized_name'])]=dict(row)
    suppliers=defaultdict(set)
    for sid,rid,name in db.execute(sa.select(Supplier.id,Supplier.restaurant_id,Supplier.name)):
        suppliers[(rid,config.normalize(config.clean_name(name)))].add(sid)
    for sid,rid,name in db.execute(sa.select(SupplierAlias.supplier_id,Supplier.restaurant_id,SupplierAlias.alias_name).join(Supplier)):
        suppliers[(rid,config.normalize(config.clean_name(name)))].add(sid)
    report={}
    mappings=[]
    for section,entries in extracted.items():
        added=skipped=0
        scopes=restaurant_ids if section=='SUPPLIER' else [None]
        for rid in scopes:
            for normalized,entry in entries.items():
                if section=='SUPPLIER':
                    matches=suppliers.get((rid,normalized),set())
                    if len(matches)>1:
                        raise ValueError(f'Ambiguous existing supplier: {entry["name"]}')
                    identifier=next(iter(matches),None)
                else:
                    current=existing.get((section,normalized))
                    identifier=current['id'] if current else None
                if identifier is None:
                    added+=1
                    if persist:
                        identifier=config.save(db,section,name=entry['name'],restaurant_id=rid)
                else:
                    skipped+=1
                mappings.append(dict(section=section,restaurant_id=rid,id=identifier,**entry))
        report[section]=dict(source_unique=len(entries),source_cells=sum(len(e['cells']) for e in entries.values()),
                             added=added,existing=skipped,pending=section=='SUPPLIER' and not restaurant_ids)
    return dict(sections=report,mappings=mappings)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--file',type=Path,default=Path('C:/Users/servi/Downloads/Cartel1.xlsx'))
    parser.add_argument('--supplier-restaurants',choices=['both','winter-park','mount-dora'])
    parser.add_argument('--persist',action='store_true')
    parser.add_argument('--verify-page',action='store_true')
    args=parser.parse_args()
    digest=hashlib.sha256(args.file.read_bytes()).hexdigest()
    extracted=extract(args.file)
    engine=local_engine()
    names={'winter-park':"Rome's Flavours - WP",'mount-dora':"Rome's Flavours - MD"}
    with Session(engine) as db:
        with db.begin():
            # Only local configuration/supplier records can change in this import.
            db.execute(sa.text('LOCK TABLE kitchen_configuration_items IN SHARE ROW EXCLUSIVE MODE'))
            before={table:db.scalar(sa.text(f'SELECT count(*) FROM {table}')) for table in
                    ('kitchen_recipes','kitchen_recipe_components','kitchen_recipe_steps','restaurant_menu_cards')}
            ids=[]
            if args.supplier_restaurants:
                requested=list(names.values()) if args.supplier_restaurants=='both' else [names[args.supplier_restaurants]]
                for name in requested:
                    matches=db.scalars(sa.select(Restaurant.id).where(Restaurant.name==name)).all()
                    if len(matches)!=1:
                        raise ValueError(f'Restaurant missing or ambiguous: {name}')
                    ids.append(matches[0])
            result=import_lists(db,extracted,restaurant_ids=ids,persist=args.persist)
            assert hashlib.sha256(args.file.read_bytes()).hexdigest()==digest, 'Source changed during import'
            after={table:db.scalar(sa.text(f'SELECT count(*) FROM {table}')) for table in before}
            assert before==after
        if args.persist:
            verification=import_lists(db,extracted,restaurant_ids=ids,persist=False)
            assert all(section['added']==0 for section in verification['sections'].values())
            result['verified_after_commit']=True
    engine.dispose()
    if args.verify_page:
        class PageCounts(HTMLParser):
            def __init__(self):
                super().__init__();self.counts={key:0 for key in SOURCE_COLUMNS};self.section=None
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='details' and attrs.get('data-config-section') in self.counts:
                    self.section=attrs['data-config-section']
                if tag=='tr' and self.section and attrs.get('data-rr-key','').startswith('config-'):
                    self.counts[self.section]+=1
            def handle_endtag(self,tag):
                if tag=='details':self.section=None
        opener=build_opener(HTTPCookieProcessor(CookieJar()))
        response=opener.open('http://127.0.0.1:5097/kitchen/configuration',timeout=20)
        page=PageCounts();page.feed(response.read().decode('utf-8'))
        for section,entries in extracted.items():
            expected=len(entries)*(len(ids) if section=='SUPPLIER' else 1)
            assert page.counts[section]>=expected, (section,page.counts[section],expected)
        result['verified_live_page_counts']=page.counts
    result.update(source_file=str(args.file.resolve()),source_sha256=digest,source_sheet='BasicData',
                  persisted=args.persist,protected_counts=after)
    output=Path(__file__).resolve().parents[2]/'output/kitchen-configuration'
    output.mkdir(parents=True,exist_ok=True)
    filename='excel-import-'+(args.supplier_restaurants or 'suppliers-pending')+('-committed' if args.persist else '-preview')+'.json'
    (output/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='mappings'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
