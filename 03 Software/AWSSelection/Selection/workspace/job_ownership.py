"""Cross-process PostgreSQL session ownership; crash releases the lock automatically."""
from contextlib import contextmanager
from sqlalchemy import text


@contextmanager
def own_reader(factory, position_id):
    with factory() as session:engine=session.get_bind()
    if engine.dialect.name!='postgresql':
        # Desktop SQLite uses the existing process-local dispatch lock.
        yield True
        return
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        owned=connection.scalar(text('SELECT pg_try_advisory_lock(187041, :position)'),{'position':position_id})
        try:yield bool(owned)
        finally:
            if owned:
                try:connection.execute(text('SELECT pg_advisory_unlock(187041, :position)'),{'position':position_id})
                except BaseException:
                    connection.invalidate()
                    raise
