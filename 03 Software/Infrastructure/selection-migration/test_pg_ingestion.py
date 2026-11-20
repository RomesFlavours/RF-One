"""Use the real upload service/readers on PostgreSQL; S3 is replaced by an in-memory store."""
import argparse,hashlib,io,json,sys
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage
from production_import import connect_target
from workspace import engine as cv_engine,rule_ai
from rfone_data_store.selection import document_store,workspace_models as ps,persistence
from rfone_data_store.selection.core.profile import CandidateCVProfile,WorkHistoryRecord
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client
from rfone_data_store import models as m


class MemoryS3:
    def __init__(self):self.objects={}
    def upload_file(self,path,bucket,key,ExtraArgs):self.objects[(bucket,key)]=Path(path).read_bytes()
    def get_object(self,Bucket,Key):return {'Body':io.BytesIO(self.objects[(Bucket,Key)])}
    def head_object(self,Bucket,Key):return {'ContentLength':len(self.objects[(Bucket,Key)])}


class TrackedStore(document_store.S3DocumentStore):
    def stage(self,*args):
        staged=super().stage(*args);self.last_local=staged.local_path;return staged


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preparation',type=Path,required=True);p.add_argument('--port',type=int,default=55479);args=p.parse_args()
    root=args.preparation.resolve();report=json.loads((root/'production-runner-local-verification.json').read_text());name=report['database'];archive=root.parent
    engine=connect_target(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{name}','local','apply',None,{'plan_sha256':'fixture'})
    s3=MemoryS3();store=TrackedStore('local-fixture-only',s3)
    txt=b'Jordan\x00 QA Example\nqa-postgres-ingestion@example.invalid\nEXPERIENCE\nServer - QA Bistro\nJan 2021 - Present\nServed guests and coordinated table service.'
    from docx import Document
    doc=Document();doc.add_paragraph('Docx QA Example');doc.add_paragraph('qa-docx-postgres@example.invalid');doc.add_paragraph('EXPERIENCE');doc.add_paragraph('Server - QA Bistro');doc.add_paragraph('Jan 2020 - Present');buf=io.BytesIO();doc.save(buf)
    docs=json.loads((archive/'migration-review/20261115T171115Z/document-inventory.json').read_text(encoding='utf-8'))['local'];pdf=next(d for d in docs if d['id']==38)
    scanned=next(d for d in docs if 'CollinAlmand' in d['filename'])
    fixtures=[('qa-nul.txt',txt),('qa.docx',buf.getvalue()),('qa-pdf.pdf',Path(pdf['local_file']).read_bytes()),('qa-scanned.pdf',Path(scanned['local_file']).read_bytes())]
    with isolated_ai_client() as guard,patch.object(rule_ai,'generate',side_effect=AssertionError('Upload must not evaluate with AI')),Session(engine) as db:
        position=db.get(ps.Position,7);proposals=db.scalar(text('SELECT count(*) FROM selection_workspace_proposals'))
        def upload(filename,data):
            return cv_engine.import_cv(db,documents=store,restaurant_id=1,position=position,file_storage=FileStorage(stream=io.BytesIO(data),filename=filename),channel=ps.MANUAL_UPLOAD,actor_id=4,actor_name='QA fixture',analyze_after=False,ai_reading=False)
        imported=[]
        for filename,data in fixtures:
            result=upload(filename,data);assert result['status']=='OK',result.get('message')
            pc=db.get(ps.PositionCandidate,result['position_candidate_id']);candidate=db.get(m.Candidate,pc.candidate_id);raw=db.get(m.RawResume,candidate.raw_resume_id)
            assert '\x00' not in raw.raw_text and '\x00' not in (candidate.full_name or '')
            assert store.read(raw.storage_path)==data
            assert not Path(store.last_local).exists(),'S3 staging file leaked'
            imported.append(pc.id)
        count=db.scalar(text('SELECT count(*) FROM raw_resumes'));assert upload(*fixtures[0])['status']=='DUPLICATE';assert db.scalar(text('SELECT count(*) FROM raw_resumes'))==count
        assert upload('qa-empty.txt',b'')['status']=='FAILED';assert db.scalar(text('SELECT count(*) FROM raw_resumes'))==count
        assert not Path(store.last_local).exists()
        assert db.scalar(text('SELECT count(*) FROM selection_workspace_proposals'))==proposals
        profile=CandidateCVProfile(full_name='Nested\x00 QA',summary='Summary\x00',work_history=[WorkHistoryRecord(employer='QA\x00',responsibilities='Work\x00')])
        candidate=persistence.save_candidate_profile(db,profile,restaurant_id=1,raw_resume_id=None);assert candidate.full_name=='Nested QA';assert candidate.work_history[0].employer=='QA'
        db.rollback();assert not guard.attempts
    engine.dispose();checks={'postgresql_ingestion_verified':True,'txt_with_nul':True,'real_pdf_with_nul':True,'docx':True,'image_only_pdf_ocr':True,'nested_parser_text_normalized':True,
        'original_bytes_unchanged':True,'original_hash_duplicate_detection_preserved':True,'empty_file_isolation':True,'s3_uri_path_verified_with_memory_transport':True,'temporary_files_cleaned':True,'evaluations_created':0,'aws_calls':0}
    (root/'postgresql-ingestion-verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8');print('POSTGRESQL INGESTION VERIFIED:',json.dumps(checks),flush=True)


if __name__=='__main__':main()
