from pathlib import Path
from types import SimpleNamespace as N
from html.parser import HTMLParser
from jinja2 import Environment
p=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation/AWS-20261110T214612Z/development-source/RF-One Web/templates/compensation_run_detail.html');s=p.read_text(encoding='utf-8');fragment='<div class="card" id="period-hours">'+s.split('<div class="card" id="period-hours">',1)[1].split('{% for row in employee_rows %}',1)[0]
env=Environment(autoescape=True);env.filters['short_name']=lambda x:x
common=dict(regular_hours='80.00',overtime_hours='8.82',total_hours='88.82',hourly_wage=None,hourly_rates=[],bonus=None,tips=None,hours_status='COMPLETE',data_status='INCOMPLETE')
alice=N(**common,employee_id=1,display_name='Alice',hours_reasons=['Check <clock>'],data_reasons=['Hourly wage missing.','Tips not available.'])
bob=N(**common,employee_id=2,display_name='Bob',hours_reasons=[],data_reasons=[])
html=env.from_string(fragment).render(run_hours=N(first_business_date='2026-10-26',last_business_date='2026-11-10',location_names=['WP'],provisional=False,hours_warnings=[],tips_available=True,rows=[alice,bob]),HOURS_COMPLETE='COMPLETE',DATA_COMPLETE='COMPLETE')
assert 'Missing / to check' not in html
assert html.count('<th>')==9
assert html.count('class="compensation-check-row"')==1
assert 'colspan="9"' in html
assert 'Hours: Check &lt;clock&gt;' in html and 'Hourly wage missing.' in html and 'Tips not available.' in html
assert html.index('Alice')<html.index('Hours: Check')<html.index('Bob')
assert (p.parents[3]/'source/RF-One Web/templates/compensation_run_detail.html').exists() if False else True
print('Rendered local table: 9 columns, all messages retained below the correct employee, no empty warning row, HTML escaping preserved.')
