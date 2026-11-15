"""Verify PostgreSQL reader exclusion across processes, including abrupt owner death."""
import argparse,json,multiprocessing,time,sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
REPO=Path(__file__).resolve().parents[3];APP=REPO/'03 Software/AWSSelection/Selection'
sys.path[:0]=[str(APP),str(APP.parent/'RF-One Data Store')]
from workspace.job_ownership import own_reader


def owner(url,ready):
    engine=create_engine(url);factory=sessionmaker(bind=engine)
    with own_reader(factory,2147000000) as acquired:
        if not acquired:raise RuntimeError('Fixture owner could not acquire lock')
        ready.set();time.sleep(60)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preparation',type=Path,required=True);p.add_argument('--port',type=int,default=55479);args=p.parse_args();root=args.preparation.resolve()
    name=json.loads((root/'production-runner-local-verification.json').read_text())['database']
    if not name.startswith('selection_production_test_'):raise RuntimeError('Wrong test database')
    url=f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{name}';engine=create_engine(url);factory=sessionmaker(bind=engine)
    ready=multiprocessing.Event();process=multiprocessing.Process(target=owner,args=(url,ready));process.start()
    try:
        assert ready.wait(25)
        with own_reader(factory,2147000000) as acquired:assert not acquired,'Second process acquired an active job'
        process.terminate();process.join(10)
        recovered=False
        for _ in range(40):
            with own_reader(factory,2147000000) as acquired:
                if acquired:recovered=True;break
            time.sleep(.1)
        assert recovered,'Owner death did not release the database lock'
        with own_reader(factory,2147000000) as acquired:assert acquired
    finally:
        if process.is_alive():process.terminate();process.join(10)
        engine.dispose()
    result={'cross_process_exclusion':True,'crashed_owner_releases_lease':True,'subsequent_poll_can_resume':True,'ai_calls':0,'aws_calls':0}
    (root/'job-ownership-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('JOB OWNERSHIP VERIFIED:',json.dumps(result))


if __name__=='__main__':main()
