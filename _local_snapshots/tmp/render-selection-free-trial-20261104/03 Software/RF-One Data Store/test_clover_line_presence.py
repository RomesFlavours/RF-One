import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from rfone_data_store.technical.connectors.clover.historical_backfill_detail import reconcile_order_line_presence

class LinePresenceTests(unittest.TestCase):
    def test_absent_lines_are_retained_and_returned_lines_reactivated(self):
        existing=[SimpleNamespace(source_line_item_id='OLD',source_present=True),SimpleNamespace(source_line_item_id='BACK',source_present=False)]
        session=Mock();session.scalars.return_value.all.return_value=existing
        reconcile_order_line_presence(session,SimpleNamespace(id=1),[{'id':'BACK'}])
        self.assertEqual([x.source_present for x in existing],[False,True])
        session.delete.assert_not_called()

    def test_verified_empty_collection_marks_all_absent_without_deletion(self):
        existing=[SimpleNamespace(source_line_item_id='OLD',source_present=True)]
        session=Mock();session.scalars.return_value.all.return_value=existing
        reconcile_order_line_presence(session,SimpleNamespace(id=1),[])
        self.assertFalse(existing[0].source_present)
        session.delete.assert_not_called()

if __name__=='__main__':unittest.main()
