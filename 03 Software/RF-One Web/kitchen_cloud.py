"""Kitchen-only AWS entrypoint. Shared RF-One auth; no account or grant bootstrap."""
from functools import wraps
from pathlib import Path
import os
from urllib.parse import urlencode
from flask import Flask,abort,redirect,request,jsonify
from sqlalchemy import text
if not os.environ.get('RFONE_DATABASE_URL'):raise RuntimeError('RFONE_DATABASE_URL is required for Kitchen AWS.')
from db import SessionFactory
from auth import require_login,load_current_account,require_csrf,get_csrf_token
from rfone_data_store import rfone_web_session as shared_session
from kitchen_routes import register_kitchen_routes

app=Flask(__name__,static_url_path='/kitchen/static')
from rfone_data_store.web_access import install_access_context
install_access_context(app, SessionFactory, load_current_account)
secret=os.environ.get('RFONE_FLASK_SECRET_KEY')
if not secret:raise RuntimeError('RFONE_FLASK_SECRET_KEY is required.')
app.secret_key=secret
app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
    KITCHEN_MEDIA_BUCKET=os.environ.get('KITCHEN_MEDIA_BUCKET'),KITCHEN_REQUIRE_S3=True,MAX_CONTENT_LENGTH=11*1024*1024)
PUBLIC=(os.environ.get('RFONE_PUBLIC_BASE_URL') or 'https://rfone.romesflavours.com').rstrip('/')


@app.context_processor
def kitchen_context():return dict(csrf_token=get_csrf_token,brand_logo_filename='rf-one.png')


@app.get('/health')
def health():
    with SessionFactory() as db:db.execute(text('SELECT 1'))
    return jsonify(status='ok',module='Kitchen',revision=os.environ.get('RFONE_RELEASE_REVISION','unknown'))


@app.get('/')
def root():return redirect('/kitchen')


@app.get('/kitchen/rf-one')
def home():return redirect(PUBLIC+'/')


@app.get('/kitchen/sign-in')
def login():
    target=request.args.get('next','/kitchen')
    if not target.startswith('/kitchen') or target.startswith('//'):target='/kitchen'
    return redirect(PUBLIC+'/login?'+urlencode({'next':target}))


@app.get('/kitchen/brand/<path:filename>')
def shared_brand_logo(filename):
    from flask import send_from_directory
    return send_from_directory(Path(__file__).resolve().parent.parent/'Shared UI/brand/logos',filename)


def require_domain_access(code):
    def decorate(view):
        @wraps(view)
        @require_login
        def wrapped(*args,**kwargs):
            with SessionFactory() as db:
                if not shared_session.account_may_enter_domain(db,load_current_account(db),code):abort(403)
            return view(*args,**kwargs)
        return wrapped
    return decorate


register_kitchen_routes(app,require_domain_access=require_domain_access,
    SessionFactory=SessionFactory,load_current_account=load_current_account,require_csrf=require_csrf)
