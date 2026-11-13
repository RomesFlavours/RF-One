"""Administrator-only, explicit identity reconciliation; no GET writes."""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m, person_reconciliation as identities


def register_person_reconciliation(app, *, SessionFactory, require_admin, load_current_account, require_csrf):
    @app.route('/admin/registry/identity-reconciliation',methods=['GET','POST'])
    @require_admin
    def registry_identity_reconciliation():
        status=200
        with SessionFactory() as db:
            actor=load_current_account(db)
            if request.method=='POST':
                require_csrf()
                try:
                    action=request.form.get('action')
                    if action not in ('link','create'):abort(400)
                    person=identities.reconcile(db,actor,key=request.form.get('key',''),
                        fingerprint=request.form.get('fingerprint',''),
                        person_id=int(request.form['person_id']) if action=='link' else None,
                        new_name=request.form.get('new_name','') if action=='create' else None)
                    db.commit()
                except (ValueError,KeyError,IntegrityError) as exc:
                    db.rollback();flash('Identity links changed or already exist. Reload and review.' if isinstance(exc,IntegrityError) else str(exc),'error');status=400
                else:
                    flash('Identity links confirmed. Accounts, permissions and learning history were preserved.','info')
                    return redirect(url_for('registry_identity_reconciliation',person_id=person.id))
            report=identities.audit(db)
            persons=list(db.scalars(select(m.CandidatePerson).order_by(m.CandidatePerson.full_name,m.CandidatePerson.id)))
            return render_template('registry_identity_reconciliation.html',report=report,persons=persons,selected_person_id=request.args.get('person_id',type=int)),status
