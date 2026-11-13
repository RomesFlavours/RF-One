from pathlib import Path
base=Path(r'tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Data Store/rfone_data_store/web_access.py';s=p.read_text(encoding='utf-8');needle='    app.extensions["registry_access_context"] = True';s=s.replace(needle,needle+'''
    @app.after_request
    def protect_authorized_response(response):
        # A permission-dependent page must be rechecked after a Registry change.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response
''');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_registry_standalone_access.py';s=p.read_text(encoding='utf-8');s=s.replace('engine=create_configured_engine', 'from rfone_data_store import kitchen, kitchen_configuration\nengine=create_configured_engine');p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/tests/test_training_role_sync.py';s=p.read_text(encoding='utf-8');a=s.index('        check("incoherent GET /training -> 403"');b=s.index('        with SessionFactory() as s:',a);s=s[:a]+'''        check("Registry student role opens despite legacy stored trainer role", resp.status_code == 200)
        denied = incoherent_client.get("/training/trainer")
        check("Legacy stored trainer role cannot elevate a Registry student", denied.status_code == 403)
        with incoherent_client.session_transaction() as sess:
            check("RF1 identity stays intact", sess.get("rfone_account_id") == incoherent_id)

'''+s[b:];s=s.replace('GET Training con ruoli incoerenti: 403, ruoli invariati, sessione pulita','GET Training: ruolo effettivo Registry, dati di identita invariati');p.write_text(s,encoding='utf-8',newline='\n')
# Extend the existing acceptance suite using actual Registry HTTP writes.
p=base/'RF-One Web/tests/test_role_company_http.py';s=p.read_text(encoding='utf-8');end=s.index("print(json.dumps({'checks_passed'")
extra=Path('tmp/test_registry_authorization_main_fixed.py').read_text(encoding='utf-8');a=extra.index('with SessionFactory() as db:\n    employee=m.Employee(display_name=');b=extra.index("post(action='permissions',id=audit_role,access_KITCHEN='all')",a)
extra=extra[a:b]
setup='''
audit=[]
def record(name,expected,actual,detail=None):
    check(name, expected == actual)
for domain in web.DOMAINS:
    web.app.add_url_rule('/_audit/gate/'+domain.code,endpoint='audit_'+domain.code,
        view_func=web.require_domain_access(domain.code)(lambda:'allowed'))
'''
# Flask routes must be registered before first request.
setup_at=s.index('passed=[]')
s=s[:setup_at]+setup.replace('audit=[]\n','')+s[setup_at:]
end=s.index("print(json.dumps({'checks_passed'")
s=s[:end]+extra+'''
# Downgrade and revocation must also block a previously authorized trainer URL.
post(action='permissions',id=audit_role,access_TRAINING='all',role_TRAINING='student')
check('Trainer downgrade closes trainer page immediately',au_client.get('/training/trainer').status_code==403)
check('Student page still opens after downgrade',au_client.get('/training',follow_redirects=False).status_code==200)
post(action='permissions',id=audit_role)
check('Training revoke denies existing open session',au_client.get('/training').status_code==302)
with SessionFactory() as db:
    db.get(m.Employee,person_id).active=False
    db.get(m.RFOneAccount,au_id).is_admin=True
    db.commit()
check('Dismissed nonowner admin loses Registry management',au_client.get('/admin/roles').status_code in (302,403))
'''+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
# Correct stale module documentation about stored Training role authority.
p=base/'RF-One Web/training_integration.py';s=p.read_text(encoding='utf-8');a=s.index('`role_code` is authoritative');b=s.index('"""',a);s=s[:a]+'''Registry effective permissions are authoritative in the current company.
The Training identity and its history remain domain-owned. A request-only
role view applies the current effective role without rewriting stored
Training identity data during navigation.
'''+s[b:];a=s.index('    """Re-verifies (every call');b=s.index('\n    access_rows =',a);s=s[:a]+'''    """Read-only, per-request Registry authorization with a linked domain identity.

    The role can differ across companies; a stored Training role cannot
    replace the effective Registry role or preserve a revoked privilege.
    """
'''+s[b:];p.write_text(s,encoding='utf-8',newline='\n')
print('Added cross-domain and trainer downgrade regression checks.')
