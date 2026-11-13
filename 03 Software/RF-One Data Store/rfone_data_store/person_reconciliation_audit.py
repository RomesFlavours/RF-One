"""Read-only audit CLI for an explicitly configured local database."""
import argparse,json,os
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import make_url
from .database import create_configured_engine,create_session_factory
from .person_reconciliation import audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();url=os.environ.get('RFONE_DATABASE_URL','')
    value=make_url(url)
    if value.get_backend_name()!='sqlite' and value.host not in ('127.0.0.1','localhost','::1'):
        parser.error('This local audit requires a loopback database; no cloud access is performed.')
    engine=create_configured_engine(url);factory=create_session_factory(engine)
    try:
        with factory() as db:
            if engine.dialect.name=='postgresql':db.execute(text('SET TRANSACTION READ ONLY'))
            report=audit(db)
            if args.output:args.output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
            print(json.dumps({'ready':report['ready'],'counts':report['counts'],'broken_links':len(report['broken_links'])}))
    finally:engine.dispose()

if __name__=='__main__':main()
