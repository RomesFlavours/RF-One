import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from datetime import datetime,timezone
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.clover import acquisition,ingest,mapping

class EmployeeHistoryTests(unittest.TestCase):
    def test_reference_catalogs_read_identities_only_from_registry_cards(self):
        # REGISTRY_MULTISITE_001: no staff-list read, no card written; the POS IDs on cards resolve people.
        session=Mock()
        client=SimpleNamespace(merchant_id='M',get=Mock())
        with patch('rfone_data_store.employee_directory.resolved_identities',return_value={'OLD':17}) as resolved,patch.object(acquisition,'_existing_ids_by_source',return_value={}),patch.object(acquisition,'paginate') as page,patch.object(acquisition,'_mirror_source_record') as mirror:
            mapping_ids,_,_=acquisition._fetch_reference_catalogs(client,session,location_id=1,source_system_id=1,ingestion_run_id=1,retrieved_at=datetime.now(timezone.utc),mode='LIVE_SYNC')
        self.assertEqual(mapping_ids,{'OLD':17})
        resolved.assert_called_once_with(session,'M')
        page.assert_not_called()
        mirror.assert_not_called()
        client.get.assert_not_called()
        session.add.assert_not_called()

    def test_both_import_paths_keep_known_details_on_id_only_reference(self):
        for writer in (acquisition._get_or_create,ingest.upsert):
            with self.subTest(writer=writer.__name__):
                existing=SimpleNamespace(display_name='Historical Name',custom_id='KNOWN',system_role='EMPLOYEE',active=True)
                session=Mock();session.scalars.return_value.first.return_value=existing
                writer(session,m.Employee,{'source_employee_id':'OLD'},mapping.map_employee({'id':'OLD'}))
                self.assertEqual(existing.display_name,'Historical Name')
                self.assertEqual(existing.custom_id,'KNOWN')
                self.assertEqual(existing.system_role,'EMPLOYEE')
                self.assertTrue(existing.active)
                session.delete.assert_not_called()

    def test_new_evidence_preserves_internal_name_and_employee_identity(self):
        existing=SimpleNamespace(id=7,display_name='Before',active=None)
        session=Mock();session.scalars.return_value.first.return_value=existing
        obj,_=acquisition._get_or_create(session,m.Employee,{'source_employee_id':'OLD'},mapping.map_employee({'id':'OLD','name':'After'}))
        self.assertEqual((obj.id,obj.display_name),(7,'Before'))
        from rfone_data_store.employee_directory import safe_snapshot
        self.assertEqual(safe_snapshot({'id':'OLD','name':'After'})['name'],'After')

    def test_blank_or_null_details_preserve_known_values_but_false_is_evidence(self):
        self.assertEqual(mapping.preserve_employee_details({'display_name':'  ','custom_id':None,'active':False,'source_available':False}),{'active':False,'source_available':False})

if __name__=='__main__':unittest.main()
