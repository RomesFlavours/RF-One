"""Lossless, local-only Kitchen import. Dry-run unless --persist is explicit."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re

import openpyxl
import sqlalchemy as sa
from sqlalchemy.engine import URL
from rfone_data_store.kitchen import recipes, components, steps


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def json_value(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def extract(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    formulas = openpyxl.load_workbook(path, data_only=False)
    values = openpyxl.load_workbook(path, data_only=True)
    s, v = formulas['DB-Recipes'], values['DB-Recipes']
    max_row, max_column = s.max_row, s.max_column
    headers = [r for r in range(2, max_row + 1) if s.cell(r, 2).value == 'A']
    codes = Counter(str(v.cell(r, 3).value).casefold() for r in headers if v.cell(r, 3).value)
    links = [link.file_link.Target for link in formulas._external_links if link.file_link]
    records = []
    for index, row in enumerate(headers):
        end = headers[index + 1] if index + 1 < len(headers) else max_row + 1
        original = v.cell(row, 3).value
        code = str(original) if original is not None else f'SOURCE-ROW-{row}'
        issues = []
        if original is None:
            issues.append('Missing source recipe code; provisional source-row identifier')
        elif codes[code.casefold()] > 1:
            code = f'{code}~ROW{row}'
            issues.append('Duplicate source code; preserved as separate record with source-row suffix')

        def payload(r):
            return {s.cell(r, c).coordinate: {'original': json_value(s.cell(r, c).value),
                     'cached': json_value(v.cell(r, c).value), 'type': s.cell(r, c).data_type}
                    for c in range(1, max_column + 1) if s.cell(r, c).value is not None}

        name = v.cell(row, 4).value
        if not isinstance(name, str) or not name.strip():
            name = f'Unnamed recipe (Excel row {row})'
            issues.append('Missing source name; provisional label')
        record = dict(code=code, name=name,
            kind='preparation' if str(original).lower().startswith('pr') else 'dish',
            ingredient_weight_g=number(v.cell(row, 7).value),
            total_cost=number(v.cell(row, 9).value), cost_per_kg=number(v.cell(row, 10).value),
            nutrition_basis='Cached Excel recipe totals; not independently validated',
            source_file=str(path.resolve()), source_sha256=digest, source_sheet=s.title, source_row=row,
            validation_status='pending')
        for col, field in [(11,'kcal'),(12,'protein_g'),(13,'carbohydrate_g'),(14,'fat_g'),(15,'cholesterol_mg')]:
            record[field] = number(v.cell(row, col).value)
        lines, instructions, work = [], [], []
        for r in range(row + 1, end):
            ingredient, prep, quantity, note = [v.cell(r,c).value for c in [5,6,7,8]]
            if note is not None:
                instructions.append(dict(position=r-row,instruction=str(note),source_row=r))
            if isinstance(prep, str) and prep.lower().startswith('pr000-'):
                if number(quantity) is not None:
                    work.append(number(quantity))
                continue
            if ingredient is not None or prep is not None:
                line = dict(position=r-row, source_line_key=str(v.cell(r,1).value or s.cell(r,2).value),
                    ingredient_reference=str(ingredient) if ingredient is not None else None,
                    preparation_reference=str(prep) if prep is not None else None,
                    quantity=number(quantity), unit='g', notes=str(note) if note is not None else None,
                    cost=number(v.cell(r,9).value), cost_per_kg=number(v.cell(r,10).value),
                    source_row=r, source_payload=payload(r))
                for col, field in [(11,'kcal'),(12,'protein_g'),(13,'carbohydrate_g'),(14,'fat_g'),(15,'cholesterol_mg')]:
                    line[field] = number(v.cell(r,col).value)
                lines.append(line)
        record['actual_work_minutes'] = sum(work) if work else None
        record['source_payload'] = dict(original_code=original, issues=issues,
            external_links=links, rows={str(r):payload(r) for r in range(row,end)})
        records.append((record, lines, instructions))
    formulas.close()
    values.close()
    return records


def local_engine():
    config = Path(os.environ['LOCALAPPDATA']) / 'RF-One/AWS-Copy/20261025T130037Z/local-connection.json'
    d = json.loads(config.read_text())
    if d['host'] != '127.0.0.1' or d['port'] != 55436:
        raise RuntimeError('Only the canonical local PostgreSQL connection is allowed')
    return sa.create_engine(URL.create('postgresql+psycopg2',username=d['user'],password=d['password'],
                          host=d['host'],port=d['port'],database=d['database']))


def run_import(c, records, persist=False):
    existing = c.execute(sa.select(recipes.c.id,recipes.c.code,recipes.c.source_sha256,recipes.c.source_sheet,recipes.c.source_row)
                         ).mappings().all()
    by_source = {(r['source_sha256'],r['source_sheet'],r['source_row']):r['id'] for r in existing}
    by_code = {r['code'].casefold() for r in existing}
    new = [x for x in records if (x[0]['source_sha256'],x[0]['source_sheet'],x[0]['source_row']) not in by_source]
    conflicts = [x[0]['code'] for x in new if x[0]['code'].casefold() in by_code]
    if conflicts:
        raise RuntimeError(f'Existing recipe code conflicts; no overwrite: {conflicts}')
    summary = dict(source_recipes=len(records), new_recipes=len(new), skipped=len(records)-len(new),
        components=sum(len(x[1]) for x in new), steps=sum(len(x[2]) for x in new),
        dishes=sum(x[0]['kind']=='dish' for x in new), preparations=sum(x[0]['kind']=='preparation' for x in new),
        provisional_records=[dict(code=x[0]['code'],issues=x[0]['source_payload']['issues']) for x in new
                             if x[0]['source_payload']['issues']], persisted=persist)
    if not persist:
        return summary
    ids = dict(by_source)
    targets = defaultdict(list)
    for record, _, _ in records:
        key = (record['source_sha256'],record['source_sheet'],record['source_row'])
        if key not in ids:
            ids[key] = c.execute(recipes.insert().values(**record).returning(recipes.c.id)).scalar_one()
        original = record['source_payload']['original_code']
        if original is not None:
            targets[str(original).casefold()].append(ids[key])
    unresolved = []
    for record, lines, instructions in new:
        recipe_id = ids[(record['source_sha256'],record['source_sheet'],record['source_row'])]
        for line in lines:
            prep = line['preparation_reference']
            if prep:
                match = re.match(r'(?i)^(pr\d+|d\d+)(?:-|\s|$)',prep)
                choices = targets.get(match.group(1).casefold(),[]) if match else []
                if len(choices)==1 and choices[0] != recipe_id:
                    line['preparation_id'] = choices[0]
                else:
                    unresolved.append(dict(recipe=record['code'],reference=prep,row=line['source_row']))
            c.execute(components.insert().values(recipe_id=recipe_id,**line))
        for instruction in instructions:
            c.execute(steps.insert().values(recipe_id=recipe_id,**instruction))
    summary['unresolved_preparations'] = unresolved
    return summary


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--file',type=Path,default=Path('C:/Users/servi/Downloads/Cartel1.xlsx'))
    parser.add_argument('--persist',action='store_true')
    args = parser.parse_args()
    engine = local_engine()
    with engine.begin() as c:
        revision = c.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all()
        if revision not in (['e5e620261110'], ['e6f120261109'], ['e6f720261110']):
            raise RuntimeError(f'Shared Kitchen migration required: {revision}')
        records = extract(args.file)
        c.execute(sa.text('LOCK TABLE kitchen_recipes IN SHARE ROW EXCLUSIVE MODE'))
        result = run_import(c,records,args.persist)
    if args.persist:
        with engine.connect() as c:
            digest = records[0][0]['source_sha256']
            imported = c.execute(sa.select(recipes.c.id).where(recipes.c.source_sha256 == digest)).scalars().all()
            counts = dict(recipes=len(imported),
                components=c.scalar(sa.select(sa.func.count()).select_from(components).where(components.c.recipe_id.in_(imported))),
                steps=c.scalar(sa.select(sa.func.count()).select_from(steps).where(steps.c.recipe_id.in_(imported))))
            assert counts == dict(recipes=len(records),components=sum(len(x[1]) for x in records),steps=sum(len(x[2]) for x in records)), counts
            result['verified_after_commit'] = counts
    engine.dispose()
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
