from pathlib import Path
import json
root=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation/AWS-20261110T214612Z')
p=root/'development-source/RF-One Web/templates/compensation_run_detail.html';s=p.read_text(encoding='utf-8')
s=s.replace('<th>Compensation data</th><th>Missing / to check</th>','<th>Compensation data</th>')
old='''              <td class="muted">
                {% for reason in p.hours_reasons %}<div>Hours: {{ reason }}</div>{% endfor %}
                {% for reason in p.data_reasons %}<div>{{ reason }}</div>{% endfor %}
              </td>
            </tr>'''
new='''            </tr>
            {% if p.hours_reasons or p.data_reasons %}
              <tr class="compensation-check-row">
                <td colspan="9" class="muted" aria-describedby="hours-{{ p.employee_id }}">
                  {% for reason in p.hours_reasons %}<span class="compensation-check-message">Hours: {{ reason }}</span>{% endfor %}
                  {% for reason in p.data_reasons %}<span class="compensation-check-message">{{ reason }}</span>{% endfor %}
                </td>
              </tr>
            {% endif %}'''
assert old in s;s=s.replace(old,new,1)
s=s.replace('{% block content %}', '''{% block head_extra %}
{{ super() }}
<style>
  #period-hours .compensation-check-row td { padding: .15rem .5rem .7rem; line-height: 1.5; }
  #period-hours .compensation-check-message + .compensation-check-message::before { content: " · "; }
</style>
{% endblock %}
{% block content %}''',1)
p.write_text(s,encoding='utf-8',newline='\n')
state_path=root/'verification.json';state=json.loads(state_path.read_text(encoding='utf-8'));state.setdefault('local_changes',[]).append({'file':'RF-One Web/templates/compensation_run_detail.html','change':'Remove Missing / to check column; retain all reasons in a full-width row below each employee.'});state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
print('Local Compensation template updated; original AWS source preserved.')
