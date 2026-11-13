from pathlib import Path
import ast
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/rfone_data_store/models.py');s=p.read_text(encoding='utf-8');t=ast.parse(s)
for n in t.body:
 if isinstance(n,ast.ClassDef) and n.name in ('ProjectResponsible','RFOneAccountDomainItemAccess'):
  print(ast.get_source_segment(s,n)[:2500])
