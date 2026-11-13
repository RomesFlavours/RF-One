from pathlib import Path
base=Path(r'tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Web/training_integration.py';s=p.read_text(encoding='utf-8');a=s.index('    access_rows =',s.index('def is_pure_training_student'));b=s.index('\n\n\ndef list_training_students',a);s=s[:a]+'''    from rfone_data_store import access_profiles as profiles
    companies = profiles.company_ids_for_account(session, rfone_account.id) | {None}
    grants = [value for company in companies for value in
              profiles.effective_permissions(session, rfone_account.id, company_id=company).items()]
    return bool(grants) and all(code == TRAINING_DOMAIN_CODE and
                               effective_training_role(value['role_code']) == 'student'
                               for code, value in grants)
'''+s[b:];p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_registry_standalone_access.py';s=p.read_text(encoding='utf-8-sig').replace('"selection":("/","/candidates")','"selection":("/","/requirements")');p.write_text(s,encoding='utf-8',newline='\n')
