"""Copy the confirmed Bank shell and its static import closure; no data or deploy tooling."""
import ast,hashlib,importlib.util,json,pathlib,re,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1];SOURCE=ROOT.parent/'BankMerge';SW=SOURCE/'03 Software'
DEST=ROOT/'03 Software';PARK=ROOT/'parking'/'previous-rules'
if (DEST/'RF-One Web'/'app.py').exists():
 raise SystemExit('Il modulo RFBank esiste già: trasferimento interrotto per non sovrascrivere il lavoro locale.')
exclude_modules={'compensation_routes','workweek_settings_routes','organizational_responsibility_routes','tips_validation_routes','clover_acquisition_routes','projects_routes','training_integration'}
exclude_calls={'register_compensation_routes','register_workweek_settings_routes','register_organizational_responsibility_routes','register_tips_validation_routes','register_clover_acquisition_routes','register_projects_routes'}
appfile=SW/'RF-One Web'/'app.py';tree=ast.parse(appfile.read_text(encoding='utf-8-sig'))
kept=[]
for n in tree.body:
 code=ast.unparse(n)
 if isinstance(n,(ast.Import,ast.ImportFrom)):
  module=n.module if isinstance(n,ast.ImportFrom) else n.names[0].name
  if module in exclude_modules:continue
 if 'training_integration' in code or '_training_bp' in code:continue
 if isinstance(n,ast.FunctionDef) and n.name.startswith('training_'):continue
 if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call):
  target=ast.unparse(n.value.func)
  if target in exclude_calls:continue
 # Other domains' route bodies are not part of the Bank shell.
 if isinstance(n,ast.FunctionDef):
  routes=[d for d in n.decorator_list if isinstance(d,ast.Call) and ast.unparse(d.func)=='app.route']
  if routes and n.name not in ('home','login','logout','profile','shared_brand_logo'):continue
 kept.append(n)
tree.body=kept
patched={appfile:ast.unparse(tree)+'\n'}
cf=SW/'RF-One Web'/'bank_configuration_routes.py'
patched[cf]=cf.read_text(encoding='utf-8-sig').replace('    from bank_category_trial import register as register_category_trial\n','').replace('    register_category_trial(app, gate, SessionFactory, require_csrf)\n','')
roots=[SW/'RF-One Web',SW/'RF-One Data Store',SW/'C-Bank Prototype',SW/'Clover Data Explorer']
modules={};names={}
for base in roots:
 for f in base.rglob('*.py'):
  if '__pycache__' in f.parts or 'tests' in f.parts or f.name.startswith('test_'):continue
  rel=f.relative_to(base).with_suffix('');parts=list(rel.parts)
  if parts[-1]=='__init__':parts.pop()
  name='.'.join(parts)
  if name:modules.setdefault(name,f);names[f]=name
selected=set();queue=[appfile,SW/'C-Bank Prototype'/'cbank'/'web.py']
# Bank's dynamic web imports are seeded, except the replaced category trial.
queue += [p for p in (SW/'RF-One Web').glob('bank*.py') if p.name!='bank_category_trial.py']
while queue:
 f=queue.pop()
 if f in selected:continue
 selected.add(f)
 name=names.get(f,'');package=name if f.name=='__init__.py' else name.rpartition('.')[0]
 for node in ast.walk(ast.parse(patched.get(f) or f.read_text(encoding='utf-8-sig'))):
  candidates=[]
  if isinstance(node,ast.Import):candidates=[a.name for a in node.names]
  elif isinstance(node,ast.ImportFrom):
   mod=node.module or ''
   if node.level:
    try:mod=importlib.util.resolve_name('.'*node.level+mod,package)
    except (ValueError,ImportError):continue
   candidates=[mod]+[mod+'.'+a.name for a in node.names if a.name!='*']
  for target in candidates:
   parts=target.split('.')
   for i in range(1,len(parts)+1):
    p=modules.get('.'.join(parts[:i]))
    if p and p not in selected:queue.append(p)
manifest=[]
def copy(f):
 rel=f.relative_to(SOURCE);out=ROOT/rel;out.parent.mkdir(parents=True,exist_ok=True)
 if f in patched:out.write_text(patched[f],encoding='utf-8')
 else:shutil.copyfile(f,out)
 manifest.append({'source':str(f),'destination':str(out),'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'destination_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'adapted':f in patched})
for f in sorted(selected):copy(f)
# Original Bank templates and shared layout macros; no other domains' pages.
web=SW/'RF-One Web'
templates={p for p in (web/'templates').glob('*.html') if p.name.startswith(('bank','_bank','_nav','_site')) or p.name=='base.html'}
templates={p for p in templates if p.name!='bank_category_trial.html'}
queue=list(templates)
while queue:
 p=queue.pop()
 for name in re.findall(r'{%\s*(?:extends|include|import|from)\s+[\'"]([^\'"]+)',p.read_text(encoding='utf-8-sig')):
  child=web/'templates'/name
  if child.is_file() and child not in templates:templates.add(child);queue.append(child)
for f in sorted(templates):copy(f)
for f in (web/'static').rglob('*'):
 if f.is_file() and (f.suffix in ('.css','.png','.svg','.ico') or (f.suffix=='.js' and (f.name.startswith(('bank','rf-one')) or 'bank-assistant' in f.parts))):
  if f.name!='bank-category-trial.js':copy(f)
for f in (SW/'C-Bank Prototype'/'cbank'/'templates').rglob('*'):
 if f.is_file():copy(f)
for f in (SW/'Shared UI'/'brand').rglob('*'):
 if f.is_file() and f.suffix.lower() in ('.svg','.png','.jpg','.ico'):copy(f)
# Keep the replaced experiment recoverable, outside the active module.
for f in [web/'bank_category_trial.py',web/'templates'/'bank_category_trial.html',web/'static'/'js'/'bank-category-trial.js']:
 if f.exists():
  out=PARK/f.relative_to(web);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,out)
(ROOT/'module-transfer.json').write_text(json.dumps({'origin':str(SOURCE),'files':manifest,'parked':str(PARK),'excluded_domains':sorted(exclude_modules)},indent=2),encoding='utf-8')
print(json.dumps({'python_files':len(selected),'templates':len(templates),'total_files':len(manifest)}))
