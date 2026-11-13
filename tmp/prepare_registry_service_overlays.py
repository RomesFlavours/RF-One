from pathlib import Path
import ast,shutil,json,hashlib,difflib
ROOT=Path.cwd();out=ROOT/'tmp/registry-access-release';canonical=ROOT/'tmp/git-anagrafica-release/03 Software'
sourceinfo=json.loads((out/'sources.json').read_text());manifest={}
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def transform(p,old,new):
 s=p.read_text(encoding='utf-8');assert old in s,(p,old[:80]);write(p,s.replace(old,new))
def copy(file,base):dst=base/file;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(canonical/file,dst)
cs=(canonical/'RF-One Data Store/rfone_data_store/models.py').read_text(encoding='utf-8');cc={n.name:n for n in ast.parse(cs).body if isinstance(n,ast.ClassDef)}
for service in ('web','tips','selection','training','kitchen'):
 root=out/(service+'-source');base=root/'03 Software' if (root/'03 Software').exists() else root
 before={str(p.relative_to(root)).replace('\\','/'):p.read_bytes() for p in root.rglob('*') if p.is_file()}
 if service=='web':
  files=['RF-One Web/'+n for n in ('role_profile_routes.py','training_integration.py','static/js/role-profiles.js','templates/admin_account_access.html','templates/home.html')]
  files+=['RF-One Data Store/rfone_data_store/dev_journal/service.py','Training/auth.py']
  for file in files:copy(file,base)
 for file in ('access_profiles.py','web_access.py','rfone_account_service.py','rfone_web_session.py','employee_directory.py'):
  copy('RF-One Data Store/rfone_data_store/'+file,base)
 # Register the already-deployed Registry schema in older service model trees,
 # preserving every service-owned model and all newer business fields.
 p=base/'RF-One Data Store/rfone_data_store/models.py';s=p.read_text(encoding='utf-8');tree=ast.parse(s);existing={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)};lines=s.splitlines(True);inserts=[]
 for name in ('Employee','RFOneAccount','RFOneAccountDomainAccess'):
  current=existing[name];fields={n.target.id for n in current.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name)}
  additions=[ast.get_source_segment(cs,n) for n in cc[name].body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id not in fields]
  if additions:inserts.append((current.end_lineno,'\n'+''.join('    '+v+'\n' for v in additions)))
 for line,content in sorted(inserts,reverse=True):lines.insert(line,content)
 s=''.join(lines)
 if 'DOMAIN_ACCESS_SCOPE_ALL =' not in s:s=s.replace('class RFOneAccountDomainAccess(', 'DOMAIN_ACCESS_SCOPE_ALL = "ALL"\nDOMAIN_ACCESS_SCOPE_SELECTED = "SELECTED"\n\n\nclass RFOneAccountDomainAccess(')
 for name in ('EmployeeCloverLink','EmployeeContextLink','EmployeeIdentityAlias','EmployeeDirectoryEvent','RFOneAccountDomainItemAccess','Project','ProjectResponsible'):
  if name not in existing:s+='\n\n'+ast.get_source_segment(cs,cc[name])+'\n'
 write(p,s)
 if service=='tips':
  p=base/'Tips/app.py';transform(p,'app = Flask(__name__)','app = Flask(__name__)\nfrom rfone_data_store.web_access import install_access_context\ninstall_access_context(app, SessionFactory)\napp.extensions["rfone_managed_training"] = True')
  transform(p,'        if rfone_identity.current_account(db_session) is not None:\n            return None','        account = rfone_identity.current_account(db_session)\n        if account is not None:\n            if not shared_session.account_may_enter_domain(db_session, account, "TIPS"):\n                abort(403)\n            return None')
  current=(canonical/'Tips/app.py').read_text(encoding='utf-8');a=current.index('@app.before_request\ndef _central_training_entry');b=current.index('# RF-One UI Rules',a)
  transform(p,'# RF-One UI Rules',current[a:b]+'# RF-One UI Rules')
  copy('Training/auth.py',base)
 if service=='selection':
  p=base/'Selection/app.py';transform(p,'app = Flask(__name__)','app = Flask(__name__)\nfrom rfone_data_store.web_access import install_access_context\ninstall_access_context(app, SessionFactory)')
  text=p.read_text(encoding='utf-8');text=text.replace('run_migrations_to_head(_DB_URL)','# Migrations are explicit release operations.');write(p,text)
 if service=='kitchen':
  p=base/'RF-One Web/kitchen_cloud.py';transform(p,"app=Flask(__name__,static_url_path='/kitchen/static')","app=Flask(__name__,static_url_path='/kitchen/static')\nfrom rfone_data_store.web_access import install_access_context\ninstall_access_context(app, SessionFactory, load_current_account)")
  copy('RF-One Web/kitchen_routes.py',base)
 if service=='training':
  p=base/'RF-One Web/training_cloud.py';transform(p,"    app=Flask(__name__,static_url_path='/training/static')","    app=Flask(__name__,static_url_path='/training/static')\n    from rfone_data_store.web_access import install_access_context\n    install_access_context(app, factory, auth.load_current_account)")
  p=base/'RF-One Web/training_integration.py';text=p.read_text(encoding='utf-8');a=text.index('    if training_account.role != role_code:');b=text.index('\n\n\ndef _role_mismatch_response',a);text=text[:a]+'''    from rfone_data_store.web_access import AuthorizedTrainingAccount
    return TrainingAuthorizationResult(AuthorizedTrainingAccount(training_account, role_code), None)'''+text[b:]
  text=text.replace('        flask_session[TRAINING_SESSION_ACCOUNT_KEY] = result.training_account.id','        from flask import g\n        g.rfone_training_account = result.training_account\n        flask_session[TRAINING_SESSION_ACCOUNT_KEY] = result.training_account.id')
  ctext=(canonical/'RF-One Web/training_integration.py').read_text(encoding='utf-8');ctree=ast.parse(ctext)
  for name in ('is_pure_training_student','list_training_students'):
   target=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name);new=next(n for n in ctree.body if isinstance(n,ast.FunctionDef) and n.name==name);old=ast.get_source_segment(text,target);text=text.replace(old,ast.get_source_segment(ctext,new))
  write(p,text)
  # Preserve Training's own files and password-first-access logic; only adapt
  # the effective role at its existing auth loader.
  p=base/'Training/auth.py';text=p.read_text(encoding='utf-8');text=text.replace('from flask import ', 'from flask import g, ',1)
  old='    account_id = current_account_id()\n    if account_id is None:'
  assert old in text
  text=text.replace(old,'''    effective = getattr(g, "rfone_training_account", None)
    if effective is not None:
        from rfone_data_store.web_access import AuthorizedTrainingAccount
        identity = training_service.get_account(db_session, effective.id)
        return AuthorizedTrainingAccount(identity, effective.role) if identity else None
    account_id = current_account_id()
    if account_id is None:''');write(p,text)
  p=base/'RF-One Web/visual_menu_access.py';text=p.read_text(encoding='utf-8');a=text.index('        grant = db.scalar(');b=text.index('        if grant:',a);text=text[:a]+'''        from rfone_data_store import rfone_web_session as shared
        grant = shared.account_may_enter_domain(db, account, 'MYRF')
'''+text[b:];write(p,text)
  p=base/'RF-One Data Store/rfone_data_store/training/workspace.py';text=p.read_text(encoding='utf-8');a=text.index('        grants=[g for g in accounts.list_domain_access_for_account');b=text.index("            raise ValueError(",a);text=text[:a]+'''        from .. import access_profiles as profiles
        companies = profiles.company_ids_for_account(db, r.id) | {None}
        grants = [g for company in companies for g in profiles.effective_permissions(db, r.id, company_id=company).items()]
        if r.is_admin or not grants or any(code != 'TRAINING' or value['role_code'] != 'student' for code,value in grants):
'''+text[b:];write(p,text)
 # Include the current applied chain without altering any service-owned migration.
 versions=base/'RF-One Data Store/migrations/versions';versions.mkdir(parents=True,exist_ok=True)
 def revisions(folder):
  found={}
  for p in folder.glob('*.py'):
   for n in ast.parse(p.read_text(encoding='utf-8')).body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='revision' for t in n.targets):found[ast.literal_eval(n.value)]=p
  return found
 known=revisions(versions)
 for rev,p in revisions(canonical/'RF-One Data Store/migrations/versions').items():
  if rev not in known:shutil.copyfile(p,versions/p.name)
 trainingver=out/'training-source/03 Software/RF-One Data Store/migrations/versions'
 for rev,p in revisions(trainingver).items():
  if rev=='t9a120261110' and rev not in known:shutil.copyfile(p,versions/p.name)
 marker=base/'RF-One Data Store/migrations/aws_applied_revision.json';shutil.copyfile(out/'aws-schema.json',marker)
 checker=base/'RF-One Data Store/check_migration_chain.py'
 if not checker.exists():shutil.copyfile(canonical/'RF-One Data Store/check_migration_chain.py',checker)
 # Recompute artifact hashes only where the service already owns that manifest.
 mf=base/'RF-One Data Store/clover_connector_release.json'
 if mf.exists():
  data=json.loads(mf.read_text(encoding='utf-8'))
  for file in data.get('files',{}):
   target=base/file
   if target.exists():data['files'][file]=hashlib.sha256(target.read_bytes()).hexdigest()
  write(mf,json.dumps(data,indent=2)+'\n')
 changed={}
 for p in root.rglob('*'):
  if not p.is_file():continue
  name=str(p.relative_to(root)).replace('\\','/');after=p.read_bytes();old=before.get(name)
  if old!=after:changed[name]={'before':hashlib.sha256(old).hexdigest() if old is not None else None,'after':hashlib.sha256(after).hexdigest()}
 manifest[service]={'baseline':sourceinfo[service],'changed_files':changed}
 print(service,'changed files',len(changed))
(out/'patch-manifest.json').write_text(json.dumps(manifest,indent=2))
