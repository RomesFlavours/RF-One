"""Explicit additive migration against the single canonical local database."""
from sqlalchemy import text, inspect
from rfone_data_store.training.enrollment import EnrollmentInvitation


def initialize(engine):
    if (engine.url.host, engine.url.port, engine.url.database) != ('127.0.0.1', 55436, 'rfone_aws_copy'):
        raise RuntimeError('Only the canonical local PostgreSQL database is allowed.')
    with engine.begin() as connection:
        connection.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        revisions = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if 't9d120261113' in revisions:
            actual = {c['name'] for c in inspect(connection).get_columns(EnrollmentInvitation.__tablename__)}
            assert actual == set(EnrollmentInvitation.__table__.columns.keys())
            return
        if revisions.count('t9c120261112') != 1:
            raise RuntimeError('Unexpected local revision '+repr(revisions)+'; no changes applied.')
        EnrollmentInvitation.__table__.create(connection, checkfirst=False)
        result=connection.execute(text("UPDATE alembic_version SET version_num='t9d120261113' WHERE version_num='t9c120261112'"))
        assert result.rowcount == 1  # preserve concurrent, unrelated branch heads
    print('PASS: additive local invitation table; no existing identity, credential or permission changed.')
