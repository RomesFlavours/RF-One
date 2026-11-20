"""Read-only live acceptance using an existing authorized RF-One account.

Never creates accounts/grants or prints session cookies/credentials.
"""
import sys,json,hashlib
from pathlib import Path
import sqlalchemy as sa
import requests
sys.path.insert(0,'/app/RF-One Web')
from kitchen_cloud import app
from db import SessionFactory
from kitchen_routes import allowed_tabs
from rfone_data_store import models as models,rfone_web_session as shared
from rfone_data_store.kitchen import recipes,photos
with SessionFactory() as db:
    account=next((a for a in db.scalars(sa.select(models.RFOneAccount).where(models.RFOneAccount.status=='ACTIVE')) if len(allowed_tabs(db,a))==4),None)
    assert account is not None,'No already-authorized account; no grant created'
    aid,version=account.id,account.session_version
    rid=db.scalar(sa.select(recipes.c.id).order_by(recipes.c.id).limit(1))
    photo=db.execute(sa.select(photos).order_by(photos.c.id.desc()).limit(1)).mappings().first()
payload={shared.SESSION_ACCOUNT_KEY:aid,shared.SESSION_VERSION_KEY:version}
cookie=app.session_interface.get_signing_serializer(app).dumps(payload)
session=requests.Session();session.cookies.set('session',cookie,domain='rfone.romesflavours.com',path='/')
checks={}
for path in ('/','/kitchen/dashboard','/kitchen/recipes','/kitchen/configuration','/kitchen/menus','/kitchen/recipes/options',f'/kitchen/recipes/{rid}/data',f'/kitchen/recipes/{rid}/plating'):
    response=session.get('https://rfone.romesflavours.com'+path,allow_redirects=False,timeout=35)
    assert response.status_code==200,(path,response.status_code)
    if path=='/':assert 'href="/kitchen"' in response.text,'Kitchen missing from assigned MyRFOne home'
    elif path in ('/kitchen/dashboard','/kitchen/recipes','/kitchen/configuration','/kitchen/menus'):assert 'data-how-works' in response.text
    checks[path]=response.status_code
if photo:
    path=f"/kitchen/recipes/{photo['recipe_id']}/plating/image"
    response=session.get('https://rfone.romesflavours.com'+path,timeout=35);assert response.status_code==200
    assert hashlib.sha256(response.content).hexdigest()==photo['sha256'],'Private S3 image bytes changed'
    checks['private_plating_image']=200
response=requests.get('https://rfone.romesflavours.com/kitchen/menus',allow_redirects=False,timeout=30);assert response.status_code==302
checks['anonymous_menu_denied']=302
print('KITCHEN_RESULT='+json.dumps(dict(verified=True,checks=checks,existing_identity_only=True,mutations=False)),flush=True)
