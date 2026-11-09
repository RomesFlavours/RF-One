"""Kitchen Board HTTP factory. No DDL, network calls or background jobs at import."""
import hmac
import base64
import hashlib
import re
import secrets
from pathlib import Path
from datetime import timezone
from functools import wraps
from zoneinfo import ZoneInfo

import bootstrap  # noqa: F401
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import select
from rfone_data_store import models as m
from store import Board, Ticket, now, pending, release
from kitchen_filter import categories_by_line, kitchen_payload, timing_by_line
from display_settings import read_settings, save_settings, validated, SettingsError, SettingsConflict


def create_app(session_factory, *, secret, view_token, release_token, local=False):
    if any(len(value or '') < 32 for value in (secret, view_token, release_token)):
        raise ValueError('Kitchen Board secrets must each contain at least 32 characters')
    if len({secret, view_token, release_token}) != 3:
        raise ValueError('Use three distinct Kitchen Board secrets')
    app = Flask(__name__)
    app.secret_key = secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=not local, MAX_CONTENT_LENGTH=4096)
    locale = 'it' if local else 'en'
    component = (Path(__file__).parent / 'templates' / '_how_works.html').read_text(encoding='utf-8')
    help_hashes = ' '.join("'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'"
                           for script in re.findall(r'<script>(.*?)</script>', component, re.S))

    def bearer():
        header = request.headers.get('Authorization', '')
        return header[7:] if header.startswith('Bearer ') else ''

    def is_token(candidate, expected):
        return hmac.compare_digest(candidate.encode(), expected.encode())

    def allowed(write=False, configuration=False):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                token = bearer()
                valid = is_token(token, release_token) or (not write and is_token(token, view_token))
                if not write and session.get('board_view'):
                    valid = True
                if configuration and session.get('board_manage'):
                    valid = True
                if not valid:
                    if request.path.startswith('/api/'):
                        abort(401)
                    return redirect(url_for('login', next=request.path))
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    @app.after_request
    def secure(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = f"default-src 'self'; script-src 'self' {help_hashes}; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
        return response

    @app.context_processor
    def labels():
        return {'locale': locale, 'it': locale == 'it'}

    def configured(db, location_id):
        board = db.get(Board, location_id)
        location = db.get(m.Location, location_id)
        if board is None or location is None:
            abort(404)
        if not location.timezone:
            abort(409, description='Location timezone is required')
        return board, location

    def serialize(ticket, location, category_lookup=None, timing_lookup=None):
        created = ticket.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return {**kitchen_payload(ticket.payload, category_lookup or {}, timing_lookup), 'order_id': ticket.order_id, 'rfone_order_id': ticket.rfone_order_id,
                'created_at': created.isoformat(), 'local_time': created.astimezone(ZoneInfo(location.timezone)).strftime('%H:%M'),
                'released_at': ticket.released_at.isoformat() if ticket.released_at else None,
                'released_by': ticket.released_by}

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = False
        if request.method == 'POST':
            candidate=request.form.get('token','')
            manager=is_token(candidate,release_token)
            if manager or is_token(candidate, view_token):
                session.clear()
                session['board_view'] = True
                session['board_manage'] = manager
                target = request.args.get('next', '/')
                return redirect(target if target.startswith('/') and not target.startswith('//') else '/')
            error = True
        return render_template('login.html', error=error), (401 if error else 200)

    @app.get('/')
    @allowed()
    def home():
        with session_factory() as db:
            locations = list(db.execute(select(Board.location_id, m.Location.name)
                .join(m.Location, m.Location.id == Board.location_id)))
            return render_template('home.html', locations=locations)

    @app.get('/board/<int:location_id>')
    @allowed()
    def board_page(location_id):
        with session_factory() as db:
            _, location = configured(db, location_id)
            return render_template('board.html', location=location)

    @app.get('/api/locations/<int:location_id>/orders')
    @allowed()
    def orders(location_id):
        with session_factory() as db:
            board, location = configured(db, location_id)
            last = board.last_sync
            if last and not last.tzinfo:
                last = last.replace(tzinfo=timezone.utc)
            waiting = pending(db, location_id)
            categories = categories_by_line(db, location_id, [t.order_id for t in waiting])
            timings = timing_by_line(db, location_id, [t.order_id for t in waiting])
            tickets = [serialize(t, location, categories, timings) for t in waiting]
            tickets = [ticket for ticket in tickets if ticket['lines']]
            return jsonify(orders=tickets,
                visible_count=board.visible_count, total=len(tickets),
                display_settings=read_settings(db,board),
                last_sync=last.isoformat() if last else None, sync_error=bool(board.sync_error),
                stale=not last or (now()-last).total_seconds() > 60)

    @app.post('/api/locations/<int:location_id>/orders/<order_id>/release')
    @allowed(write=True)
    def release_order(location_id, order_id):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get('released_by'), str) or not 1 <= len(body['released_by'].strip()) <= 255:
            abort(400)
        with session_factory() as db:
            configured(db, location_id)
            try:
                return jsonify(release(db, location_id, order_id, body['released_by'].strip()))
            except LookupError:
                abort(404)

    @app.post('/api/locations/<int:location_id>/settings')
    @allowed(write=True)
    def settings(location_id):
        body = request.get_json(silent=True)
        try: changes=validated(body)
        except SettingsError: abort(400)
        with session_factory() as db:
            board, _ = configured(db, location_id)
            try: result=save_settings(db,board,changes)
            except SettingsConflict: abort(409)
        return jsonify(result)

    @app.route('/settings/<int:location_id>',methods=['GET','POST'])
    @allowed(write=True,configuration=True)
    def display_settings_page(location_id):
        if 'settings_csrf' not in session:
            session['settings_csrf']=secrets.token_urlsafe(32)
        error=None; status=200
        with session_factory() as db:
            board,location=configured(db,location_id)
            values=read_settings(db,board)
            if request.method=='POST':
                if not is_token(request.form.get('csrf_token',''),session['settings_csrf']): abort(403)
                submitted=request.form.to_dict()
                try:
                    changes=validated(submitted,form=True)
                    if set(changes)!={'visible_count','font_family','font_size','row_count','layout'}:
                        raise SettingsError('invalid')
                    revision=submitted.get('revision','')
                    if not revision.isascii() or not revision.isdigit(): raise SettingsError('revision')
                    save_settings(db,board,changes,expected_revision=int(revision))
                    return redirect(url_for('display_settings_page',location_id=location_id,saved='1'))
                except SettingsConflict:
                    db.rollback(); status=409
                    error=('Le impostazioni sono state cambiate da un’altra pagina. Ricarica prima di salvare; i tuoi valori sono ancora qui.' if locale=='it'
                           else 'Settings changed in another page. Reload before saving; your draft is still shown.')
                except SettingsError:
                    db.rollback(); status=400
                    error=('Controlla i valori: colonne da 1 a 16, righe da 1 a 3 e carattere da 12 a 36 pixel.' if locale=='it'
                           else 'Check the values: 1–16 columns, 1–3 rows and 12–36 pixel text.')
                values={**values,**{key:submitted[key] for key in values if key in submitted}}
            return render_template('settings.html',location=location,values=values,error=error,
                saved=request.args.get('saved')=='1' and request.method=='GET',csrf=session['settings_csrf']),status

    @app.get('/archive/<int:location_id>')
    @allowed()
    def archive(location_id):
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            abort(400)
        with session_factory() as db:
            _, location = configured(db, location_id)
            tickets = list(db.scalars(select(Ticket).where(Ticket.location_id == location_id,
                Ticket.released_at.is_not(None)).order_by(Ticket.released_at.desc(), Ticket.order_id)
                .offset((page-1)*40).limit(41)))
            categories = categories_by_line(db, location_id, [t.order_id for t in tickets[:40]])
            return render_template('archive.html', location=location, page=page,
                tickets=[serialize(t, location, categories) for t in tickets[:40]], more=len(tickets)>40)

    @app.get('/exit')
    @allowed()
    def exit_board():
        with session_factory() as db:
            locations = list(db.execute(select(Board.location_id, m.Location.name)
                .join(m.Location, m.Location.id == Board.location_id)))
            return render_template('home.html', locations=locations)

    return app
