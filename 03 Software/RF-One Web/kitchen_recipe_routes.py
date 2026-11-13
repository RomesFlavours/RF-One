"""Authenticated Kitchen recipe editor; every mutation is CSRF protected."""
import json
from pathlib import Path
from flask import abort, jsonify, make_response, render_template, request, send_file, url_for
from sqlalchemy.exc import IntegrityError
from botocore.exceptions import BotoCoreError,ClientError
from kitchen_media_response import serve_kitchen_image
from rfone_data_store import kitchen_editor as editor
from rfone_data_store import kitchen_plating as plating


def register_recipe_routes(app, *, gate, SessionFactory, load_current_account, allowed_tabs, require_csrf):
    root=Path(__file__).resolve().parents[2]
    app.config.setdefault('KITCHEN_PLATING_UPLOAD_DIR',str(root/'output/kitchen-plating'))
    def access(db):
        account=load_current_account(db)
        tabs=allowed_tabs(db,account) if account else []
        if not any(t[0]=='RECIPES' for t in tabs):abort(403)
        return tabs

    def response(payload,status=200):
        result=jsonify(payload);result.status_code=status;result.headers['Cache-Control']='no-store';return result

    @app.get('/kitchen/recipes')
    @gate
    def kitchen_recipes():
        with SessionFactory() as db:
            tabs=access(db);rows=editor.listing(db)
        result=make_response(render_template('kitchen_recipes.html',kitchen_tabs=tabs,active_tab='RECIPES',ui=lambda s:s,recipes=rows))
        result.headers['Cache-Control']='no-store';return result

    @app.get('/kitchen/recipes/options')
    @gate
    def kitchen_recipe_options():
        with SessionFactory() as db:
            access(db);return response(editor.options(db))

    @app.get('/kitchen/recipes/<int:recipe_id>/plating')
    @gate
    def kitchen_recipe_plating(recipe_id):
        with SessionFactory() as db:
            access(db)
            try:data=plating.read(db,recipe_id)
            except editor.EditorError as exc:return response({'error':str(exc)},404)
            photo=data.pop('photo')
            data['image_url']=url_for('kitchen_recipe_plating_image',recipe_id=recipe_id,v=photo['id']) if photo else None
            return response(data)

    @app.get('/kitchen/recipes/<int:recipe_id>/plating/image')
    @gate
    def kitchen_recipe_plating_image(recipe_id):
        with SessionFactory() as db:
            access(db)
            try:editor.record(db,recipe_id)
            except editor.EditorError:abort(404)
            photo=plating.current_photo(db,recipe_id)
            if photo is None:abort(404)
            return serve_kitchen_image(photo['asset_uri'],photo['mime_type'])

    @app.post('/kitchen/recipes/<int:recipe_id>/plating')
    @gate
    def kitchen_recipe_plating_save(recipe_id):
        created=None;committed=False
        with SessionFactory() as db:
            access(db)
            if require_csrf is None:abort(400)
            require_csrf()
            try:
                image=request.files.get('image')
                content=image.stream.read(plating.LIMIT+1) if image and image.filename else None
                recipe,created=plating.save(db,recipe_id,revision=request.form.get('revision'),
                    description=request.form.get('description'),content=content,directory=app.config['KITCHEN_PLATING_UPLOAD_DIR'],storage_bucket=app.config.get('KITCHEN_MEDIA_BUCKET'))
                db.commit();committed=True;return response({'recipe':recipe})
            except (editor.EditorError,IntegrityError) as exc:
                db.rollback()
                return response({'error':str(exc) if isinstance(exc,editor.EditorError) else 'The plating could not be saved. Close and reopen the record.'},409 if isinstance(exc,(editor.StaleRecipe,IntegrityError)) else 400)
            except (OSError,BotoCoreError,ClientError):
                db.rollback()
                return response({'error':'The image could not be stored. Your description and file selection remain in the dialog.'},503)
            finally:
                if created and not committed:created.unlink(missing_ok=True)

    @app.get('/kitchen/recipes/<int:recipe_id>/data')
    @gate
    def kitchen_recipe_data(recipe_id):
        with SessionFactory() as db:
            access(db)
            try:return response(editor.composition(db,recipe_id))
            except editor.EditorError as exc:return response({'error':str(exc)},404)

    @app.post('/kitchen/recipes/save')
    @app.post('/kitchen/recipes/<int:recipe_id>/composition')
    @gate
    def kitchen_recipe_save(recipe_id=None):
        with SessionFactory() as db:
            access(db)
            if require_csrf is None:abort(400)
            require_csrf()
            try:
                if recipe_id is None:result={'recipe':editor.save_metadata(db,request.form)}
                else:
                    data=json.loads(request.form.get('payload',''))
                    if not isinstance(data,dict):raise editor.EditorError('Invalid recipe draft.')
                    result=editor.save_composition(db,recipe_id,data)
                db.commit();return response(result)
            except (editor.EditorError,IntegrityError,ValueError,TypeError) as exc:
                db.rollback()
                message=str(exc) if isinstance(exc,editor.EditorError) else 'The recipe could not be saved. Check the fields and reopen if it changed.'
                return response({'error':message},409 if isinstance(exc,(editor.StaleRecipe,IntegrityError)) else 400)
