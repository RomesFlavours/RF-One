"""Activity labels are removed, not hidden; exact-source classification is tested separately."""
import sys, unittest, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, store

class RemovedLabelsTests(unittest.TestCase):
    def test_label_tables_and_model_are_absent(self):
        with sqlite3.connect(config.BANK_DB) as c:
            self.assertFalse(c.execute("select name from sqlite_master where name in ('bank_who_labels','bank_occurrence_labels')").fetchall())
            self.assertFalse(any(x[1].startswith('label_') for x in c.execute('pragma table_info(bank_who_profiles)')))
        self.assertFalse(hasattr(legacy.m,'BankWhoLabel'))
        self.assertFalse(hasattr(legacy.m,'BankOccurrenceLabel'))

    def test_engine_has_no_activity_label_inputs_or_outputs(self):
        e=E.Engine(legacy.session(),store.connect(":memory:"))
        self.assertFalse(hasattr(e,'who_labels'))
        for t in e.txns[:100]:
            r=e.evaluate(t)
            self.assertNotIn('who_labels',r)
            self.assertNotIn('label_hints',r)
            self.assertFalse(any(x['stage']=='Labels' for x in r['trace']))
        e.db.close()
