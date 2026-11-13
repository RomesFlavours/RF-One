from pathlib import Path
import ast,difflib
c=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/rfone_data_store/models.py').read_text(encoding='utf-8');classes={n.name:n for n in ast.parse(c).body if isinstance(n,ast.ClassDef)}
for service in ('training','kitchen','selection','tips'):
 root=Path('tmp/registry-access-release')/(service+'-source');base=root/'03 Software' if (root/'03 Software').exists() else root;s=(base/'RF-One Data Store/rfone_data_store/models.py').read_text(encoding='utf-8');cs={n.name:n for n in ast.parse(s).body if isinstance(n,ast.ClassDef)}
 print(service)
 for name in ('Employee','RFOneAccount','RFOneAccountDomainAccess','RestaurantRole','OperationalArea'):
  fields=lambda node:{v.target.id for v in node.body if isinstance(v,ast.AnnAssign) and isinstance(v.target,ast.Name)}
  print(name,fields(classes[name])-fields(cs[name]))
 a=Path('tmp/registry-access-release/web-source/RF-One Data Store/rfone_data_store/rfone_account_service.py').read_text(encoding='utf-8').replace('list_direct_domain_access_for_account','list_domain_access_for_account').replace('list_direct_domain_item_access_for_account','list_domain_item_access_for_account');b=(base/'RF-One Data Store/rfone_data_store/rfone_account_service.py').read_text(encoding='utf-8')
 print('service diff lines',len(list(difflib.unified_diff(a.splitlines(),b.splitlines()))))
