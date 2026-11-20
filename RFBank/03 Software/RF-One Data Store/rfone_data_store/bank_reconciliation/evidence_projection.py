"""Transactional, batched deltas for the three derived support-evidence tables."""
from sqlalchemy import text


def begin_projection(db):
    """Keep source reads and derived writes in one serialized SQLite transaction.

    The old DELETE acquired the writer reservation before reading reports. Take
    that reservation without deleting unchanged rows, including on startup when
    the caller has not already flushed an upload. The caller still owns commit.
    """
    if db.get_bind().dialect.name == 'sqlite':
        connection = db.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')


def sync_rows(db, table, rows, keys):
    # Identifiers are code-owned, never a source value or user query.
    if table not in {'bank_amazon_items', 'bank_paypal_observations', 'bank_paypal_transactions'}:
        raise ValueError('Unknown evidence projection')
    old = {tuple(row[k] for k in keys): dict(row) for row in
           db.execute(text('SELECT * FROM ' + table)).mappings()}
    columns = list(rows[0]) if rows else []
    insert, update = [], []
    for row in rows:
        key = tuple(row[k] for k in keys)
        previous = old.pop(key, None)
        if previous is None:
            insert.append(row)
        elif previous != row:
            update.append(dict(row, **{'_key_' + k: row[k] for k in keys}))
    if old:
        db.execute(text('DELETE FROM ' + table + ' WHERE ' + ' AND '.join(
            k + '=:_key_' + k for k in keys)), [{'_key_' + k: v for k, v in zip(keys, key)} for key in old])
    if update:
        db.execute(text('UPDATE ' + table + ' SET ' + ','.join(k+'=:'+k for k in columns if k not in keys)
            + ' WHERE ' + ' AND '.join(k+'=:_key_'+k for k in keys)), update)
    if insert:
        db.execute(text('INSERT INTO ' + table + ' ('+','.join(columns)+') VALUES ('
            + ','.join(':'+k for k in columns)+')'), insert)
