"""Validated Registry return targets; never accept an arbitrary redirect URL."""
from flask import abort, request, url_for
from rfone_data_store import employee_directory as directory


def account_return(db, account):
    person_id = directory.context_person_id(db, 'RFONE_ACCOUNT', account.id)
    target = f'employee:{person_id}' if person_id is not None else f'account:{account.id}'
    supplied = request.values.get('from_person', '')
    if supplied:
        try:
            kind, raw = supplied.split(':')
            identity = int(raw)
        except (ValueError, AttributeError):
            abort(400)
        if kind == 'account':
            if identity != account.id: abort(400)
        elif kind == 'employee':
            if person_id is None or directory.resolve_employee_id(db, identity) != person_id: abort(400)
        else:
            abort(400)
    return target, url_for('role_profiles_home', tab='people', person=target, _anchor='people-table')
