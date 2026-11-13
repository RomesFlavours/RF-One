"""Real workbook import reconciliation in disposable memory, never local production."""
from pathlib import Path
import sqlalchemy as sa
from rfone_data_store.kitchen import KITCHEN_TABLES, menu_cards
from import_kitchen_excel import extract, run_import


def main():
    records = extract(Path('C:/Users/servi/Downloads/Cartel1.xlsx'))
    assert len(records) == 255
    assert sum(len(r[0]['source_payload']['rows']) for r in records) == 4080
    assert len({r[0]['code'].casefold() for r in records}) == len(records)
    metadata = sa.MetaData()
    sa.Table('restaurants',metadata,sa.Column('id',sa.Integer,primary_key=True))
    sa.Table('acting_identities',metadata,sa.Column('id',sa.Integer,primary_key=True))
    menu_cards.to_metadata(metadata)
    for t in KITCHEN_TABLES:
        t.to_metadata(metadata)
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.exec_driver_sql('PRAGMA foreign_keys=ON')
        metadata.create_all(c)
        result = run_import(c,records,persist=True)
        assert result['new_recipes'] == 255
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipes')) == 255
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipe_components')) == result['components']
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipe_steps')) == 246
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipes WHERE dietary_class IS NOT NULL')) == 0
        assert c.scalar(sa.text("SELECT count(*) FROM kitchen_recipe_components WHERE preparation_reference LIKE 'Pr000-%'")) == 0
        assert c.scalar(sa.text("SELECT count(*) FROM kitchen_recipes WHERE code LIKE 'D053~ROW%'")) == 2
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipes WHERE source_row=418')) == 1
        second = run_import(c,records,persist=True)
        assert second['new_recipes'] == 0 and second['skipped'] == 255
        assert c.scalar(sa.text('SELECT count(*) FROM kitchen_recipe_components')) == result['components']
    engine.dispose()
    print('PASS: 255 shared recipes, 4080 source rows, all components/246 notes, separate work minutes, unknown properties, duplicate preservation, repeat import skips all')
    print('Unresolved preparation references:',len(result['unresolved_preparations']))


if __name__ == '__main__':
    main()
