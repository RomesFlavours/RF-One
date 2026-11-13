from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_registry_performance.py')
p.write_text('''"""Query-growth and queue-equivalence regressions on a disposable local DB."""
import unittest
from datetime import datetime, timezone
from sqlalchemy import event, select
from test_registry_clover_confirmation import RegistryCloverTest
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.clover.identity_holds import held_shifts
from registry_clover import _held_by_link


class RegistryPerformanceTest(RegistryCloverTest):
    def test_query_budget_with_forty_linked_people(self):
        with self.factory() as db:
            for i in range(40):
                person=m.Employee(display_name=f'Person {i:03}',location_id=self.loc,active=i%7!=0)
                account=m.RFOneAccount(username=f'fixture-{i}',display_name=f'Person {i:03}',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1)
                db.add_all([person,account]);db.flush()
                db.add(m.EmployeeContextLink(employee_id=person.id,rfone_account_id=account.id))
            db.commit()
        for tab,limit in [('people',250),('roles',30),('areas',30),('companies',30)]:
            queries=[]
            def count(*args):queries.append(args[2])
            event.listen(self.engine,'before_cursor_execute',count)
            try:response=self.client.get('/admin/roles?tab='+tab)
            finally:event.remove(self.engine,'before_cursor_execute',count)
            self.assertEqual(response.status_code,200)
            self.assertLess(len(queries),limit,(tab,len(queries)))
        self.assertIn(b'Person 001',self.client.get('/admin/roles').data)
        self.assertNotIn(b'data-edit-person="employee:2"',self.client.get('/admin/roles').data)

    def test_batched_mirror_matches_existing_reader_after_employee_changes(self):
        with self.factory() as db:
            original=db.get(m.EmployeeCloverLink,self.link)
            other=m.EmployeeCloverLink(location_id=self.loc,merchant_id='WP',external_employee_id='other',state='PRESENT',snapshot={'name':'Other'})
            db.add(other);db.flush()
            source=db.scalar(select(m.SourceRecord).order_by(m.SourceRecord.id))
            def mirror(employee,override=None):
                raw={'id':'reassigned-shift','employee':{'id':employee},'inTime':1793030400000}
                if override:raw['overrideInEmployee']={'id':override}
                db.add(m.SourceRecord(source_system_id=source.source_system_id,retrieved_at=datetime.now(timezone.utc),payload_hash='fixture',ingestion_run_id=source.ingestion_run_id,entity_type='shift',source_id='reassigned-shift',raw_json=raw))
            mirror('pending');mirror('other','pending');db.flush()
            actual=_held_by_link(db,[original,other])
            for link in (original,other):
                expected=held_shifts(db,location_ids=[link.location_id],external_ids={link.external_employee_id})
                self.assertEqual(actual[link.id],expected)
            self.assertIn('reassigned-shift',actual[other.id])
            # Latest pending match now refers to the other employee, so exclude it.
            self.assertNotIn('reassigned-shift',actual[original.id])
            # Once attributed, both queue readers must remove the canonical shift.
            db.add(m.Shift(employee_id=self.person,location_id=self.loc,source_shift_id='reassigned-shift',clock_in=datetime(2026,10,26,tzinfo=timezone.utc)))
            db.flush()
            actual=_held_by_link(db,[original,other])
            for link in (original,other):
                self.assertEqual(actual[link.id],held_shifts(db,location_ids=[link.location_id],external_ids={link.external_employee_id}))


if __name__=='__main__':unittest.main()
''',encoding='utf-8',newline='\n')
