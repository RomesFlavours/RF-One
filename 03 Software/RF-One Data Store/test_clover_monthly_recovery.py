"""Regression tests for silent 90-day truncation and historical identities."""
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from rfone_data_store.technical.connectors.clover import acquisition as a

class MonthlyRecoveryTests(unittest.TestCase):
    def test_every_month_and_millisecond_boundary_is_requested(self):
        calls=[]
        def page(client,path,extra_params):
            lower,upper=[int(s.split('=')[-1]) for s in extra_params['filter']]
            self.assertLessEqual(upper-lower,31*86400000)
            calls.append((lower,upper))
            return SimpleNamespace(ok=True,truncated_by_safety_guard=False,elements=[{'id':str(lower)}])
        start=datetime(2026,1,1,5,tzinfo=timezone.utc)
        end=datetime(2026,10,18,14,tzinfo=timezone.utc)
        with patch.object(a,'paginate',side_effect=page):
            rows=a._read_monthly_collection(None,'/payments',period_start=start,period_end=end)
        self.assertEqual(len(rows),10)
        self.assertEqual(calls[0][0],int(start.timestamp()*1000))
        self.assertEqual(calls[-1][1],int(end.timestamp()*1000))
        self.assertTrue(all(right[0]==left[1]+1 for left,right in zip(calls,calls[1:])))

    def test_partial_month_never_passes_for_complete(self):
        result=SimpleNamespace(ok=False,error='network failure',error_status_code=503,truncated_by_safety_guard=False)
        with patch.object(a,'paginate',return_value=result):
            with self.assertRaises(a.CloverSourceUnavailableError):
                a._read_monthly_collection(None,'/payments',period_start=datetime(2026,1,1,tzinfo=timezone.utc),period_end=datetime(2026,1,2,tzinfo=timezone.utc))

    def test_historical_reference_404_preserves_identity_without_invented_details(self):
        client=SimpleNamespace(merchant_id='M',get=Mock(return_value=SimpleNamespace(ok=False,status_code=404)))
        session=Mock(); identities={}
        with patch('rfone_data_store.employee_directory.observe_historical_employee',return_value=SimpleNamespace(id=123)) as observe,patch.object(a,'_mirror_source_record') as mirror:
            a._resolve_historical_employee(client,session,{'id':'OLD'},location_id=1,source_system_id=1,employee_by_source_id=identities,ingestion_run_id=5,retrieved_at=datetime.now(timezone.utc))
        self.assertEqual(identities,{'OLD':123})
        self.assertEqual(observe.call_args.kwargs['raw'], {'id':'OLD'})
        self.assertFalse(observe.call_args.kwargs['available'])
        self.assertEqual(mirror.call_args.kwargs['entity_type'],'employee_reference')

    def test_unauthorized_historical_employee_fails_without_creating_identity(self):
        client=SimpleNamespace(merchant_id='M',get=Mock(return_value=SimpleNamespace(ok=False,status_code=403,error='denied')))
        with patch('rfone_data_store.employee_directory.observe_historical_employee') as observe:
            with self.assertRaises(a.CloverSourceUnavailableError):
                a._resolve_historical_employee(client,Mock(),{'id':'OLD'},location_id=1,source_system_id=1,employee_by_source_id={},ingestion_run_id=5,retrieved_at=datetime.now(timezone.utc))
        observe.assert_not_called()

if __name__=='__main__':unittest.main()
