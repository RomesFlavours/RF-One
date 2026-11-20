"""Training AWS entry point using the existing RF-One session and real grants."""
from pathlib import Path
import os
from urllib.parse import urlencode
from flask import Flask,abort,jsonify,redirect,request,url_for
from sqlalchemy import select,text
import auth
from db import SessionFactory as DefaultSessionFactory
from rfone_data_store import display_format
from rfone_data_store import models as m
import training_integration

PUBLIC=(os.environ.get('RFONE_PUBLIC_BASE_URL') or 'https://rfone.romesflavours.com').rstrip('/')


def create_app(*,SessionFactory=None):
    factory=SessionFactory or DefaultSessionFactory
    app=Flask(__name__,static_url_path='/training/static')
    from rfone_data_store.web_access import install_access_context
    install_access_context(app, factory, auth.load_current_account)
    secret=os.environ.get('RFONE_FLASK_SECRET_KEY') or os.environ.get('RFONE_WEB_TEST_SECRET_KEY')
    if not secret:raise RuntimeError('The shared RF-One secret is required.')
    app.secret_key=secret
    app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
        MAX_CONTENT_LENGTH=30*1024*1024,MAX_FORM_MEMORY_SIZE=2*1024*1024,
        KITCHEN_MEDIA_BUCKET=os.environ.get('KITCHEN_MEDIA_BUCKET'),KITCHEN_REQUIRE_S3=True)
    app.jinja_env.globals.update(ui=lambda value:value,rfone_home_url=lambda:url_for('home'),zone_label=display_format.zone_label)
    app.jinja_env.filters.update(local_dt=display_format.local_datetime,short_name=display_format.employee_short_name)

    @app.context_processor
    def shared_context():
        legacy=(request.endpoint or '').split('.')[-1]
        with factory() as db:
            timezone=db.scalar(select(m.Location.timezone).where(m.Location.timezone.is_not(None)).order_by(m.Location.id))
        return dict(csrf_token=auth.get_csrf_token,brand_logo_filename='rf-one.png',tz=timezone,
            help_section='training_legacy_'+legacy if request.blueprint=='training' else None)

    @app.get('/health')
    def health():
        with factory() as db:db.execute(text('SELECT 1'))
        return jsonify(status='ok',module='Training',revision=os.environ.get('RFONE_RELEASE_REVISION','unknown'))

    @app.get('/')
    def home():return redirect(PUBLIC+'/')

    @app.get('/training/sign-in')
    def login():
        target=request.args.get('next','/training')
        if not target.startswith(('/training','/visual-menu')) or target.startswith('//'):target='/training'
        return redirect(PUBLIC+'/login?'+urlencode({'next':target}))

    @app.get('/training/brand/<path:filename>')
    def shared_brand_logo(filename):
        from flask import send_from_directory
        return send_from_directory(Path(__file__).resolve().parent.parent/'Shared UI/brand/logos',filename)

    @app.get('/training/menu')
    def training_menu():
        from flask import send_file
        return send_file(Path(__file__).resolve().parent.parent/'Training/RF-One-Training.html')

    @app.get('/training-trainer/students')
    @app.get('/training-trainer/students/new')
    def legacy_student_entry():return redirect(url_for('tw_students'))

    app.register_blueprint(training_integration.install_training_blueprint())
    from training_workspace_routes import install
    install(app,SessionFactory=factory,auth=auth)
    from visual_menu_routes import register_visual_menu_routes
    register_visual_menu_routes(app,SessionFactory=factory,load_current_account=auth.load_current_account,require_csrf=auth.require_csrf)

    @app.before_request
    def training_boundary():
        response=training_integration.enforce_training_sso(auth,factory)
        if response is not None:return response
        if request.blueprint=='training':
            with factory() as db:
                account=auth.load_current_account(db)
                result=training_integration.check_training_authorization(db,account)
                if result.training_account and result.training_account.role=='trainer' and (request.endpoint=='training.home' or request.endpoint.startswith('training.trainer_')):
                    if request.method=='GET':return redirect(url_for('tw_students'))
                    abort(404)
    # SSO checks run before the legacy Training blueprint; first-access checks
    # remain earlier so no shared page bypasses mandatory password replacement.

    @app.errorhandler(413)
    def oversized_upload(error):return jsonify(error='The save exceeds 30 MB. Upload materials in smaller batches.'),413

    return app


app=create_app()
