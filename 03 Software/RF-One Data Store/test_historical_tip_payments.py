"""Isolated historical payout evidence and Tips HTTP regressions."""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from rfone_data_store import models as m
from rfone_data_store.tips import historical_payments as service


class HistoricalPaymentsTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        for model in [m.SourceSystem,m.Location,m.Restaurant,m.RestaurantLocation,m.Employee,m.EmployeeIdentityAlias,m.EmployeeCloverLink,m.EmployeeAssignment,m.IngestionRun,m.SourceRecord]:
            model.__table__.create(self.engine)
        self.factory=sessionmaker(self.engine)
        with self.factory.begin() as session:
            session.add(m.Restaurant(id=1,name='Test restaurant'))
            session.add(m.Restaurant(id=2,name='Other restaurant'))
            session.add(m.RestaurantLocation(restaurant_id=1,location_id=1))
            session.add(m.Employee(id=1,location_id=1,display_name='Example Person',source_employee_id='fixture'))
            session.add(m.Employee(id=2,location_id=2,display_name='Example Person',source_employee_id='other'))
        row={'pdf_row':1,'page':1,'recipient':'Example Person','amount_minor':12345,'date':'2026-01-12',
            'memo':'26 Jan 05-11 Tip','status':'Completed','explicit_tip':True,'category':'in_scope',
            'period_start':'2026-01-05','period_end':'2026-01-11','nonstandard_week':False}
        self.payload={'pdf_sha256':'a'*64,'scope':['2026-01-01','2026-10-04'],
            'ledger':[row,{**row,'pdf_row':2},{**row,'pdf_row':3,'recipient':'Unknown Person'}],
            'people':[{'name':'Example Person'},{'name':'Unknown Person'}],
            'totals':{'in_scope_minor':37035},'basis':'PDF explicit completed tips'}

    def load(self,payload=None):
        with self.factory.begin() as session:
            return service.import_document(session,payload=payload or self.payload,
                restaurant_id=1,location_id=1,file_name='fixture.pdf')

    def view(self,run):
        with self.factory() as session:return service.report(session,restaurant_id=1,run_id=run)

    def test_idempotency_and_exact_name_scope(self):
        first=self.load(); second=self.load()
        self.assertTrue(first['created']);self.assertFalse(second['created'])
        self.assertEqual(first['run_id'],second['run_id'])
        report=self.view(first['run_id'])
        self.assertEqual(report['totals']['in_scope'],37035)
        person=report['people'][0]
        self.assertEqual(person['employee_id'],1)
        self.assertEqual(person['exact_repeat_extra'],12345)
        self.assertTrue(report['people'][1]['unresolved'])
        with self.factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(m.SourceRecord)),4)
            self.assertIsNone(service.report(session,restaurant_id=2,run_id=first['run_id']))

    def test_modified_document_refused_without_overwrite(self):
        run=self.load()['run_id']; changed=copy.deepcopy(self.payload)
        changed['ledger'][0]['memo']='Changed'
        with self.assertRaises(ValueError):self.load(changed)
        self.assertEqual(self.view(run)['people'][0]['payments'][0]['observation']['memo'],'26 Jan 05-11 Tip')

    def test_pending_not_paid_and_no_implicit_tip(self):
        for field,value in [('status','Rejected'),('explicit_tip',False),('amount_minor',1.5)]:
            changed=copy.deepcopy(self.payload);changed['ledger'][0][field]=value
            with self.assertRaises(ValueError):self.load(changed)

    def test_integrity_failure_visible(self):
        run=self.load()['run_id']
        with self.factory.begin() as session:
            record=session.scalars(select(m.SourceRecord).where(m.SourceRecord.entity_type==service.PAYMENT)).first()
            record.raw_json={**record.raw_json,'currency':'EUR'}
        with self.assertRaises(ValueError):self.view(run)

    def test_ambiguous_identity_not_guessed(self):
        with self.factory.begin() as session:
            session.add(m.Employee(location_id=1,display_name='Example Person'))
        run=self.load()['run_id']
        self.assertTrue(self.view(run)['people'][0]['unresolved'])
        self.assertIsNone(self.view(run)['people'][0]['employee_id'])

    def test_import_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with self.factory.begin() as session:
                service.import_document(session,payload=self.payload,restaurant_id=1,location_id=1,file_name='fixture.pdf')
                raise RuntimeError('abort')
        with self.factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(m.SourceRecord)),0)

    def test_http_authenticated_read_and_scope(self):
        run=self.load()['run_id']
        tips=HERE.parent/'Tips'
        sys.path.insert(0,str(tips))
        with patch.dict(os.environ,{'RFONE_DATABASE_URL':'sqlite://','RFONE_FLASK_SECRET_KEY':'test-only'}):
            spec=importlib.util.spec_from_file_location('tips_historical_http_test',tips/'app.py')
            app=importlib.util.module_from_spec(spec);sys.modules[spec.name]=app;spec.loader.exec_module(app)
        app.SessionFactory=self.factory
        client=app.app.test_client()
        with patch.object(app.rfone_identity,'current_account',return_value=object()):
            response=client.get('/historical-tip-payments')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'370.35',response.data)
            self.assertIn(b'Unknown Person',response.data)
            self.assertIn(b'Needs identity review',response.data)
            self.assertEqual(client.get('/historical-tip-payments?document=99999').status_code,404)
            self.assertEqual(client.post('/historical-tip-payments').status_code,405)
        with patch.object(app.rfone_identity,'current_account',return_value=None):
            self.assertIn(client.get('/historical-tip-payments').status_code,(302,401))


if __name__=='__main__':unittest.main()
