from pathlib import Path
from sqlalchemy import create_engine,select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from datetime import datetime,timezone
from decimal import Decimal
import os,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'03 Software/RF-One Data Store'))
from rfone_data_store import models as m
from rfone_data_store.tips import distribution_engine as engine,distribution_rule_service as rules
p=Path(os.environ['LOCALAPPDATA'])/'RF-One/AWS-Copy/20261025T130037Z/local-connection.json';d=json.loads(p.read_text());assert d['port']==55436
u=URL.create('postgresql+psycopg2',username=d['user'],password=d['password'],host=d['host'],port=d['port'],database=d['database']);e=create_engine(u)
results=[]
with Session(e) as s:
 try:
  # Changes exist only inside this transaction and are always rolled back.
  for rule in rules.list_rules(s,1):rule.is_active=False
  role=lambda name:s.scalars(select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id==1,m.RestaurantRole.name==name)).one().id
  rules.create_rule(s,restaurant_id=1,source_role_id=role('Server'),recipient_role_id=role('Host'),
   calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY,rate=Decimal(10),effective_from=datetime(2026,1,1,9,tzinfo=timezone.utc),
   aggregation_scope=m.AGGREGATION_SCOPE_SOURCE_BUSINESS_DAY,eligibility_mode=m.ELIGIBILITY_MODE_WORKED_DURING_BUSINESS_DAY,
   distribution_method=m.DISTRIBUTION_METHOD_HOURS_PROPORTIONAL)
  version=rules.list_versions(s,3) if False else None
  for start,end in [('2026-10-21T08:00:00+00:00','2026-10-26T08:00:00+00:00'),('2026-01-01T09:00:00+00:00','2026-11-09T09:00:00+00:00')]:
   t=time.monotonic();r=engine.calculate_tips(s,restaurant_id=1,period_start=datetime.fromisoformat(start),period_end=datetime.fromisoformat(end))
   rows=engine.build_employee_review(s,r);totals=engine.build_operational_totals(r,rows)
   result=dict(start=start,end=end,orders=r.summary.orders_considered,gross_minor=r.voluntary_total_minor+r.gratuity_total_minor,
    distributed_minor=r.distributed_total_minor,blocked_reason=r.blocked_reason,entitlements_minor=totals.total_employee_entitlements_minor,
    reconciles=totals.total_employee_entitlements_minor==r.voluntary_total_minor+r.gratuity_total_minor,
    no_recipient_orders=len(r.no_eligible_recipient_lines),seconds=round(time.monotonic()-t,2))
   result['source_semantics']='ROLE: Server'
   results.append(result);print(json.dumps(result),flush=True)
   if start.startswith('2026-10'):
    v=s.scalars(select(m.TipDistributionRuleVersion).where(m.TipDistributionRuleVersion.aggregation_scope=='SOURCE_BUSINESS_DAY')).all()[-1]
    v.source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER;v.source_role_id=None;s.flush()
    compare=engine.calculate_tips(s,restaurant_id=1,period_start=datetime.fromisoformat(start),period_end=datetime.fromisoformat(end))
    comparison=dict(source_semantics='ORDER_SERVICE_OWNER',distributed_minor=compare.distributed_total_minor,no_recipient_orders=len(compare.no_eligible_recipient_lines),host_totals=[dict(name=row.display_name,amount_minor=row.inbound_tip_out_minor) for row in engine.build_employee_review(s,compare) if row.inbound_tip_out_minor]);results.append(comparison);print('OWNER COMPARISON',json.dumps(comparison),flush=True)
    v.source_role_id=3;v.source_semantics=m.TIP_SOURCE_SEMANTICS_ROLE;s.flush()
 finally:s.rollback()
e.dispose();(ROOT/'tmp/local_tips_preview.json').write_text(json.dumps(dict(rolled_back=True,results=results),indent=2))
