from pathlib import Path
p=Path('tmp/launch_registry_local.py');s=p.read_text(encoding='utf-8')
s=s.replace('from html import escape','''from html import escape
from flask import g
from itsdangerous import URLSafeSerializer, BadSignature
local_signer=URLSafeSerializer(web.app.secret_key,salt='loopback-user-selection')
LOCAL_CHOICE_COOKIE='rfone_local_user_choice' ''')
a=s.index("    # Bootstrap once.");b=s.index("    if request.path in ('/login','/logout'):",a)
s=s[:a]+'''    # Keep the explicit choice outside the RF1 session: a denied/inactive
    # account must never fall back to owner after auth clears that session.
    choice=None
    try:
        choice=local_signer.loads(request.cookies.get(LOCAL_CHOICE_COOKIE,''))
    except BadSignature:
        pass
    if not browser_session.get('local_user_selected'):
        if choice is None:
            with SessionFactory() as db:
                owner=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.status=='ACTIVE',m.RFOneAccount.is_owner.is_(True)))
                assert owner is not None
                choice={'id':owner.id,'version':owner.session_version}
        browser_session.clear()
        browser_session['local_user_selected']=True
        browser_session[shared.SESSION_ACCOUNT_KEY]=choice['id']
        browser_session[shared.SESSION_VERSION_KEY]=choice['version']
    g.local_user_choice=choice or {'id':browser_session.get(shared.SESSION_ACCOUNT_KEY),'version':browser_session.get(shared.SESSION_VERSION_KEY)}
'''+s[b:]
needle="    return redirect('/')\n\n\ndef install_local"
s=s.replace(needle,"""        choice={'id':account.id,'version':account.session_version}
    response=redirect('/')
    response.set_cookie(LOCAL_CHOICE_COOKIE,local_signer.dumps(choice),httponly=True,samesite='Lax',path='/')
    return response


def install_local""")
s=s.replace("        response.headers['Cache-Control']='no-store'","""        response.headers['Cache-Control']='no-store'
        if not request.cookies.get(LOCAL_CHOICE_COOKIE) and getattr(g,'local_user_choice',None):
            response.set_cookie(LOCAL_CHOICE_COOKIE,local_signer.dumps(g.local_user_choice),httponly=True,samesite='Lax',path='/')""")
p.write_text(s,encoding='utf-8',newline='\n')
# Fix an obsolete Home assertion after the requested removal of Accounts.
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_training_integration_http.py');s=p.read_text(encoding='utf-8').replace("resp.status_code == 200 and b'href=\"/admin/accounts\"' in resp.data","resp.status_code == 200 and b'href=\"/admin/roles?tab=people\"' in resp.data and b'href=\"/admin/accounts\"' not in resp.data");p.write_text(s,encoding='utf-8',newline='\n')
p=Path('tmp/verify_registry_local_users.py');s=p.read_text(encoding='utf-8');s=s.replace("from sqlalchemy import select,func","from sqlalchemy import select,func\nsys.path.insert(0,str(source/'RF-One Web'))\nfrom domain_registry import DOMAINS_BY_CODE")
s=s.replace("   response=c.get(base+path", """   item_grant=grants.get(domain)
   if item_grant and item_grant['scope']=='SELECTED':
    items=DOMAINS_BY_CODE[domain].items
    first=next((item for item in items if item.code in item_grant['items']),None)
    if first:path=(first.exact_paths or first.paths)[0]
   response=c.get(base+path""")
p.write_text(s,encoding='utf-8',newline='\n')
