"""One administrative directory for employees and external people."""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import inspect, or_, select
from sqlalchemy.exc import IntegrityError

from auth import load_current_account
from rfone_data_store import models as m
from rfone_data_store import people_registry as people
from rfone_data_store.interviews import service as interviews
from rfone_data_store.interviews.models import InterviewSession


def register_people_routes(app, *, SessionFactory, require_admin, require_csrf):
    def error_message(value):
        message = str(value)
        if not app.config.get('RFONE_LOCAL_OPERATOR'):
            return message
        return {
            'Invalid company status.': 'Status aziendale non valido.',
            'Person not found.': 'Persona non trovata.',
            'Company status migration is required.': 'Lo status aziendale non è ancora disponibile.',
            'Enter a name within 255 characters and valid contact lengths.': 'Inserisci un nome entro 255 caratteri e contatti di lunghezza valida.',
            'Enter a valid email address or leave it blank.': 'Inserisci un indirizzo email valido oppure lascia il campo vuoto.',
            'Possible existing person. Open the existing record and verify the identity before creating another.': 'Possibile persona già presente: apri la scheda esistente e verifica l’identità prima di crearne un’altra.',
            'Source record not found.': 'Record di origine non trovato.',
            'Select the existing person to link.': 'Seleziona la persona esistente da collegare.',
            'Invalid operation.': 'Operazione non valida.',
            'Reload the record and try again.': 'Ricarica la scheda e riprova.',
            'This record was linked by another request. Reload the directory.': 'Il record è stato collegato da un’altra richiesta. Ricarica l’anagrafica.',
            'This person already has a linked RF-One account.': 'Questa persona ha già un account RF-One collegato.',
            'This record is already linked to another person. No identity was changed.': 'Il record è già collegato a un’altra persona. Nessuna identità modificata.',
            'Invalid source record.': 'Record di origine non valido.',
        }.get(message, message)

    @app.context_processor
    def people_help_language():
        if request.endpoint not in {'people_home', 'person_detail'}:
            return {}
        labels = {'How this page works': 'Come funziona questa pagina', 'Close': 'Chiudi'}
        return {'ui': lambda value: labels.get(value, value) if app.config.get('RFONE_LOCAL_OPERATOR') else value}

    def ready(db):
        if not people.available(db):
            abort(503, description="The people directory is not available yet. Please contact your administrator.")

    @app.route("/people", methods=["GET", "POST"])
    @require_admin
    def people_home():
        with SessionFactory() as db:
            ready(db)
            actor = load_current_account(db)
            if request.method == "POST":
                require_csrf()
                try:
                    action = request.form.get("action")
                    if action == "create":
                        person = people.create_person(db, actor, request.form.get("full_name", ""),
                            request.form.get("email", ""), request.form.get("phone", ""),
                            company_codes=request.form.getlist('company_status'))
                    elif action in {"link", "create_from_source"}:
                        kind, source_id = request.form.get("source", "").split(":", 1)
                        source_id = int(source_id)
                        if action == "create_from_source":
                            source = db.get(m.RFOneAccount if kind == "account" else m.Employee, source_id)
                            if source is None or kind not in {"account", "employee"}:
                                raise ValueError("Source record not found.")
                            if db.scalar(select(m.CandidatePerson.id).where(m.CandidatePerson.normalized_name == ' '.join((source.display_name or '').casefold().split())).limit(1)):
                                raise ValueError('Possible existing person. Open the existing record and verify the identity before creating another.')
                            person = people.create_person(db, actor, source.display_name or "")
                        else:
                            person = db.get(m.CandidatePerson, int(request.form.get("person_id", "0")))
                            if person is None:
                                raise ValueError("Select the existing person to link.")
                        people.link_source(db, actor, person.id, kind, source_id)
                    else:
                        raise ValueError("Invalid operation.")
                    db.commit()
                    return redirect(url_for("person_detail", person_id=person.id))
                except PermissionError:
                    abort(403)
                except (ValueError, IntegrityError) as exc:
                    db.rollback()
                    flash(error_message(exc if isinstance(exc, ValueError) else "This record was linked by another request. Reload the directory."), "error")
            data = people.directory(db)
            query = request.args.get("q", "").strip().casefold()
            if query:
                data["people"] = [p for p in data["people"] if query in " ".join(filter(None, [p.full_name, p.primary_email])).casefold()]
                data["unlinked_accounts"] = [a for a in data["unlinked_accounts"] if query in (a.display_name + " " + a.username).casefold()]
                data["unlinked_employees"] = [e for e in data["unlinked_employees"] if query in (e.display_name or "").casefold()]
            # Link choices must include every existing person even while filtering.
            choices = list(db.scalars(select(m.CandidatePerson).order_by(m.CandidatePerson.full_name)))
            return render_template("people.html", **data, choices=choices, query=request.args.get("q", ""),
                draft=request.form, company_codes=people.COMPANY_STATUSES,
                company_statuses={p.id: people.company_statuses(db, p.id) for p in data['people']},
                company_status_ready=inspect(db.connection()).has_table('person_company_statuses'))

    @app.route("/people/<int:person_id>", methods=['GET', 'POST'])
    @require_admin
    def person_detail(person_id):
        with SessionFactory() as db:
            ready(db)
            person = db.get(m.CandidatePerson, person_id)
            if person is None:
                abort(404)
            if request.method == 'POST':
                require_csrf()
                try:
                    people.set_company_statuses(db, load_current_account(db), person_id, request.form.getlist('company_status'))
                    db.commit()
                    return redirect(url_for('person_detail', person_id=person_id))
                except (ValueError, IntegrityError) as exc:
                    db.rollback()
                    flash(error_message(exc if isinstance(exc, ValueError) else 'Reload the record and try again.'), 'error')
            link = db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.person_id == person.id))
            account = db.get(m.RFOneAccount, link.account_id) if link else None
            employees = list(db.scalars(select(m.Employee).join(people.PersonEmployeeLink,
                people.PersonEmployeeLink.employee_id == m.Employee.id).where(people.PersonEmployeeLink.person_id == person.id)))
            rows = []
            interview_ready = interviews.available(db)
            if interview_ready:
                condition = InterviewSession.person_id == person.id
                if account:
                    condition = or_(condition, (InterviewSession.person_id.is_(None)) & (InterviewSession.recipient_id == account.id))
                rows = list(db.scalars(select(InterviewSession).where(condition,
                    InterviewSession.requester_id == load_current_account(db).id).order_by(InterviewSession.created_at.desc())))
            return render_template("person_detail.html", person=person, linked_account=account,
                employee_records=employees, interviews=rows, interviews_ready=interview_ready,
                company_codes=people.COMPANY_STATUSES, company_statuses=people.company_statuses(db, person_id),
                company_status_ready=inspect(db.connection()).has_table('person_company_statuses'))

    @app.after_request
    def people_private_pages(response):
        if request.endpoint in {"people_home", "person_detail"}:
            response.headers["Cache-Control"] = "no-store"
        return response
