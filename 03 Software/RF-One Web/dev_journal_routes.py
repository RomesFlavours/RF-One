"""RF-One Web — Development Journal.

A system-level service (`10 System/Development Journal/README.md`), not a
business Domain. Every route below — pages AND documents — is gated by
`require_domain_access("DEV_JOURNAL")`: the Home link is never the access
control. Every POST also checks the CSRF token.

  * `/dev-journal`                              — list with filters, "New work";
  * `/dev-journal/new`                          — create a card;
  * `/dev-journal/<id>`                         — the card: next step, journal,
                                                  documents, phase/status history;
  * `/dev-journal/<id>/edit`, `/reopen`         — change / reopen the card;
  * `/dev-journal/<id>/entries`                 — add an entry (with files);
  * `/dev-journal/<id>/entries/<e>/edit`        — the author, or a Development
                                                  Journal administrator, corrects an entry;
  * `/dev-journal/<id>/entries/<e>/versions`    — every version of an entry;
  * `/dev-journal/<id>/documents`               — upload to the card or an entry;
  * `/dev-journal/<id>/documents/<doc>`         — open or download, never public.

All rules live in `rfone_data_store.dev_journal.service`; this module only
reads requests and renders. Nothing here talks to Git, Claude, Codex or AWS
except the private document bucket, when one is configured.

Registered from `app.py` via `register_dev_journal_routes(app, ...)`,
passing collaborators in explicitly like the other route modules here."""

from __future__ import annotations

import os
from urllib.parse import quote

from flask import Response, abort, flash, redirect, render_template, request, url_for

from domain_registry import DOMAINS
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.dev_journal import document_store
from rfone_data_store.dev_journal import models as dj
from rfone_data_store.dev_journal import service as svc

DOMAIN_CODE = svc.ACCESS_CODE
# Generous whole-request ceiling for one form with several files; each file
# is still checked against MAX_DOCUMENT_BYTES on its own.
_MAX_FILES_PER_REQUEST = 10
_MAX_REQUEST_BYTES = svc.MAX_DOCUMENT_BYTES * _MAX_FILES_PER_REQUEST + 1024 * 1024

# How the store is built; tests replace it with their own.
store_factory = document_store.from_environment


def domain_options() -> list[tuple[str, str]]:
    """"General / System" first, then every RF-One access code except the
    journal itself, by name."""
    others = sorted(((d.code, d.display_name) for d in DOMAINS if d.code != DOMAIN_CODE),
                    key=lambda item: item[1].casefold())
    return [(svc.GENERAL_DOMAIN_CODE, svc.GENERAL_DOMAIN_LABEL), *others]


def _int_or_none(raw: str | None) -> int | None:
    try:
        return int(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def _work_input(form) -> svc.WorkInput:
    return svc.WorkInput(
        title=form.get("title"), domain_code=form.get("domain_code"), objective=form.get("objective"),
        responsible_account_id=_int_or_none(form.get("responsible_account_id")),
        phase=form.get("phase"), status=form.get("status"), next_step=form.get("next_step"),
    )


def _entry_input(form) -> svc.EntryInput:
    return svc.EntryInput(**{name: form.get(name) for name in svc.EntryInput.__dataclass_fields__})


def _entry_form(entry) -> dict:
    return {name: getattr(entry, name) or "" for name in dj.ENTRY_CONTENT_FIELDS}


def _read_files(files) -> list[svc.CheckedDocument]:
    """Every chosen file, checked before anything is stored."""
    chosen = [f for f in files if f and f.filename]
    if len(chosen) > _MAX_FILES_PER_REQUEST:
        raise svc.DevJournalError(f"At most {_MAX_FILES_PER_REQUEST} files at a time.")
    return [svc.check_document(f.filename, f.read(svc.MAX_DOCUMENT_BYTES + 1)) for f in chosen]


def _document_store():
    try:
        return store_factory()
    except document_store.StorageNotConfiguredError:
        raise svc.DevJournalError(
            "Document storage is not configured on this server, so documents cannot be uploaded. "
            "Nothing was saved; please tell an administrator."
        ) from None


def _store_documents(db, work, documents, *, actor_id, entry=None) -> None:
    if not documents:
        return
    store = _document_store()
    stored: list[str] = []
    try:
        for document in documents:
            row = svc.add_document(db, work, document, store, actor_id=actor_id, entry=entry)
            stored.append(row.storage_path)
    except Exception:
        for path in stored:
            store.discard(path)
        raise


def register_dev_journal_routes(app, *, require_domain_access, SessionFactory, load_current_account, require_csrf):
    gate = require_domain_access(DOMAIN_CODE)

    def _guard_request_size() -> None:
        if request.content_length is not None and request.content_length > _MAX_REQUEST_BYTES:
            abort(413)

    def _names(db) -> dict[int, str]:
        return {a.id: a.display_name or a.username for a in account_service.list_accounts(db)}

    def _responsible_options(db, current_id: int | None = None) -> list:
        options = [(a.id, a.display_name or a.username) for a in svc.journal_accounts(db)]
        if current_id is not None and current_id not in {i for i, _ in options}:
            current = account_service.get_account(db, current_id)
            if current is not None:
                options.append((current.id, f"{current.display_name or current.username} (no longer enabled)"))
        return options

    def _labels() -> dict:
        return {
            "domain_labels": dict(domain_options()), "phase_labels": svc.PHASE_LABELS,
            "status_labels": svc.STATUS_LABELS, "entry_type_labels": svc.ENTRY_TYPE_LABELS,
            "environment_labels": svc.RELEASE_ENVIRONMENT_LABELS, "outcome_labels": svc.RELEASE_OUTCOME_LABELS,
            "event_labels": svc.EVENT_TYPE_LABELS, "closed_statuses": svc.CLOSED_STATUSES,
            "human_size": svc.human_size, "max_document_mb": svc.MAX_DOCUMENT_BYTES // (1024 * 1024),
        }

    def _is_admin(db, account) -> bool:
        # ADMIN_PERMISSIONS_001 — an RF-One administrator, or the Domain
        # administrator role on DEV_JOURNAL, may correct anyone's entry.
        return shared_session.account_is_domain_admin(db, account, DOMAIN_CODE)

    def _work_or_404(db, work_id: int):
        work = svc.get_work(db, work_id)
        if work is None:
            abort(404)
        return work

    def _entry_or_404(db, work_id: int, entry_id: int):
        entry = svc.get_entry(db, work_id, entry_id)
        if entry is None:
            abort(404)
        return entry

    # -----------------------------------------------------------------
    # List
    # -----------------------------------------------------------------

    @app.route("/dev-journal")
    @gate
    def dev_journal_list():
        filters = svc.WorkFilters(
            domain_code=request.args.get("domain") or None,
            phase=request.args.get("phase") or None,
            status=request.args.get("status") or None,
            responsible_account_id=_int_or_none(request.args.get("responsible")),
        )
        with SessionFactory() as db:
            works = svc.list_works(db, filters)
            names = _names(db)
            responsible_ids = {w.responsible_account_id for w in svc.list_works(db, svc.WorkFilters())}
            responsible_filter = sorted(
                {(a.id, a.display_name or a.username) for a in svc.journal_accounts(db)}
                | {(i, names.get(i, f"#{i}")) for i in responsible_ids},
                key=lambda item: item[1].casefold(),
            )
            return render_template(
                "dev_journal_list.html", works=works, names=names, filters=filters,
                domain_choices=domain_options(), responsible_filter=responsible_filter, **_labels(),
            )

    # -----------------------------------------------------------------
    # Create / edit / reopen
    # -----------------------------------------------------------------

    @app.route("/dev-journal/new", methods=["GET", "POST"])
    @gate
    def dev_journal_new():
        with SessionFactory() as db:
            account = load_current_account(db)
            form = request.form if request.method == "POST" else {
                "phase": "STUDY", "status": "IN_PROGRESS", "responsible_account_id": str(account.id),
            }
            if request.method == "POST":
                require_csrf()
                try:
                    work = svc.create_work(db, _work_input(request.form), actor_id=account.id,
                                           domain_codes=dict(domain_options()))
                    db.commit()
                except svc.DevJournalError as exc:
                    db.rollback()
                    flash(str(exc), "error")
                else:
                    flash("Work created.", "info")
                    return redirect(url_for("dev_journal_work", work_id=work.id))
            return render_template(
                "dev_journal_work_form.html", mode="create", work=None, form=form,
                domain_choices=domain_options(), responsible_options=_responsible_options(db), **_labels(),
            ), (400 if request.method == "POST" else 200)

    @app.route("/dev-journal/<int:work_id>/edit", methods=["GET", "POST"])
    @gate
    def dev_journal_edit(work_id: int):
        with SessionFactory() as db:
            account = load_current_account(db)
            work = _work_or_404(db, work_id)
            form = request.form if request.method == "POST" else {
                "title": work.title, "domain_code": work.domain_code, "objective": work.objective,
                "responsible_account_id": str(work.responsible_account_id), "phase": work.phase,
                "status": work.status, "next_step": work.next_step or "",
            }
            if request.method == "POST":
                require_csrf()
                try:
                    svc.update_work(db, work, _work_input(request.form), actor_id=account.id,
                                    domain_codes=dict(domain_options()))
                    db.commit()
                except svc.DevJournalError as exc:
                    db.rollback()
                    flash(str(exc), "error")
                else:
                    flash("Work updated.", "info")
                    return redirect(url_for("dev_journal_work", work_id=work.id))
            return render_template(
                "dev_journal_work_form.html", mode="edit", work=work, form=form,
                domain_choices=domain_options(),
                responsible_options=_responsible_options(db, work.responsible_account_id), **_labels(),
            ), (400 if request.method == "POST" else 200)

    @app.route("/dev-journal/<int:work_id>/reopen", methods=["POST"])
    @gate
    def dev_journal_reopen(work_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            work = _work_or_404(db, work_id)
            try:
                svc.reopen_work(db, work, actor_id=account.id)
                db.commit()
                flash("Work reopened: status “In progress”.", "info")
            except svc.DevJournalError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("dev_journal_work", work_id=work_id))

    # -----------------------------------------------------------------
    # The card
    # -----------------------------------------------------------------

    def _render_work(db, work, *, entry_form=None, status: int = 200):
        account = load_current_account(db)
        entries = svc.list_entries(db, work.id)
        documents = svc.list_documents(db, work.id)
        docs_by_entry: dict[int, list] = {}
        for doc in documents:
            if doc.entry_id is not None:
                docs_by_entry.setdefault(doc.entry_id, []).append(doc)
        return render_template(
            "dev_journal_work.html", work=work, entries=entries, current_account_id=account.id,
            correctable_entry_ids={e.id for e in entries if svc.may_correct_entry(
                e, actor_id=account.id, actor_is_admin=_is_admin(db, account))},
            work_documents=[d for d in documents if d.entry_id is None], docs_by_entry=docs_by_entry,
            changes=svc.list_changes(db, work.id), events=svc.list_events(db, work.id), names=_names(db),
            entry_form=entry_form or {"phase": work.phase, "entry_type": "ACTIVITY"}, **_labels(),
        ), status

    @app.route("/dev-journal/<int:work_id>")
    @gate
    def dev_journal_work(work_id: int):
        with SessionFactory() as db:
            return _render_work(db, _work_or_404(db, work_id))

    @app.route("/dev-journal/<int:work_id>/entries", methods=["POST"])
    @gate
    def dev_journal_add_entry(work_id: int):
        _guard_request_size()
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            work = _work_or_404(db, work_id)
            data = _entry_input(request.form)
            try:
                svc.validate_entry(data)
                documents = _read_files(request.files.getlist("files"))
                if documents:
                    _document_store()  # refuse before writing anything when storage is missing
                entry = svc.add_entry(db, work, data, actor_id=account.id)
                _store_documents(db, work, documents, actor_id=account.id, entry=entry)
                db.commit()
            except svc.DevJournalError as exc:
                db.rollback()
                flash(f"Entry not saved: {exc}", "error")
                return _render_work(db, work, entry_form=request.form, status=400)
            flash("Entry added." + (f" {len(documents)} document(s) attached." if documents else ""), "info")
            return redirect(url_for("dev_journal_work", work_id=work_id, _anchor=f"entry-{entry.id}"))

    # -----------------------------------------------------------------
    # Correcting an entry (its author or an administrator) and its versions
    # -----------------------------------------------------------------

    @app.route("/dev-journal/<int:work_id>/entries/<int:entry_id>/edit", methods=["GET", "POST"])
    @gate
    def dev_journal_edit_entry(work_id: int, entry_id: int):
        with SessionFactory() as db:
            account = load_current_account(db)
            work = _work_or_404(db, work_id)
            entry = _entry_or_404(db, work_id, entry_id)
            is_admin = _is_admin(db, account)
            if not svc.may_correct_entry(entry, actor_id=account.id, actor_is_admin=is_admin):
                abort(403)
            form = request.form if request.method == "POST" else _entry_form(entry)
            if request.method == "POST":
                require_csrf()
                try:
                    kept = svc.edit_entry(db, work, entry, _entry_input(request.form), actor_id=account.id,
                                          actor_is_admin=is_admin)
                    db.commit()
                except svc.DevJournalError as exc:
                    db.rollback()
                    flash(f"Correction not saved: {exc}", "error")
                else:
                    flash("Entry corrected; the previous version is kept." if kept else "Nothing changed.", "info")
                    return redirect(url_for("dev_journal_work", work_id=work_id, _anchor=f"entry-{entry_id}"))
            return render_template(
                "dev_journal_entry_form.html", work=work, entry=entry, form=form,
                author_name=None if entry.author_account_id == account.id
                else _names(db).get(entry.author_account_id, f"#{entry.author_account_id}"),
                **_labels(),
            ), (400 if request.method == "POST" else 200)

    @app.route("/dev-journal/<int:work_id>/entries/<int:entry_id>/versions")
    @gate
    def dev_journal_entry_versions(work_id: int, entry_id: int):
        with SessionFactory() as db:
            work = _work_or_404(db, work_id)
            entry = _entry_or_404(db, work_id, entry_id)
            return render_template(
                "dev_journal_entry_versions.html", work=work, entry=entry,
                versions=list(reversed(svc.list_entry_versions(db, entry.id))), names=_names(db), **_labels(),
            )

    # -----------------------------------------------------------------
    # Documents
    # -----------------------------------------------------------------

    @app.route("/dev-journal/<int:work_id>/documents", methods=["POST"])
    @gate
    def dev_journal_upload(work_id: int):
        _guard_request_size()
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            work = _work_or_404(db, work_id)
            entry = None
            entry_id = _int_or_none(request.form.get("entry_id"))
            if entry_id is not None:
                entry = _entry_or_404(db, work_id, entry_id)
            try:
                documents = _read_files(request.files.getlist("files"))
                if not documents:
                    raise svc.DevJournalError("Choose at least one file.")
                _store_documents(db, work, documents, actor_id=account.id, entry=entry)
                db.commit()
            except svc.DevJournalError as exc:
                db.rollback()
                flash(f"Upload failed: {exc}", "error")
            else:
                flash(f"{len(documents)} document(s) uploaded.", "info")
        anchor = f"entry-{entry_id}" if entry_id is not None else "documents"
        return redirect(url_for("dev_journal_work", work_id=work_id, _anchor=anchor))

    @app.route("/dev-journal/<int:work_id>/documents/<int:document_id>")
    @gate
    def dev_journal_document(work_id: int, document_id: int):
        with SessionFactory() as db:
            document = next((d for d in svc.list_documents(db, work_id) if d.id == document_id), None)
            if document is None:
                abort(404)
            try:
                data = store_factory().read(document.storage_path)
            except document_store.StorageNotConfiguredError:
                abort(503, description="Document storage is not configured on this server.")
            if data is None:
                abort(404)
            extension = os.path.splitext(document.original_filename)[1].lower()
            inline = extension in svc.INLINE_EXTENSIONS and request.args.get("download") != "1"
            # Markdown opens as plain text: shown, never rendered as a page.
            content_type = "text/plain; charset=utf-8" if inline and extension == ".md" else document.content_type
            name = document.original_filename
            ascii_name = name.encode("ascii", "replace").decode("ascii").replace("?", "_")
            disposition = (f"{'inline' if inline else 'attachment'}; filename=\"{ascii_name}\"; "
                           f"filename*=UTF-8''{quote(name)}")
            response = Response(data, content_type=content_type)
            response.headers["Content-Disposition"] = disposition
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "private, no-store"
            return response
