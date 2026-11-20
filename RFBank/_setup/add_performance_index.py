"""Explicit local index installation; backup before DDL, never run on import."""
from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]


def install(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Expected an existing RFBank project database')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as check:
        for _, name, *_ in check.execute('PRAGMA index_list(financial_transactions)'):
            columns = [r[2] for r in check.execute('PRAGMA index_info("'+name.replace('"','""')+'")')]
            if columns and columns[0] == 'posting_date':
                return dict(created=False, existing=name)
    backup = ROOT/'backups'/('before-performance-index-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
    backup.parent.mkdir(exist_ok=True)
    source = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close(); source.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute('CREATE INDEX IF NOT EXISTS ix_ft_posting_date_id ON financial_transactions(posting_date,id)')
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        connection.close()
    return dict(created=True, backup=str(backup))


if __name__ == '__main__':
    print(install(ROOT/'rfone.db'))
