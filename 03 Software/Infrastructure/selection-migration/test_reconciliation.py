"""Identity reconciliation rules of the import runner (fix A4). Synthetic plans only; no database, no network.

    python test_reconciliation.py
"""
import copy
import unittest

import production_import as runner


def plan():
    return {'inserts': {'candidate_persons': [{'id': 2}], 'candidates': [{'id': 10}, {'id': 11}], 'applications': []},
            'reused_ids': {'candidate_persons': {'1': 50}},
            'identity_reconciliation': [{'type': 'SAME_PERSON_DISTINCT_CV_AND_PDL', 'local_candidate_id': 10,
                                         'existing_candidate_id': 60, 'local_person_id': 1, 'existing_person_id': 50,
                                         'local_position_id': 7, 'existing_position_id': 3,
                                         'local_original_sha256': 'a' * 64, 'existing_original_sha256': 'b' * 64,
                                         'reason': 'synthetic'}]}


class ReconciliationScope(unittest.TestCase):
    def refused(self, mutate):
        p = plan()
        mutate(p)
        with self.assertRaises(runner.PlanError):
            runner.reconciliation_scope(p)

    def test_valid_reconciliation_exempts_only_that_candidate(self):
        self.assertEqual(runner.reconciliation_scope(plan()), {10})

    def test_plan_without_reconciliation_is_unchanged(self):
        self.assertEqual(runner.reconciliation_scope({'inserts': {}}), set())

    def test_unjustified_reuse_refused(self):
        self.refused(lambda p: p['reused_ids']['candidate_persons'].update({'9': 99}))

    def test_reuse_without_reconciliation_refused(self):
        self.refused(lambda p: p.update(identity_reconciliation=[]))

    def test_same_original_cv_refused(self):
        self.refused(lambda p: p['identity_reconciliation'][0].update(local_original_sha256='b' * 64))

    def test_same_job_refused(self):
        self.refused(lambda p: p['identity_reconciliation'][0].update(local_position_id=3))

    def test_reused_person_also_inserted_refused(self):
        self.refused(lambda p: p['inserts']['candidate_persons'].append({'id': 1}))

    def test_other_tables_cannot_be_reused(self):
        self.refused(lambda p: p['reused_ids'].update(candidates={'11': 61}))

    def test_unknown_type_refused(self):
        self.refused(lambda p: p['identity_reconciliation'][0].update(type='MERGE'))

    def test_scope_does_not_mutate_plan(self):
        p = plan()
        before = copy.deepcopy(p)
        runner.reconciliation_scope(p)
        self.assertEqual(p, before)


if __name__ == '__main__':
    unittest.main()
