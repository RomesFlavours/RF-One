import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from datetime import datetime,timezone
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.clover import acquisition,ingest,mapping

class EmployeeHistoryTests(unittest.TestCase):
    def registry_profile(self,session,name,code=None):
        session.get.return_value=SimpleNamespace(source_name=name,source_custom_id=code,
            protect_name=False,protect_code=False,protect_status=False,version=1,needs_review=False)

    def test_profile_missing_from_catalog_and_404_keeps_details_and_identity(self):
        existing=SimpleNamespace(id=17,display_name='Archived Name',custom_id='K',system_role='EMPLOYEE',active=True)
        session=Mock();session.scalars.return_value.first.return_value=existing
        client=SimpleNamespace(merchant_id='M',get=Mock(return_value=SimpleNamespace(ok=False,status_code=404)))
        complete=SimpleNamespace(ok=True,truncated_by_safety_guard=False,elements=[])
        ids=lambda session,model,**kwargs: {'OLD':17} if model is m.Employee else {}
        with patch.object(acquisition,'_existing_ids_by_source',side_effect=ids),patch.object(acquisition,'paginate',return_value=complete),patch.object(acquisition,'_mirror_source_record'):
            mapping_ids,_,_=acquisition._fetch_reference_catalogs(client,session,location_id=1,source_system_id=1,ingestion_run_id=1,retrieved_at=datetime.now(timezone.utc),mode='LIVE_SYNC')
        self.assertEqual(mapping_ids['OLD'],17)
        self.assertEqual(existing.display_name,'Archived Name')
        self.assertTrue(existing.active)
        self.assertFalse(existing.source_available)
        session.delete.assert_not_called()

    def test_both_import_paths_keep_known_details_on_id_only_reference(self):
        for writer in (acquisition._get_or_create,ingest.upsert):
            with self.subTest(writer=writer.__name__):
                existing=SimpleNamespace(id=17,display_name='Historical Name',custom_id='KNOWN',system_role='EMPLOYEE',active=True)
                session=Mock();session.scalars.return_value.first.return_value=existing
                self.registry_profile(session,'Historical Name','KNOWN')
                writer(session,m.Employee,{'source_employee_id':'OLD'},mapping.map_employee({'id':'OLD'}))
                self.assertEqual(existing.display_name,'Historical Name')
                self.assertEqual(existing.custom_id,'KNOWN')
                self.assertEqual(existing.system_role,'EMPLOYEE')
                self.assertTrue(existing.active)
                session.delete.assert_not_called()

    def test_new_evidence_updates_name_without_changing_employee_identity(self):
        existing=SimpleNamespace(id=7,display_name='Before',active=None)
        session=Mock();session.scalars.return_value.first.return_value=existing
        self.registry_profile(session,'Before')
        obj,_=acquisition._get_or_create(session,m.Employee,{'source_employee_id':'OLD'},mapping.map_employee({'id':'OLD','name':'After'}))
        self.assertEqual((obj.id,obj.display_name),(7,'After'))

    def test_blank_or_null_details_preserve_known_values_but_false_is_evidence(self):
        self.assertEqual(mapping.preserve_employee_details({'display_name':'  ','custom_id':None,'active':False,'source_available':False}),{'active':False,'source_available':False})

if __name__=='__main__':unittest.main()
