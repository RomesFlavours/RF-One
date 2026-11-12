"""Explicit loopback-launcher sign-in; never installed by the deployed app."""
from flask import abort, request
from sqlalchemy import select
from rfone_data_store import models as m


def local_admin_preview(account):
    from flask import current_app, has_request_context
    if not has_request_context():
        return False
    return (current_app.config.get('RFONE_LOCAL_OPERATOR') == getattr(account,'username',None)
            and current_app.config.get('RFONE_LOCAL_OPERATOR') is not None
            and request.remote_addr in ('127.0.0.1','::1')
            and getattr(account,'is_admin',False) and getattr(account,'status',None)=='ACTIVE')


def install_local_operator_session(app, *, SessionFactory, load_current_account, log_in, username='rfone'):
    with SessionFactory() as db:
        host = db.get_bind().url.host
        if host not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('Automatic local sign-in requires a loopback database.')
        account = db.scalar(select(m.RFOneAccount).where(
            m.RFOneAccount.username == username, m.RFOneAccount.status == 'ACTIVE'))
        if account is None:
            raise RuntimeError('The existing active local operator was not found.')
        if not account.is_admin:
            raise RuntimeError('Local automatic preview requires the existing administrator.')
    app.config['RFONE_LOCAL_OPERATOR'] = username

    @app.before_request
    def local_operator_session():
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)
        with SessionFactory() as db:
            if load_current_account(db) is not None:
                return None
            account = db.scalar(select(m.RFOneAccount).where(
                m.RFOneAccount.username == username, m.RFOneAccount.status == 'ACTIVE'))
            if account is None:
                abort(403)
            log_in(account.id, account.session_version)
        return None
