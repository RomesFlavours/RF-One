"""The person's page in Training: resend the existing invitation (Product Owner 2026-11-23).

Selection, the Server Course and Invite student start the FIRST invitation. Afterwards the Trainer opens the
person's page — identified by the Registry ID of the person's card — and resends the existing invitation, to the
registered address or to a corrected one. It is always the same invitation, the same card and the same training
path; one active invitation per Registry ID. The new email is sent first: the link already received and the
registered recipient stay valid until the email service accepts it; only then the invitation takes the new link
(and the corrected recipient). After activation the person signs in; the invitation is never reopened.
"""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from rfone_data_store import employee_directory as directory, models as m
from rfone_data_store.technical import account_email
from rfone_data_store.training import enrollment as enroll
from training_account_routes import public_base


def pending_invitations(db):
    """Active invitations with the person's Registry ID, for the Students page (newest first)."""
    rows = []
    for invitation in reversed(enroll.active_invitations_all(db)):
        card = directory.card_for_person(db, invitation.person_id) if invitation.person_id else None
        if card is not None:
            rows.append(dict(employee_id=card.id, name=card.display_name or invitation.name or invitation.email,
                             email=invitation.email, expires_at=invitation.expires_at))
    return rows


def install(app, *, SessionFactory, auth, trainer):
    def deliver(email, link, name):
        try:
            from training_enrollment_routes import invitation_email
            subject, body = invitation_email(name or '', link)
            account_email.send_email(to_address=email, subject=subject, text_body=body)
        except account_email.EmailSendError:
            return False
        return True

    @app.route('/training/manage/people/<int:employee_id>', methods=['GET', 'POST'])
    @trainer
    def tw_person_invitation(employee_id):
        error = None
        with SessionFactory() as db:
            card = db.get(m.Employee, directory.resolve_employee_id(db, employee_id))
            if card is None:
                abort(404)
            employee_id = card.id
            if request.method == 'POST':
                auth.require_csrf()
                actor = auth.load_current_account(db)
                try:
                    prepared = enroll.prepare_resend(db, actor=actor, employee_id=employee_id,
                                                     email=request.form.get('email', ''))
                except ValueError as exc:
                    db.rollback(); error = str(exc)
                else:
                    db.rollback()   # nothing written yet: the email goes first, with no transaction held
                    link = public_base() + url_for('tw_enrollment_link', token=prepared['token'])
                    if not deliver(prepared['email'], link, prepared['name']):
                        error = ('The email could not be sent. Nothing changed: the link already sent to '
                                 f"{prepared['old_email']} still works. Try again in a minute.")
                    else:
                        try:
                            outcome = enroll.complete_resend(db, actor=actor, prepared=prepared)
                            db.commit()
                        except IntegrityError:
                            db.rollback(); outcome = 'changed'
                        if outcome == 'resent':
                            flash(f"Invitation resent to {prepared['email']}. The new link is the one that works.", 'info')
                            return redirect(url_for('tw_person_invitation', employee_id=employee_id))
                        error = ('The invitation was activated meanwhile: the person signs in with username and password.'
                                 if outcome == 'activated' else
                                 'The invitation changed meanwhile. Reload the page and try again.')
            invitations = enroll.invitations_for_card(db, employee_id)
            active = [i for i in invitations if enroll.is_active(i)]
            used = next((i for i in invitations if i.consumed_at), None)
            sites = [site.name for site in directory.sites_of(db, employee_id)]
            return render_template('training_workspace/person_invitation.html', active_tab='students',
                                   help_section='training_person_invitation', card=card, active=active[0] if active else None,
                                   used=used, sites=sites, error=error, draft=request.form), 400 if error else 200
