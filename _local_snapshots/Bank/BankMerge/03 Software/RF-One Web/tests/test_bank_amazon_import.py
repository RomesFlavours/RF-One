"""Monthly Amazon import integration, on a disposable operational DB backup."""
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1])]
import test_bank_conversation_intent as fixture
import app as web
import auth
from db import SessionFactory
from sqlalchemy import select
from rfone_data_store import models as m
import bank_amazon as amazon
import bank_guided_reconciliation as guided
from rfone_data_store.bank_reconciliation import import_session

HEADER = 'Order Date,Order ID,Charge Identifier,ASIN,Title,Item Quantity\n'
REPORT = (HEADER + '01/01/2027,ORDER-A,TESTAMZ123,ASIN1,Printer paper,1\n'
          '01/01/2027,ORDER-A,TESTAMZ123,ASIN2,Personal product,1\n'
          '01/01/2027,ORDER-B,LATERAMZ456,ASIN3,Ceiling fan,1\n').encode()


class AmazonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.IntentTests.setUpClass()
        cls.account = fixture.IntentTests.admin_id
        cls.source = fixture.IntentTests.personal_card
        cls.why = fixture.IntentTests.personal_why
        cls.folder = tempfile.TemporaryDirectory(prefix='amazon-stage-')
        web.app.config['BANK_IMPORT_STAGING_DIR'] = cls.folder.name
        web.app.config['BANK_CHAT_PROVIDER_CONTEXT_APPROVED'] = True

    def setUp(self):
        # Each test owns its artifact state; the fixture ledger is retained.
        with SessionFactory() as db:
            for a in db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind.in_((amazon.REPORT, amazon.RUN)))):
                db.delete(a)
            for t in db.scalars(select(m.FinancialTransaction).where(m.FinancialTransaction.description_original.like('%TESTAMZ%'))):
                t.description_original = 'OLD FIXTURE'
            txn=m.FinancialTransaction(payment_instrument_id=self.source,description_original='AMZN Mktp US*TESTAMZ123',
                transaction_date=date(2027,2,20),posting_date=date(2027,2,22),amount_minor=-99999,
                accounting_status='CANONICAL',duplicate_status='NONE',classification='UNKNOWN',status='COMPLETED')
            db.add(txn);db.flush();self.txn=txn.id;db.commit()
        self.client=web.app.test_client()
        with self.client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY]=self.account
            session[auth.SESSION_VERSION_KEY]=fixture.IntentTests.admin_version
        response=self.client.get('/bank/amazon')
        self.assertEqual(response.status_code,200,(response.status_code,response.headers.get('Location'),response.data[:500]))
        page=self.client.get('/bank/ai-rules').data.decode()
        self.csrf=re.search(r'<meta name="bank-csrf" content="([^"]+)"',page).group(1)

    def fingerprint(self):
        tables=(m.FinancialTransaction,m.BankTransactionExplanation,m.BankTransactionAllocation,m.BankAiRule,
            m.BankAiRuleVersion,m.BankWhoSourceClassification,m.PaymentInstrument,m.BankOccurrence,
            m.BankTransactionReason,m.BankAccountingClassification,m.FinancialTransactionMatch)
        with SessionFactory() as db:
            values=[(t.__tablename__,[tuple(r) for r in db.execute(select(*t.__table__.c).order_by(t.id))]) for t in tables]
        return hashlib.sha256(json.dumps(values,default=str).encode()).hexdigest()

    def ingest(self, content=REPORT):
        with SessionFactory() as db:
            result=amazon.ingest(db,[dict(file_name='Amazon.csv',content=content)],self.account)
            db.commit();return result

    def provider(self,prompt):
        request=json.loads(prompt.split('\n')[-1])
        self.assertIn('UNTRUSTED DATA',prompt)
        return dict(items=[dict(item_id=i['item_id'],why_id=self.why,reason='Natura prodotto e WHOM personale',
            confidence='MEDIUM',question='') for i in request['items']])

    def latest(self):
        with SessionFactory() as db:
            return json.loads(amazon.artifacts(db,amazon.RUN,self.account)[0].payload)

    def test_exact_code_ignores_amount_dates_and_preserves_products_and_whom(self):
        before=self.fingerprint();self.ingest()
        amazon.process_pending(SessionFactory,True,self.provider)
        result=self.latest();self.assertEqual(result['status'],'COMPLETED',result)
        c=next(c for c in result['results'] if c['charge']=='TESTAMZ123')
        self.assertEqual(c['status'],'PROPOSED');self.assertEqual(len(c['items']),2)
        self.assertTrue(c['movement']['whom']['name'])
        self.assertEqual(c['movement']['id'],self.txn)
        self.assertEqual(self.fingerprint(),before)
        self.assertEqual(self.client.get('/bank/amazon').status_code,200)

    def test_unmatched_report_reused_by_later_bank_only_import(self):
        self.ingest();amazon.process_pending(SessionFactory,True,self.provider)
        with SessionFactory() as db:
            txn=m.FinancialTransaction(payment_instrument_id=self.source,description_original='AMAZON*LATERAMZ456',
                posting_date=date(2027,3,1),amount_minor=-1,accounting_status='CANONICAL',duplicate_status='NONE',classification='UNKNOWN',status='COMPLETED')
            db.add(txn);db.flush();tid=txn.id
            amazon.ingest(db,[],self.account);db.commit()
        amazon.process_pending(SessionFactory,True,self.provider)
        c=next(c for c in self.latest()['results'] if c['charge']=='LATERAMZ456')
        self.assertEqual(c['movement']['id'],tid);self.assertEqual(c['status'],'PROPOSED')

    def test_repeated_exports_do_not_duplicate_products(self):
        self.ingest();saved=self.ingest();self.assertFalse(saved[0]['created'])
        self.ingest(REPORT.replace(b'Printer paper',b'Updated paper'))
        with SessionFactory() as db:
            c=next(c for c in amazon.snapshot(db,self.account)['charges'] if c['charge']=='TESTAMZ123')
            self.assertEqual(len(c['products']),2)
            self.assertEqual(c['products'][0]['fields']['Title'],'Updated paper')

    def test_protected_confirmed_why_and_who_only_confirmation(self):
        with SessionFactory() as db:
            e=m.BankTransactionExplanation(financial_transaction_id=self.txn,decision_source='HUMAN',
                decision_status='HUMAN_CONFIRMED',transaction_reason_id=self.why)
            db.add(e);db.flush();db.get(m.FinancialTransaction,self.txn).explanation_id=e.id;db.commit()
        before=self.fingerprint();self.ingest()
        with patch.object(amazon.bank_chatgpt,'generate_json') as provider:
            amazon.process_pending(SessionFactory,True)
            provider.assert_not_called()
        c=next(c for c in self.latest()['results'] if c['charge']=='TESTAMZ123')
        self.assertEqual(c['status'],'PROTECTED');self.assertEqual(self.fingerprint(),before)
        with SessionFactory() as db:
            e=db.get(m.BankTransactionExplanation,db.get(m.FinancialTransaction,self.txn).explanation_id)
            self.assertTrue(amazon.protected(db.get(m.FinancialTransaction,self.txn),e))
            e.transaction_reason_id=None
            self.assertFalse(amazon.protected(db.get(m.FinancialTransaction,self.txn),e))
            db.rollback()

    def test_provider_failure_invalid_catalog_and_concurrent_change_keep_ledger(self):
        for mode in ('consent','invalid','failure','changed'):
            self.ingest();before=self.fingerprint()
            def provider(prompt):
                if mode=='failure':raise ValueError('Provider offline')
                answer=self.provider(prompt)
                if mode=='invalid':answer['items'][0]['why_id']=99999999
                if mode=='changed':
                    with SessionFactory() as db:
                        a=amazon.artifacts(db,amazon.REPORT,self.account)[0]
                        data=json.loads(a.payload);data['rows'][0]['fields']['Title']='Changed during analysis'
                        a.payload=amazon.encode(data);db.commit()
                return answer
            amazon.process_pending(SessionFactory,mode!='consent',provider)
            self.assertEqual(self.latest()['status'],'ERROR',mode)
            self.assertEqual(self.fingerprint(),before,mode)

    def test_bad_csv_blank_codes_repeated_lines_and_token_boundaries(self):
        with self.assertRaises(ValueError):amazon.parse_report(b'Order ID,Title\n1,Paper\n')
        with self.assertRaises(ValueError):amazon.parse_report(HEADER.encode()+b'1,2,ABC,ASIN,Paper\n')
        rows=amazon.parse_report((HEADER+'1,A,N/A,ASIN,Paper,1\n'+'1,A,ABC,ASIN,Fan,1\n'*3).encode())
        self.assertEqual(rows['without_code'],1);self.assertEqual(len(rows['rows']),4)
        self.assertEqual(rows['rows'][0]['fields']['Charge Identifier'],'N/A')
        self.ingest(REPORT.replace(b'TESTAMZ123',b'TESTAMZ12'))
        with SessionFactory() as db:
            c=next(c for c in amazon.snapshot(db,self.account)['charges'] if c['charge']=='TESTAMZ12')
            self.assertEqual(c['status'],'UNMATCHED')

    def test_duplicate_bank_code_is_ambiguous_and_private_results(self):
        with SessionFactory() as db:
            db.add(m.FinancialTransaction(payment_instrument_id=self.source,description_original='AMZN*TESTAMZ123',
                posting_date=date(2027,2,23),amount_minor=-200,accounting_status='CANONICAL',duplicate_status='NONE',classification='UNKNOWN',status='COMPLETED'))
            db.commit()
        self.ingest()
        with SessionFactory() as db:
            c=next(c for c in amazon.snapshot(db,self.account)['charges'] if c['charge']=='TESTAMZ123')
            self.assertEqual(c['status'],'AMBIGUOUS')
            self.assertFalse(amazon.artifacts(db,amazon.REPORT,-999))
        self.assertEqual(self.client.post('/bank/amazon').status_code,400)

    def test_http_report_only_import_confirmation_and_replay(self):
        before=self.fingerprint()
        response=self.client.post('/bank/upload',data=dict(csrf_token=self.csrf,
            files=(io.BytesIO(REPORT),'Amazon.csv')),content_type='multipart/form-data')
        location=response.headers['Location'];token=location.rsplit('/',1)[-1]
        page=self.client.get(location);self.assertEqual(page.status_code,200,page.data[:300])
        self.assertIn(b'Amazon report ready',page.data)
        response=self.client.post(location+'/check',data=dict(csrf_token=self.csrf))
        page=self.client.get(location)
        self.assertNotIn(b'id="import-confirm" disabled',page.data)
        callbacks=[]
        with patch.object(guided,'run_after_import',side_effect=lambda **kw:callbacks.append(kw['after'])), \
             patch('bank_who_identification_routes.enqueue_new'),patch('bank_import_worker.Worker.wake'):
            response=self.client.post(f'/bank/upload/{token}/confirm',data=dict(csrf_token=self.csrf))
        self.assertEqual(response.status_code,302)
        # BANK_UPLOAD_AND_RECONCILE_001: an import starts nothing; the proposals run when the person starts
        # the reconciliation (Upload and Reconcile runs `process_pending` first).
        self.assertEqual(len(callbacks),0)
        with SessionFactory() as db:self.assertEqual(len(amazon.artifacts(db,amazon.REPORT,self.account)),1)
        with patch.object(amazon.bank_chatgpt,'generate_json',side_effect=self.provider):
            amazon.process_pending(SessionFactory,True)
        self.assertEqual(self.latest()['status'],'COMPLETED',self.latest())
        self.client.post(f'/bank/upload/{token}/confirm',data=dict(csrf_token=self.csrf))
        self.assertEqual(self.fingerprint(),before)

    def test_mixed_monthly_upload_imports_banks_before_amazon_and_ai_when_started(self):
        with SessionFactory() as db:
            source=next(s for s in db.scalars(select(m.PaymentInstrument))
                        if s.is_payment_source and s.instrument_type=='CREDIT_CARD'
                        and not import_session.source_missing_fields(db,s))
            source_id=source.id
        report=REPORT.replace(b'TESTAMZ123',b'NEWAMZ998')
        bank=(b'Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n'
              b'02/11/2027,02/12/2027,AMZN Mktp US*NEWAMZ998,Shopping,Sale,-23.45,\n')
        response=self.client.post('/bank/upload',data=dict(csrf_token=self.csrf,
            payment_instrument_id=str(source_id),files=[(io.BytesIO(report),'Amazon.csv'),
            (io.BytesIO(bank),'Chase-card.csv')]),content_type='multipart/form-data')
        location=response.headers['Location'];token=location.rsplit('/',1)[-1]
        self.client.get(location)
        self.client.post(location+'/check',data=dict(csrf_token=self.csrf))
        order=[];real_ingest=amazon.ingest
        def ingest(db,files,account_id):
            self.assertIsNotNone(db.scalar(select(m.FinancialTransaction).where(
                m.FinancialTransaction.description_original=='AMZN Mktp US*NEWAMZ998')))
            order.append('bank first');return real_ingest(db,files,account_id)
        def run(**kw):
            with SessionFactory() as db:
                self.assertTrue(amazon.artifacts(db,amazon.REPORT,self.account))
            order.append('committed');kw['after']()
        with patch.object(amazon,'ingest',side_effect=ingest),patch.object(guided,'run_after_import',side_effect=run),\
             patch.object(amazon.bank_chatgpt,'generate_json',side_effect=self.provider),patch('bank_import_worker.Worker.wake'):
            response=self.client.post(f'/bank/upload/{token}/confirm',data=dict(csrf_token=self.csrf))
        self.assertEqual(response.status_code,302)
        self.assertEqual(order,['bank first'])   # nothing runs after the import (BANK_UPLOAD_AND_RECONCILE_001)
        with patch.object(amazon.bank_chatgpt,'generate_json',side_effect=self.provider):
            amazon.process_pending(SessionFactory,True)
        self.assertEqual(self.latest()['status'],'COMPLETED',self.latest())
        c=next(c for c in self.latest()['results'] if c['charge']=='NEWAMZ998')
        self.assertEqual(c['movement']['source'],source.display_name)

    def test_engine_callback_follows_engine_completion(self):
        import types
        order=[];threads=[]
        class Thread:
            def __init__(self,**kwargs):self.target=kwargs['target'];threads.append(self)
            def start(self):self.target()
        fake=types.ModuleType('cbank')
        fake.service=types.SimpleNamespace(run_if_bank_changed=lambda con:order.append('engine'))
        with patch.dict(sys.modules,{'cbank':fake}),patch.object(guided,'available',return_value=True),\
             patch.object(guided,'_cbank_app',return_value=types.SimpleNamespace(config={'CON':None})),\
             patch.object(guided.threading,'Thread',Thread):
            guided.run_after_import(after=lambda:order.append('amazon'))
        self.assertEqual(order,['engine','amazon'])


if __name__=='__main__':unittest.main(verbosity=2)


