from pathlib import Path
p=Path(r'tmp/git-anagrafica-release/03 Software/Training/auth.py');s=p.read_text(encoding='utf-8');s=s.replace('''    if effective is not None:
        return effective''','''    if effective is not None:
        from rfone_data_store.web_access import AuthorizedTrainingAccount
        identity = training_service.get_account(db_session, effective.id)
        return AuthorizedTrainingAccount(identity, effective.role) if identity else None''');p.write_text(s,encoding='utf-8',newline='\n')
