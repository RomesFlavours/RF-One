from pathlib import Path
root=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation/AWS-20261110T214612Z');web=root/'development-source/RF-One Web';p=web/'templates/compensation_run_detail.html';s=p.read_text(encoding='utf-8')
a=s.index('  #period-hours .compensation-check-row');b=s.index('</style>',a)
s=s[:a]+'''  #period-hours button.compensation-incomplete { border: 1px solid #ecd6a5; margin: 0; line-height: inherit; }
  #period-hours button.compensation-incomplete:hover { background: #f9e8c8; color: #8a5a10; }
  #period-hours button.compensation-incomplete:focus-visible { outline: 2px solid var(--olive-700); outline-offset: 3px; }
  #compensation-check-dialog .org-modal-panel { max-width: 42rem; }
  #compensation-check-dialog li { margin: .5rem 0; line-height: 1.55; }
'''+s[b:]
for field,complete in [('hours_status','HOURS_COMPLETE'),('data_status','DATA_COMPLETE')]:
 old='''<td><span class="badge {{ 'ok' if p.'''+field+''' == '''+complete+''' else 'warn' }}">{{ 'COMPLETE' if p.'''+field+''' == '''+complete+''' else 'INCOMPLETE' }}</span></td>'''
 new='''<td>{% if p.'''+field+''' == '''+complete+''' %}<span class="badge ok">COMPLETE</span>{% else %}<button type="button" class="badge warn compensation-incomplete" data-compensation-check="{{ p.employee_id }}" data-person-name="{{ p.display_name or ('Employee ' ~ p.employee_id) }}" aria-haspopup="dialog" aria-controls="compensation-check-dialog" aria-label="Show incomplete details for {{ p.display_name or ('Employee ' ~ p.employee_id) }}">INCOMPLETE</button>{% endif %}</td>'''
 assert old in s;s=s.replace(old,new,1)
a=s.index('            {% if p.hours_reasons or p.data_reasons %}');b=s.index('          {% endfor %}',a)
s=s[:a]+s[b:]
marker='{% for row in employee_rows %}'
modal='''<div class="org-modal-overlay" id="compensation-check-dialog" hidden aria-hidden="true">
  <section class="org-modal-panel" role="dialog" aria-modal="true" aria-labelledby="compensation-check-title">
    <div class="modal-header"><h2 id="compensation-check-title">Items to check</h2><button type="button" class="link-button" data-modal-close aria-label="Close">✕</button></div>
    <div id="compensation-check-content"></div>
    <div class="btn-row"><button type="button" data-modal-close>Close</button></div>
  </section>
</div>
{% for p in run_hours.rows %}
  <template id="compensation-check-{{ p.employee_id }}">
    {% if p.hours_reasons %}<h3>Hours</h3><ul>{% for reason in p.hours_reasons %}<li>{{ reason }}</li>{% endfor %}</ul>{% endif %}
    {% if p.data_reasons %}<h3>Compensation data</h3><ul>{% for reason in p.data_reasons %}<li>{{ reason }}</li>{% endfor %}</ul>{% endif %}
    {% if not p.hours_reasons and not p.data_reasons %}<p>Review the incomplete hours or compensation data for this person.</p>{% endif %}
  </template>
{% endfor %}
<script defer src="{{ url_for('static',filename='js/compensation-checks.js') }}?v=1"></script>

'''
assert marker in s;s=s.replace(marker,modal+marker,1);p.write_text(s,encoding='utf-8',newline='\n')
(web/'static/js/compensation-checks.js').write_text('''/* RF1 Compensation: per-person incomplete details, using the shared modal. */
(function () {
  "use strict";
  var overlay = document.getElementById("compensation-check-dialog");
  if (!overlay) return;
  var modal = RFOneModal.create({ overlay: overlay });
  var title = document.getElementById("compensation-check-title");
  var content = document.getElementById("compensation-check-content");
  document.querySelectorAll("[data-compensation-check]").forEach(function (button) {
    button.addEventListener("click", function () {
      var template = document.getElementById("compensation-check-" + button.dataset.compensationCheck);
      if (!template) return;
      title.textContent = button.dataset.personName + " · Items to check";
      content.replaceChildren(template.content.cloneNode(true));
      modal.open(button);
    });
  });
})();
''',encoding='utf-8',newline='\n')
print('Local Compensation: incomplete badges open shared RF1 popup; inline warning rows removed.')
