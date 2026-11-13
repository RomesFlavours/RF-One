from pathlib import Path
repo=Path('tmp/git-anagrafica-release');store=repo/'03 Software/RF-One Data Store';web=repo/'03 Software/RF-One Web'
p=store/'rfone_data_store/models.py';t=p.read_text(encoding='utf-8');start=t.index('class RFOneAccount(Base):');i=t.index('    email_verified_at:',start);t=t[:i]+'''    # Registry contact data for external accounts; separate from login recovery.
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
''' +t[i:];p.write_text(t,encoding='utf-8')
p=store/'migrations/versions/f3b120261110_registry_contacts.py';p.write_text('''"""Registry contact details for external RF1 accounts, not recovery channels."""
from alembic import op
import sqlalchemy as sa
revision='f3b120261110'
down_revision='f2a120261110'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('rfone_accounts',sa.Column('contact_email',sa.String(255),nullable=True))
    op.add_column('rfone_accounts',sa.Column('contact_phone',sa.String(64),nullable=True))

def downgrade():
    raise RuntimeError('Preserve Registry contacts; use the verified backup for recovery.')
''',encoding='utf-8')
p=store/'rfone_data_store/access_profiles.py';t=p.read_text(encoding='utf-8');t=t.replace('def save_person_profile(db,target,*,name,company_ids,assignments,actor=None):', '''_CONTACT_UNSET=object()

def _contact(value,limit,label):
    value=(value or '').strip()
    if len(value)>limit or any(ord(char)<32 for char in value):raise ValueError(f'Invalid {label}.')
    if value and label=='email':
        import re
        if not re.fullmatch(r'[^\\s@]+@[^\\s@]+\\.[^\\s@]+',value):raise ValueError('Enter a valid email address.')
    return value or None

def save_person_profile(db,target,*,name,company_ids,assignments,actor=None,email=_CONTACT_UNSET,phone=_CONTACT_UNSET):''')
t=t.replace("    name=_name(name)\n    company_ids=", "    name=_name(name)\n    if email is not _CONTACT_UNSET:email=_contact(email,255,'email')\n    if phone is not _CONTACT_UNSET:phone=_contact(phone,64,'phone')\n    company_ids=",1)
t=t.replace('directory.update_management(db,record,display_name=name,custom_id=record.custom_id,active=record.active,account_id=actor)', '''directory.update_management(db,record,display_name=name,custom_id=record.custom_id,active=record.active,account_id=actor,
            email=record.email if email is _CONTACT_UNSET else email,phone=record.phone if phone is _CONTACT_UNSET else phone)''')
t=t.replace("        before=record.display_name;record.display_name=name", """        contact_before={'email':record.contact_email,'phone':record.contact_phone}
        if email is not _CONTACT_UNSET:record.contact_email=email
        if phone is not _CONTACT_UNSET:record.contact_phone=phone
        if email is not _CONTACT_UNSET or phone is not _CONTACT_UNSET:event(db,'EXTERNAL_CONTACT_UPDATE',actor,account_id=account,before=contact_before,after={'email':record.contact_email,'phone':record.contact_phone})
        before=record.display_name;record.display_name=name""")
t=t.replace('def create_profile_person(db,*,name,company_ids,assignments,actor=None):','def create_profile_person(db,*,name,company_ids,assignments,actor=None,email=_CONTACT_UNSET,phone=_CONTACT_UNSET):').replace("save_person_profile(db,f'employee:{person.id}',name=name,company_ids=company_ids,assignments=assignments,actor=actor)","save_person_profile(db,f'employee:{person.id}',name=name,company_ids=company_ids,assignments=assignments,actor=actor,email=email,phone=phone)")
p.write_text(t,encoding='utf-8')
p=web/'role_profile_routes.py';t=p.read_text(encoding='utf-8');t=t.replace("if action=='person_access':", "if action in ('person_access','person_password'):");t=t.replace("return redirect(url_for('admin_account_access',account_id=linked.id,from_person=person))", "return redirect(url_for('admin_account_edit',account_id=linked.id,_anchor='reset-password')) if action=='person_password' else redirect(url_for('admin_account_access',account_id=linked.id,from_person=person))")
t=t.replace("assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id)","assignments=json.loads(request.form.get('person_roles','[]')),actor=account.id,**{key:request.form[key] for key in ('email','phone') if key in request.form})")
t=t.replace("{'key':key,'access_url':access_url,'name':target.display_name", "{'key':key,'email':target.email if kind=='employee' else target.contact_email,'phone':target.phone if kind=='employee' else target.contact_phone,'access_url':access_url,'name':target.display_name")
p.write_text(t,encoding='utf-8')
p=web/'templates/home.html';t=p.read_text(encoding='utf-8');t='\n'.join(line for line in t.split('\n') if not ('home-row' in line and '<strong>Accounts</strong>' in line));p.write_text(t,encoding='utf-8')
p=web/'templates/role_profiles.html';t=p.read_text(encoding='utf-8').replace('<fieldset><legend>Company · select one or more</legend>', '''<div class="person-contact-fields"><label>Email <input type="email" name="email" maxlength="255" autocomplete="off"></label><label>Phone <input type="tel" name="phone" maxlength="64" autocomplete="off"></label></div>
<fieldset><legend>Company · select one or more</legend>''',1);t=t.replace('<p id="person-authorizations-help"', '<button type="submit" id="person-reset-password" form="person-password-form" hidden>Reset password</button><p id="person-authorizations-help"',1);t=t.replace('<form id="person-access-form"', '<form id="person-password-form" method="post" target="_blank" rel="noopener">{{ hidden(\'person_password\') }}</form>\n<form id="person-access-form"',1).replace('?v=8','?v=contacts1');p.write_text(t,encoding='utf-8')
p=web/'static/js/role-profiles.js';t=p.read_text(encoding='utf-8').replace('    link.hidden=!person;',"    link.hidden=!person;document.getElementById('person-reset-password').hidden=!person;field(document.getElementById('person-password-form'),'person',person?person.key:'');").replace("field(editor,'name',p.name);field(editor,'tab'", "field(editor,'name',p.name);field(editor,'email',p.email||'');field(editor,'phone',p.phone||'');field(editor,'tab'");p.write_text(t,encoding='utf-8')
p=web/'static/css/role-profiles.css';p.write_text(p.read_text(encoding='utf-8')+'\n.person-contact-fields{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem}.person-extra>button{margin-right:.6rem}#person-reset-password[hidden]{display:none}@media(max-width:700px){.person-contact-fields{grid-template-columns:1fr}}\n',encoding='utf-8')
# Recalculate only the tracked guard hashes, including models and service changes.
import json,hashlib
manifest_path=store/'clover_connector_release.json';manifest=json.loads(manifest_path.read_text());manifest['release']='rfone-registry-contacts-20261110'
for file in (store/'rfone_data_store/models.py',store/'rfone_data_store/access_profiles.py',store/'migrations/versions/f3b120261110_registry_contacts.py'):manifest['files'][file.relative_to(repo/'03 Software').as_posix()]=''
for name in manifest['files']:
 file=repo/'03 Software'/name;payload=file.read_bytes().replace(b'\r\n',b'\n');file.write_bytes(payload);manifest['files'][name]=hashlib.sha256(payload).hexdigest()
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Registry contacts and reset-password entry implemented; Accounts removed from MyRF')
