"""Manual labour/elapsed times, separation from composition and forbidden work pseudo-items."""
from uuid import uuid4
from decimal import Decimal
import json
from test_kitchen_recipe_editor import build_app
import sqlalchemy as sa
from rfone_data_store.kitchen import recipes
from rfone_data_store.kitchen_configuration import items


def main():
 app,engine=build_app();client=app.test_client();base='/kitchen/recipes'
 def create(**values):return client.post(base+'/save',data=dict(csrf_token='test-csrf',name='Recipe with times',kind='dish',draft_key=str(uuid4()),**values))
 response=create(actual_work_minutes='15',elapsed_preparation_minutes='60')
 assert response.status_code==200,response.text
 rid=response.json['recipe']['id']
 def current():return client.get(f'{base}/{rid}/data').json['recipe']
 def edit(**values):return client.post(base+'/save',data=dict(csrf_token='test-csrf',id=rid,name='Recipe with times',revision=current()['revision'],**values))
 r=current();assert Decimal(r['actual_work_minutes'])==15 and Decimal(r['elapsed_preparation_minutes'])==60
 assert edit(actual_work_minutes='60',elapsed_preparation_minutes='30').status_code==200
 assert edit().status_code==200
 assert Decimal(current()['actual_work_minutes'])==60 and Decimal(current()['elapsed_preparation_minutes'])==30
 for field,value in [('actual_work_minutes','-1'),('elapsed_preparation_minutes','-1'),('elapsed_preparation_minutes','NaN'),('actual_work_minutes','1.12345')]:
  assert edit(**{field:value}).status_code==400
 with engine.begin() as db:db.execute(recipes.update().where(recipes.c.id==rid).values(total_cost=100,kcal=500))
 assert edit(elapsed_preparation_minutes='40').status_code==200
 with engine.connect() as db:assert db.scalar(sa.select(recipes.c.total_cost).where(recipes.c.id==rid))==100
 assert edit(actual_work_minutes='20').status_code==200
 with engine.connect() as db:
  r=db.execute(sa.select(recipes).where(recipes.c.id==rid)).mappings().one()
  assert r['total_cost'] is None and r['kcal']==500
 payload=dict(revision=current()['revision'],rows=[])
 assert client.post(f'{base}/{rid}/composition',data=dict(csrf_token='test-csrf',payload=json.dumps(payload))).status_code==200
 assert Decimal(current()['actual_work_minutes'])==20 and Decimal(current()['elapsed_preparation_minutes'])==40
 payload.update(revision=current()['revision'],work_minutes='200')
 assert client.post(f'{base}/{rid}/composition',data=dict(csrf_token='test-csrf',payload=json.dumps(payload))).status_code==400
 with engine.begin() as db:
  wid=db.execute(recipes.insert().values(code='Pr000',name='Actual Work Time (min)',kind='preparation').returning(recipes.c.id)).scalar_one()
  cid=db.execute(items.insert().values(section='COMPONENT',name='Actual Work Time (min)',normalized_name='actual work time (min)').returning(items.c.id)).scalar_one()
 choices=client.get(base+'/options').json
 assert all(p['id']!=wid for p in choices['preparations']) and all(c['id']!=cid for c in choices['components'])
 page=client.get(base).text
 assert 'data-recipe-id="'+str(wid)+'"' not in page and 'id="composition-work"' not in page
 assert 'name="actual_work_minutes"' in page and 'name="elapsed_preparation_minutes"' in page
 for line in [dict(component='id:'+str(cid),grams='1'),dict(preparation='id:'+str(wid),grams='1')]:
  payload=dict(revision=current()['revision'],rows=[line])
  assert client.post(f'{base}/{rid}/composition',data=dict(csrf_token='test-csrf',payload=json.dumps(payload))).status_code==400
 assert edit(actual_work_minutes='0',elapsed_preparation_minutes='0').status_code==200
 assert Decimal(current()['actual_work_minutes'])==0
 assert edit(actual_work_minutes='',elapsed_preparation_minutes='').status_code==200
 assert current()['actual_work_minutes']=='' and current()['elapsed_preparation_minutes']==''
 engine.dispose()
 print('PASS: manual time fields, round-trip, zero/unknown/invalid, person-minutes vs elapsed, cost invalidation without nutrient changes, composition preservation, pseudo-item hiding and rejection')


if __name__=='__main__':main()
