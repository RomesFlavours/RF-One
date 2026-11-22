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

    def test_historical_employee_references_are_never_looked_up_in_clover(self):
        # REGISTRY_MULTISITE_001: the former historical-identity reader (which created pending Registry
        # identities) is removed; an unknown reference simply waits as unattributed work.
        self.assertFalse(hasattr(a,'_resolve_historical_employee'))
        self.assertFalse(hasattr(a,'EmployeeIdentityConfirmationRequired'))

if __name__=='__main__':unittest.main()
