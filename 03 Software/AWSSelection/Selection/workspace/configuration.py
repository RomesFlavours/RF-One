"""Selection-owned configuration; existing actor and CSRF gates are reused."""
from flask import abort, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from . import role_catalog as roles
from .routes import bp, access_required, _current_job, external_url


def render(db, actor, *, dialog=None, error=None, status=200):
    rows = list(db.scalars(select(roles.JobRole).where(roles.JobRole.active.is_(True)).order_by(func.lower(roles.JobRole.name), roles.JobRole.code)))
    position = _current_job(db, actor)
    public_url = external_url('careers.job_page', token=position.public_token) if position else None
    from . import automations
    from .observation_templates import locations
    return render_template('workspace/configuration.html', actor=actor, role_rows=rows,
        observation_locations=locations(db),
        section='configuration', automation_actions=automations.items(db,'action'), automation_procedures=automations.items(db,'procedure'), dialog=dialog, error=error, current_job=position, public_url=public_url), status


@bp.route('/configurazioni', methods=['GET', 'POST'])
@access_required
def configuration(db, actor):
    if request.method == 'GET':
        return render(db, actor)
    if not actor.is_owner:
        abort(403)
    code = request.form.get('code') or None
    values = {'code': code or '', 'name': request.form.get('name', ''),
              'version': request.form.get('version', '')}
    try:
        role = roles.save(db, code=code, name=values['name'], version=values['version'])
        db.commit()
        return redirect(url_for('.configuration', _anchor='role-' + role.code))
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        error = str(exc) if isinstance(exc, ValueError) else 'Esiste già un ruolo con questo nome. Nessuna modifica salvata.'
        return render(db, actor, dialog=values, error=error, status=422)
