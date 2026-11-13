"""Read-only migration graph checks and isolated recovered-schema regression."""
from pathlib import Path
import importlib.util
import sys
import unittest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

STORE=Path(__file__).resolve().parent
sys.path.insert(0,str(STORE))

class MigrationHistoryTests(unittest.TestCase):
    def script(self):
        config=Config(str(STORE/'alembic.ini'))
        config.set_main_option('script_location',str(STORE/'migrations'))
        return ScriptDirectory.from_config(config)

    def test_all_parents_and_dependencies_are_resolvable(self):
        script=self.script()
        revisions=list(script.walk_revisions())
        self.assertTrue(revisions)
        for revision in revisions:
            for parent in revision._all_down_revisions:
                self.assertIsNotNone(script.get_revision(parent))
        for revision in ['e2c320261109','e1b220261102','e0a120261101',
                         'd9e220261029','c8e1f4a7b2d6','f2a120261110','f3b120261110']:
            self.assertIsNotNone(script.get_revision(revision))

    def test_registry_upgrade_does_not_schedule_other_branches(self):
        script=self.script()
        steps=script._upgrade_revs('t9c120261112',('k9f120261112',))
        self.assertEqual([step.to_revisions for step in steps],[('t9c120261112',)])
        self.assertEqual(script._upgrade_revs('t9c120261112',('k9f120261112','t9c120261112')),[])

    def test_recovered_tip_scope_migration_preserves_existing_rule(self):
        path=STORE/'migrations/versions/e2c320261109_tips_aggregation_scope.py'
        spec=importlib.util.spec_from_file_location('tip_scope_migration',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE tip_distribution_rule_versions (id INTEGER PRIMARY KEY, rate INTEGER NOT NULL)'))
                connection.execute(text('INSERT INTO tip_distribution_rule_versions VALUES (7,25)'))
                with Operations.context(MigrationContext.configure(connection)):
                    module.upgrade()
                    self.assertEqual(tuple(connection.execute(text('SELECT id,rate,aggregation_scope FROM tip_distribution_rule_versions')).one()),(7,25,'ORDER'))
                    module.downgrade()
                self.assertEqual(tuple(connection.execute(text('SELECT id,rate FROM tip_distribution_rule_versions')).one()),(7,25))
        finally:
            engine.dispose()

if __name__=='__main__':unittest.main(verbosity=2)
