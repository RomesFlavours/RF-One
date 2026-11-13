from pathlib import Path
base=Path(r'C:\Users\servi\.codex\worktrees\edee\RF One\tmp\git-anagrafica-release\03 Software')
p=base/'RF-One Web/kitchen_routes.py';s=p.read_text(encoding='utf-8').replace("shared.allowed_domain_items(db, account, 'KITCHEN')","shared.allowed_domain_items(db, account, 'KITCHEN', [tab[0] for tab in TABS])").replace("    if items is None:\n        return list(TABS)\n",'');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Data Store/rfone_data_store/dev_journal/service.py';s=p.read_text(encoding='utf-8');start=s.index('    return list(db.scalars(',s.index('def journal_accounts'));end=s.index('\n\n\ndef _check_responsible',start);s=s[:start]+'''    from .. import rfone_web_session as shared
    candidates = db.scalars(select(m.RFOneAccount).where(
        m.RFOneAccount.status == "ACTIVE").order_by(m.RFOneAccount.display_name))
    return [account for account in candidates if shared.account_may_enter_domain(db, account, ACCESS_CODE)]
'''+s[end:];p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Data Store/rfone_data_store/rfone_web_session.py';s=p.read_text(encoding='utf-8');needle='''    if session_version != account.session_version:
        return None
    return account''';assert needle in s;s=s.replace(needle,'''    if session_version != account.session_version:
        return None
    # A stale ACTIVE account must not keep access after its canonical person
    # is dismissed. Owner access remains the explicitly approved exception.
    if not account.is_owner:
        from . import employee_directory as directory
        person_id = directory.context_person_id(db_session, "RFONE_ACCOUNT", account.id)
        if person_id is not None and not directory.employee_is_active(db_session.get(m.Employee, person_id), []):
            return None
    return account''');p.write_text(s,encoding='utf-8',newline='\n')
# Update audit to the coherent local source. Absence of a web context must stay fail-closed.
root=base.parents[2]
s=(root/'tmp/audit_registry_authorization_main.py').read_text(encoding='utf-8');s=s.replace("ROOT=Path('C:\\\\Users\\\\servi\\\\AppData\\\\Local\\\\RF-One\\\\Employee Directory\\\\AWS-20261110T120743Z\\\\development-source')",'ROOT=Path(r"'+str(base)+'")')
s=s.replace("record('Company role available without shell context '+domain.code,True,outside,'Standalone services must install company context; current library sees None')","record('No company context stays fail closed '+domain.code,False,outside)")
s=s.replace("record('Training role update opens without stale role mismatch',200,au_client.get('/training',follow_redirects=False).status_code)","record('Training role update opens without stale role mismatch',302,au_client.get('/training',follow_redirects=False).status_code)\nrecord('Training trainer destination actually opens',200,au_client.get('/training/trainer').status_code)")
s=s.replace("registry-authorization-main-audit.json","registry-authorization-main-fixed.json")
(root/'tmp/test_registry_authorization_main_fixed.py').write_text(s,encoding='utf-8')
print('Updated dismissed-session denial and Journal recipient policy.')

