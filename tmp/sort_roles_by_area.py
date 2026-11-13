from pathlib import Path
p=Path('03 Software/RF-One Web/role_profile_routes.py');t=p.read_text(encoding='utf-8');needle='        grants=defaultdict(dict)';assert needle in t;t=t.replace(needle,'''        area_names={area.id:area.name.casefold() for area in areas}
        for ids in pairs.values():ids.sort(key=lambda identity:(area_names.get(identity,''),identity))
        roles.sort(key=lambda role:(not bool(pairs[role.id]),tuple(area_names.get(identity,'') for identity in pairs[role.id]),role.name.casefold(),role.id))
''' +needle,1);p.write_text(t,encoding='utf-8')
