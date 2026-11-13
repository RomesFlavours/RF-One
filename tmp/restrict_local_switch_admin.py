from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/Infrastructure/Registry Local/launch_local.py')
s=p.read_text(encoding='utf-8')
marker='def user_controls():\n    with SessionFactory() as db:\n'
assert marker in s
s=s.replace(marker,'''def local_administrator(db):
    account=shared.account_for_session(db,
        account_id=browser_session.get(shared.SESSION_ACCOUNT_KEY),
        session_version=browser_session.get(shared.SESSION_VERSION_KEY))
    return bool(account and (account.is_admin or account.is_owner))


def require_local_administrator():
    with SessionFactory() as db:
        if not local_administrator(db):abort(403)


def user_controls():
    with SessionFactory() as db:
        if not local_administrator(db):return ''
''')
s=s.replace("def local_users():\n    return", "def local_users():\n    require_local_administrator()\n    return")
s=s.replace("def select_local_user():\n    if", "def select_local_user():\n    require_local_administrator()\n    if")
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('tmp/git-anagrafica-release/03 Software/Infrastructure/Registry Local/README.md');s=p.read_text(encoding='utf-8');s+='''
## Administrator restriction (2026-11-10)

Switch user is rendered only for a currently valid RF1 platform administrator
or owner. Both GET /local/users and POST /local/access-user validate that same
permission server-side before listing accounts or changing identity. Domain
administrator roles do not confer this capability. After selecting a nonadmin
account, the control disappears and that account cannot use either endpoint.
The restriction is checked afresh, including inactive/revoked sessions.
''';p.write_text(s,encoding='utf-8',newline='\n')
