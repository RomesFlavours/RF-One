from flask import request, redirect, flash
def reject_pending_session(app, factory, auth):
    import training_integration as integration
    from rfone_data_store.training.workspace import TrainingStudentProfile
    with factory() as db:
        account=auth.load_current_account(db)
        if account is None:return None
        link=integration.get_link_for_rfone_account(db, account.id)
        p=db.get(TrainingStudentProfile,link.training_account_id) if link else None
        if p and p.must_change_password and not account.email_verified_at and integration.is_pure_training_student(db,account):
            auth.log_out()
            flash('Activate your account using the personal link sent by email. Ask your trainer to resend it if needed.','error')
            return redirect('/training/activation')
