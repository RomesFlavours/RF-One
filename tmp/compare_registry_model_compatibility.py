from pathlib import Path
import ast
base=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/rfone_data_store/models.py');tree=ast.parse(base.read_text(encoding='utf-8'));classes={n.name:n for n in tree.body if isinstance(n,ast.ClassDef)}
for service in ('training','kitchen','selection','tips'):
 r=Path('tmp/registry-access-release')/(service+'-source');r=r/'03 Software' if (r/'03 Software').exists() else r;t=ast.parse((r/'RF-One Data Store/rfone_data_store/models.py').read_text(encoding='utf-8'));c={n.name:n for n in t.body if isinstance(n,ast.ClassDef)}
 print(service,'missingclasses',list(set(classes)-set(c)),'extra',list(set(c)-set(classes)))
 for name in ('Employee','RFOneAccount'):
  names=lambda n:{v.targets[0].id for v in n.body if isinstance(v,ast.Assign) and isinstance(v.targets[0],ast.Name)}
  print(name,'missing',names(classes[name])-names(c[name]))
