"""Local Training workspace; installed only by training_local.py."""
import secrets
from functools import wraps
from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash
from rfone_data_store import models as m, rfone_account_service as accounts
from rfone_data_store.training import service, workspace as ws
from rfone_data_store.training import courses
import training_integration as integration
from rfone_data_store import student_registry as registry
from training_account_routes import invite, pending_link_activation


def install(app, *, SessionFactory, auth):
    from training_account_routes import install as install_account_routes
    install_account_routes(app, SessionFactory=SessionFactory, auth=auth)

    def trainer(view):
        @wraps(view)
        def wrapped(*args,**kwargs):
            with SessionFactory() as db:
                account=auth.load_current_account(db)
                if account is None:
                    return redirect(url_for('tw_login'))
                result=integration.check_training_authorization(db,account)
                if result.training_account is None or result.training_account.role!='trainer':
                    abort(403)
            return view(*args,**kwargs)
        return wrapped

    def trainer_id(db):
        result=integration.check_training_authorization(db,auth.load_current_account(db))
        if not result.training_account or result.training_account.role!='trainer': abort(403)
        return result.training_account.id

    from training_course_routes import register
    register(app,SessionFactory=SessionFactory,auth=auth,trainer=trainer)
    from training_enrollment_routes import install as install_enrollment
    install_enrollment(app,SessionFactory=SessionFactory,auth=auth,trainer=trainer)

    def render(page,**context):
        return render_template('training_workspace/'+page+'.html',active_tab=page,
            help_section='training_'+page,**context)

    @app.before_request
    def first_access_gate():
        if request.endpoint in ('tw_login','tw_password','tw_logout','tw_account','tw_activation_link','tw_activation','tw_enrollment_link','tw_enrollment_activation','static','shared_brand_logo'):
            return None
        with SessionFactory() as db:
            account=auth.load_current_account(db)
            if account:
                link=integration.get_link_for_rfone_account(db,account.id)
                p=db.get(ws.TrainingStudentProfile,link.training_account_id) if link else None
                if p and p.archived_at and request.path.startswith(('/training','/visual-menu')):
                    auth.log_out()
                    return redirect(url_for('tw_login'))
                if p and p.must_change_password and pending_link_activation(db,account):
                    # Initial credentials alone never open MyRF or a module.
                    auth.log_out()
                    flash(ACTIVATE_FIRST,'error')
                    return redirect(url_for('tw_login'))
                if p and p.must_change_password:
                    return redirect(url_for('tw_password'))

    @app.route('/training/manage/students',methods=['GET','POST'])
    @trainer
    def tw_students():
        error=None; status=200; matches=[]
        session.setdefault('tw_submission',secrets.token_urlsafe(32))
        if request.method=='POST':
            auth.require_csrf()
            with SessionFactory() as db:
                try:
                    action=request.form.get('action')
                    if action=='invite':
                        account=ws.linked_account(db,int(request.form['id']))
                        training=db.get(m.TrainingAccount,int(request.form['id']))
                        if not account or not training or training.role!='student':raise ValueError('Studente non disponibile.')
                        sent=invite(db,account)
                        flash('Invito inviato.' if sent else 'Invito non consegnato. Account conservato: riprova con Reinvia invito.','info' if sent else 'error')
                    elif action in ('archive','restore'):
                        ws.archive_student(db,int(request.form['id']),action=='archive')
                    elif action=='save':
                        password=request.form.get('password','')
                        if password!=request.form.get('password_confirm',''):
                            raise ValueError('Le password non coincidono.')
                        key=request.form.get('id','')
                        if not key:
                            if len(request.form.get('phone','').strip())>80:raise ValueError('Telefono troppo lungo (massimo 80 caratteri).')
                            first,last=request.form.get('first_name','').strip(),request.form.get('last_name','').strip()
                            if not first or not last:raise ValueError('Inserisci nome e cognome.')
                            username=integration.generate_username(db,first,last)
                            initial=integration.generate_initial_password()
                            rf_account,account=integration.create_student_via_rf_one(db,
                                username=username,display_name=f'{first} {last}',
                                password=initial,email=request.form.get('email',''),confirmation=request.form.get('confirmation'))
                            # The generated username was free, so equality means a new login.
                            # A confirmed existing login keeps its username and credentials.
                            created=rf_account.username==username.lower()
                            key=account.id
                            p=ws.profile(db,key)
                            p.phone=request.form.get('phone','').strip()
                            db.commit()
                            sent=invite(db,rf_account,initial_password=initial if created else None,
                                display_username=username if created else None)
                            reissued=not created and pending_link_activation(db,rf_account)
                            assigned=(f'Nome utente assegnato: {username}. ' if created else
                                      f'Studente già registrato e mai attivato ({rf_account.username}): nuova password iniziale e nuovo collegamento. ' if reissued else
                                      f'Account esistente collegato: nome utente {rf_account.username}, credenziali invariate. ')
                            flash(assigned+('Invito inviato.' if sent else 'Invito non consegnato. Account conservato: riprova con Reinvia invito.'),'info' if sent else 'error')
                            action='created'  # the creation message above is the only one
                        else:
                            ws.save_student(db,int(key),name=request.form.get('name',''),username=request.form.get('username',''),
                            email=request.form.get('email',''),phone=request.form.get('phone',''),password=password)
                    else:
                        abort(400)
                    db.commit()
                except (ValueError,IntegrityError) as exc:
                    db.rollback();error=localized_error(exc);status=400
                    if isinstance(exc,registry.ConfirmationRequired):matches=exc.candidates
                else:
                    if action not in ('created','invite'):flash('Studente archiviato. Lo storico è conservato.' if action=='archive' else
                          'Studente ripristinato.' if action=='restore' else 'Dati dello studente salvati.','info')
                    return redirect(url_for('tw_students',archived=request.args.get('archived'),q=request.args.get('q','')))
        with SessionFactory() as db:
            q=request.args.get('q','').strip().lower();archived=request.args.get('archived')=='1'
            rows=[r for r in ws.roster(db) if r['archived']==archived
                  and (not q or q in (r['name']+' '+r['username']+' '+(r['email'] or '')).lower())]
            return render('students',students=rows,archived=archived,q=request.args.get('q',''),error=error,
                          draft=request.form if error and request.form.get('action')=='save' else None,
                          matches=matches,pills=service.list_all_pills(db),submission=session['tw_submission']),status

    @app.route('/training/manage/content')
    @trainer
    def tw_content():
        with SessionFactory() as db:
            q=request.args.get('q','').strip().lower()
            rows=[row for row in courses.catalog(db) if q in (row['title']+' '+row['objective']).lower()]
            return render('content',course_rows=rows,q=request.args.get('q',''),error=None,course_draft=None)

    @app.get('/training/manage')
    @trainer
    def tw_assignments():
        return redirect(url_for('tw_students'))

    @app.post('/training/manage/students/<int:student_id>/assign')
    @trainer
    def tw_assign_student(student_id):
        auth.require_csrf()
        expected=session.get('tw_submission','')
        submitted=request.form.get('submission','')
        if not expected or not submitted or not secrets.compare_digest(expected,submitted):
            return jsonify(error='Questa assegnazione è già stata confermata. Riapri l’elenco studenti.'),400
        with SessionFactory() as db:
            try:
                count=ws.assign(db,trainer_id=trainer_id(db),recipients=[f'student:{student_id}'],
                    pill_ids=[int(value) for value in request.form.getlist('pills')],
                    purpose='Assegnazione di contenuti Training',token=submitted)
                db.commit()
            except (ValueError,IntegrityError) as exc:
                db.rollback()
                message=localized_error(exc)
                if str(exc).startswith('invalid literal'):message='Contenuto selezionato non valido.'
                return jsonify(error=message),400
        session.pop('tw_submission',None)
        flash(f'Assegnazione completata: {count} contenuti assegnati allo studente.','info')
        if request.accept_mimetypes.best=='application/json':return jsonify(saved=True)
        return redirect(url_for('tw_students',q=request.form.get('return_q') or None))

    @app.route('/training/access',methods=['GET','POST'])
    def tw_login():
        error=None
        if request.method=='POST':
            auth.require_csrf()
            with SessionFactory() as db:
                result=accounts.verify_login(db,username=request.form.get('username',''),password=request.form.get('password',''))
                db.commit()
                account=result.account
                if account and pending_link_activation(db,account):
                    return render('login',error=ACTIVATE_FIRST),400
                if account:
                    authorization=integration.check_training_authorization(db,account)
                    if authorization.training_account:
                        auth.log_in(account.id,account.session_version)
                        session['tw_student_session']=authorization.training_account.role=='student'
                        return redirect(url_for('tw_password' if authorization.training_account.role=='student' else 'tw_students'))
                error='Nome utente o password non validi, oppure accesso Training non disponibile.'
        return render('login',error=error),400 if error else 200

    @app.route('/training/first-access',methods=['GET','POST'])
    def tw_password():
        error=None
        with SessionFactory() as db:
            account=auth.load_current_account(db)
            if not account:return redirect(url_for('tw_login'))
            link=integration.get_link_for_rfone_account(db,account.id)
            p=db.get(ws.TrainingStudentProfile,link.training_account_id) if link else None
            if not p or not p.must_change_password:return redirect(url_for('training.home'))
            if request.method=='POST':
                auth.require_csrf()
                password=request.form.get('password','')
                if len(password)<8:error='La nuova password deve contenere almeno 8 caratteri.'
                elif password!=request.form.get('password_confirm',''):error='Le password non coincidono.'
                elif check_password_hash(account.password_hash,password):error='Scegli una password diversa da quella iniziale.'
                if not error:
                    try:
                        ws.save_student(db,p.training_account_id,name=account.display_name,
                            username=request.form.get('username',account.username),email=account.email or '',
                            phone=p.phone,password=password)
                    except (ValueError,IntegrityError) as exc:
                        db.rollback();error=localized_error(exc)
                    else:
                        p.must_change_password=False
                        db.commit();auth.log_in(account.id,account.session_version)
                        session['tw_student_session']=True
                        return redirect(url_for('training.home'))
            username=account.username
        return render('password',error=error,username=username),400 if error else 200

    @app.post('/training/access/logout')
    def tw_logout():
        auth.require_csrf();auth.log_out()
        session['tw_student_session']=True
        return redirect(url_for('tw_login'))


ACTIVATE_FIRST=('Account non ancora attivato: apri il collegamento personale ricevuto via email e inserisci '
                'nome utente e password iniziale. Se il collegamento è scaduto chiedi all’istruttore di reinviare l’invito.')


def localized_error(exc):
    message=str(exc)
    if isinstance(exc,IntegrityError):return 'Il record è già presente o è stato aggiornato. Ricarica e riprova.'
    if 'email address is already' in message:return 'Questo indirizzo email è già utilizzato.'
    if 'already' in message and ('sername' in message or 'sername' in message.lower()):return 'Nome utente già utilizzato.'
    if message.startswith(('A valid email','email is required')):return 'Inserisci un indirizzo email valido.'
    if message.startswith(('username','display_name','password')):return 'Compila nome, nome utente e password.'
    return message
