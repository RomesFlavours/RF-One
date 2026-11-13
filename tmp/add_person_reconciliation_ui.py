from pathlib import Path
root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web')
(root/'person_reconciliation_routes.py').write_text('''"""Administrator-only, explicit identity reconciliation; no GET writes."""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from rfone_data_store import models as m, person_reconciliation as identities


def register_person_reconciliation(app, *, SessionFactory, require_admin, load_current_account, require_csrf):
    @app.route('/admin/registry/identity-reconciliation',methods=['GET','POST'])
    @require_admin
    def registry_identity_reconciliation():
        status=200
        with SessionFactory() as db:
            actor=load_current_account(db)
            if request.method=='POST':
                require_csrf()
                try:
                    action=request.form.get('action')
                    if action not in ('link','create'):abort(400)
                    person=identities.reconcile(db,actor,key=request.form.get('key',''),
                        fingerprint=request.form.get('fingerprint',''),
                        person_id=int(request.form['person_id']) if action=='link' else None,
                        new_name=request.form.get('new_name','') if action=='create' else None)
                    db.commit()
                except (ValueError,KeyError) as exc:
                    db.rollback();flash(str(exc),'error');status=400
                else:
                    flash('Identity links confirmed. Accounts, permissions and learning history were preserved.','info')
                    return redirect(url_for('registry_identity_reconciliation',person_id=person.id))
            report=identities.audit(db)
            persons=list(db.scalars(select(m.CandidatePerson).order_by(m.CandidatePerson.full_name,m.CandidatePerson.id)))
            return render_template('registry_identity_reconciliation.html',report=report,persons=persons),status
''',encoding='utf-8',newline='\n')
(root/'templates/registry_identity_reconciliation.html').write_text('''{% extends 'base.html' %}
{% from '_nav_macros.html' import breadcrumb %}
{% block page_title %}Identity reconciliation · Registry{% endblock %}
{% block content %}
{{ breadcrumb([('RF-One',url_for('home')),('Registry',url_for('role_profiles_home',tab='people')),('Identity reconciliation',none)]) }}
<h1>Identity reconciliation</h1>
<p>One person across Registry, RF1 accounts and Training. Names and email are suggestions only: links require explicit confirmation.</p>
<p><a href="{{ url_for('role_profiles_home',tab='people') }}">Back to Registry</a></p>
{% if not report.ready %}<p role="alert">Identity linking requires the explicit local schema setup. This page does not create tables or change records.</p>{% endif %}
<div class="card"><strong>{{ report.counts.confirmed }} linked groups</strong> · {{ report.counts.unlinked }} without a central person · {{ report.counts.conflict }} conflicts</div>
{% for group in report.groups %}
<details class="card" {% if group.state=='conflict' %}open{% endif %} data-identity-group="{{ group.key }}">
<summary><strong>{{ group.name }}</strong> · {{ group.state }}{% if group.person_ids %} · Person #{{ group.person_ids|join(', ') }}{% endif %}</summary>
<table><thead><tr><th>Record</th><th>Name</th><th>Status</th></tr></thead><tbody>
{% for record in group.records if record.kind!='acting' %}<tr><td>{{ record.kind }} #{{ record.id }}</td><td>{{ record.name }}</td><td>{{ record.status or ('Dismissed' if record.active is sameas false else '—') }}</td></tr>{% endfor %}
</tbody></table>
{% for conflict in group.conflicts %}<p role="alert">{{ conflict }}</p>{% endfor %}
{% if group.suggestions %}<p>Possible matches (not linked): {% for suggestion in group.suggestions %}{{ suggestion.name }} (#{{ suggestion.id }}, {{ suggestion.reason }}){% if not loop.last %}; {% endif %}{% endfor %}</p>{% endif %}
{% if report.ready and not group.conflicts %}
<form method="post">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="key" value="{{ group.key }}"><input type="hidden" name="fingerprint" value="{{ group.fingerprint }}">
<label>Confirmed person <select name="person_id"><option value="">Select a person after reviewing the records</option>{% for person in persons %}<option value="{{ person.id }}" {% if person.id in group.person_ids %}selected{% endif %}>{{ person.full_name }} · #{{ person.id }}</option>{% endfor %}</select></label>
<button name="action" value="link">Confirm links to this person</button>
{% if not group.person_ids %}<label>Or explicitly create a central person <input name="new_name" value="{{ group.name }}" maxlength="255" autocomplete="off"></label><button name="action" value="create">Create person and confirm links</button>{% endif %}
</form>
{% else %}<p>Conflicts are retained for review. No automatic merge, deletion or reassignment is available.</p>{% endif %}
</details>
{% endfor %}
{% endblock %}
''',encoding='utf-8',newline='\n')
p=root/'role_profile_routes.py';s=p.read_text(encoding='utf-8');needle='    install_access_context(app, SessionFactory, load_current_account)';assert needle in s;s=s.replace(needle,needle+'''\n    from person_reconciliation_routes import register_person_reconciliation
    register_person_reconciliation(app, SessionFactory=SessionFactory, require_admin=require_admin,
        load_current_account=load_current_account, require_csrf=require_csrf)''',1);p.write_text(s,encoding='utf-8',newline='\n')
p=root/'templates/role_profiles.html';s=p.read_text(encoding='utf-8').replace('<h1>Registry</h1>','<h1>Registry</h1>\n<p><a href="{{ url_for(\'registry_identity_reconciliation\') }}">Identity reconciliation</a></p>',1);p.write_text(s,encoding='utf-8',newline='\n')
