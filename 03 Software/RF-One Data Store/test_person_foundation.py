"""Approved RF-One-owned person foundation. Disposable databases, no network."""
import unittest
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m, employee_directory as directory
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.projects import service as projects
from rfone_data_store.bank_reconciliation import card_configuration as cards
from rfone_data_store.bank_reconciliation.configuration import cardholder_candidates


class PersonFoundationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover")
        self.db.add(self.source); self.db.flush()
        merchant = m.Merchant(name="Test", source_system_id=self.source.id, source_merchant_id="WP")
        self.db.add(merchant); self.db.flush()
        self.site = m.Location(name="WP", merchant_id=merchant.id, source_system_id=self.source.id,
                               source_location_id="WP", timezone="America/New_York")
        self.db.add(self.site); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def person(self, name="RF-One Person"):
        return directory.create_person(self.db, display_name=name, email="reference@example.test", phone="123")

    def sync(self, records):
        result = directory.import_snapshot(self.db, location_id=self.site.id, merchant_id="WP", records=records)
        for link in self.db.scalars(select(m.EmployeeCloverLink)):
            link.last_clock_in = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.db.flush()
        return result

    def test_native_person_needs_no_pos_location_or_employment_and_has_account(self):
        person = self.person()
        self.assertIsNone(person.location_id)
        self.assertIsNone(person.source_system_id)
        self.assertEqual(person.email, "reference@example.test")
        directory.update_management(self.db, person, display_name="Updated reference", custom_id="", active=None, account_id=None)
        self.assertEqual((person.email, person.phone), ("reference@example.test", "123"))
        self.assertEqual(directory.employee_options(self.db)[0].id, person.id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), 1)
        for model in (m.EmployeeAssignment, m.EmployeeCompensationTerm):
            self.assertEqual(self.db.scalar(select(func.count()).select_from(model)), 0)
        self.assertTrue(all(event.employee_id == person.id for event in self.db.scalars(select(m.EmployeeDirectoryEvent))))

    def test_native_person_uses_workforce_sites_without_pos_and_keeps_history(self):
        person = self.person()
        restaurant = m.Restaurant(name="No POS restaurant")
        self.db.add(restaurant); self.db.flush()
        area = m.OperationalArea(restaurant_id=restaurant.id, name="Root")
        role = m.RestaurantRole(restaurant_id=restaurant.id, name="Role")
        self.db.add_all([area, role]); self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=self.site.id))
        assignment = m.EmployeeAssignment(employee_id=person.id, restaurant_id=restaurant.id,
            operational_area_id=area.id, restaurant_role_id=role.id, location_id=self.site.id,
            valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc), assignment_source="MANUAL")
        self.db.add(assignment); self.db.flush()
        self.assertEqual(directory.employee_options(self.db, location_ids=[self.site.id])[0].id, person.id)
        self.assertIsNone(person.location_id)
        assignment.valid_to = datetime(2021, 1, 1, tzinfo=timezone.utc)
        self.db.flush()
        self.assertEqual(directory.employee_options(self.db, location_ids=[self.site.id]), [])
        self.assertEqual(directory.employee_options(self.db, location_ids=[self.site.id], include_inactive=True)[0].id, person.id)
        assignment.valid_to = None
        self.db.flush()
        _, pending = self.sync([{"id": "MANUAL-PERSON", "name": person.display_name}])
        directory.attach_link(self.db, link_id=pending[0], employee_id=person.id)
        from rfone_data_store.profile.bootstrap import bootstrap_restaurant_profile, MODE_PERSIST
        bootstrap_restaurant_profile(self.db, restaurant_id=restaurant.id, source_system_id=self.source.id,
            mode=MODE_PERSIST, sync_time=datetime.now(timezone.utc))
        self.assertIsNone(assignment.valid_to)

    def test_unknown_pos_is_pending_even_without_suggestions_and_idempotent(self):
        for _ in range(3):
            resolved, pending = self.sync([{"id": "A", "name": "Unknown", "pin": "never-store"}])
            self.assertEqual(resolved, {})
            self.assertEqual(len(pending), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 0)
        link = self.db.get(m.EmployeeCloverLink, pending[0])
        self.assertNotIn("pin", link.snapshot)
        person = self.person("Reference Name")
        directory.attach_link(self.db, link_id=link.id, employee_id=person.id)
        resolved, pending = self.sync([{"id": "A", "name": "POS Changed", "email": "source@example.test"}])
        self.assertEqual(resolved["A"], person.id)
        self.assertEqual((person.display_name, person.email), ("Reference Name", "reference@example.test"))

    def test_same_merchant_duplicates_are_explicit_and_dynamic(self):
        person = self.person("Pinco Pallino")
        _, pending = self.sync([{"id": "A", "name": "Pinco Pallino"}, {"id": "B", "name": "Pallino Pinco"}])
        for identity in pending:
            directory.attach_link(self.db, link_id=identity, employee_id=person.id)
        links = list(self.db.scalars(select(m.EmployeeCloverLink)))
        self.assertIn("duplicate_accounts", directory.source_conflicts(links))
        self.sync([{"id": "A", "name": "Pinco Pallino"}])
        self.assertEqual(directory.source_conflicts(links), {})
        self.assertEqual(directory.source_absence_link_ids(links), set())
        self.assertEqual(len(links), 2)
        self.assertTrue(directory.employee_is_active(person, links))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 1)
        self.assertGreater(self.db.scalar(select(func.count()).select_from(m.EmployeeDirectoryEvent)), 0)

    def test_historical_unknown_requires_confirmation_without_creating_person(self):
        arguments = dict(location_id=self.site.id, merchant_id="WP", raw={"id": "OLD", "name": "Former"},
                         available=False, observed_at=datetime.now(timezone.utc), run_id=None)
        for _ in range(2):
            self.assertIsNone(directory.observe_historical_employee(self.db, **arguments))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 0)
        link = self.db.scalar(select(m.EmployeeCloverLink))
        person = self.person()
        link.last_clock_in = datetime(2026, 10, 1, tzinfo=timezone.utc)
        directory.attach_link(self.db, link_id=link.id, employee_id=person.id)
        self.assertEqual(directory.observe_historical_employee(self.db, **arguments).id, person.id)

    def test_removed_unconfirmed_source_record_leaves_current_queue_but_history_remains(self):
        _, pending = self.sync([{"id": "TEMP", "name": "Temporary typo"}])
        link = self.db.get(m.EmployeeCloverLink, pending[0])
        self.assertTrue(directory.pending_requires_review(self.db, link))
        self.sync([])
        self.assertFalse(directory.pending_requires_review(self.db, link))
        self.assertIsNotNone(self.db.get(m.EmployeeCloverLink, link.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 0)

    def test_reversed_names_are_suggestions_only(self):
        person = self.person("Pinco Pallino")
        _, pending = self.sync([{"id": "REVERSED", "name": "Pallino Pinco"}])
        self.assertEqual(len(pending), 1)
        self.assertEqual(directory.candidates(self.db, {"name": "Pallino Pinco"})[0]["employee"].id, person.id)
        self.assertIsNone(self.db.get(m.EmployeeCloverLink, pending[0]).employee_id)

    def test_historical_import_failure_preserves_pending_identity_and_no_work(self):
        from rfone_data_store.clover_acquisition_validation import FakeCloverClient
        from rfone_data_store.technical.connectors.clover import acquisition as acquisition
        client = FakeCloverClient("WP")
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        client.payments = [{"id": "PENDING-PAYMENT", "employee": {"id": "HISTORICAL-UNKNOWN"},
                            "createdTime": int(now.timestamp() * 1000), "amount": 100, "result": "SUCCESS"}]
        location_id = self.site.id
        self.db.commit()
        client.shifts = [{"id": "HISTORICAL-SHIFT", "employee": {"id": "HISTORICAL-UNKNOWN"}, "inTime": int(now.timestamp() * 1000)}]
        summary = acquisition.import_clover_period(self.db, location_id=location_id,
                period_start=now, period_end=now, mode="LIVE_SYNC", client=client)
        self.assertTrue(summary.errors)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Payment)), 0)
        link = self.db.scalar(select(m.EmployeeCloverLink))
        self.assertIsNotNone(link)
        self.assertIsNone(link.employee_id)
        self.assertTrue(directory.pending_requires_review(self.db, link))
        self.assertEqual(self.db.scalar(select(m.IngestionRun.status)), "FAILED")

    def test_existing_authentication_bridge_resolves_person_without_grants(self):
        person, other = self.person(), self.person("Other")
        targets = self.contexts()
        self.db.add(m.RFOneTrainingIdentityLink(rfone_account_id=targets["RFONE_ACCOUNT"].id,
                                              training_account_id=targets["TRAINING"].id))
        self.db.flush()
        directory.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=targets["RFONE_ACCOUNT"].id)
        self.assertEqual(directory.context_person_id(self.db, "TRAINING", targets["TRAINING"].id), person.id)
        self.assertEqual(directory.context_person_id(self.db, "ACTING_IDENTITY", targets["ACTING_IDENTITY"].id), person.id)
        with self.assertRaises(ValueError):
            directory.link_context(self.db, employee_id=other.id, kind="TRAINING", target_id=targets["TRAINING"].id)
        self.assertIsNone(directory.context_person_id(self.db, "CANDIDATE", None))

    def contexts(self):
        account = m.RFOneAccount(username="person", display_name="Account label", password_hash="test", status="ACTIVE")
        actor = m.ActingIdentity(kind="HUMAN_USER", display_name="Acting label")
        candidate = m.CandidatePerson(full_name="Candidate label")
        project = projects.create_project(self.db, name="Project")
        responsible = projects.create_responsible(self.db, project.id, name="External label")
        self.db.add_all([account, actor, candidate]); self.db.flush()
        training = m.TrainingAccount(username="learner", role="student", acting_identity_id=actor.id, password_hash="test")
        self.db.add(training); self.db.flush()
        return {"RFONE_ACCOUNT": account, "ACTING_IDENTITY": actor, "TRAINING": training,
                "CANDIDATE": candidate, "PROJECT_RESPONSIBLE": responsible}

    def test_all_contexts_link_explicitly_without_grants_or_domain_rewrites(self):
        person = self.person()
        targets = self.contexts()
        for kind, target in targets.items():
            self.assertIn(directory.context_person_id(self.db, kind, target.id), (None, person.id))
            link = directory.link_context(self.db, employee_id=person.id, kind=kind, target_id=target.id)
            self.assertEqual(directory.link_context(self.db, employee_id=person.id, kind=kind, target_id=target.id).id, link.id)
            self.assertEqual(directory.context_person_id(self.db, kind, target.id), person.id)
        self.assertEqual(targets["CANDIDATE"].full_name, "Candidate label")
        self.assertEqual(targets["RFONE_ACCOUNT"].display_name, "Account label")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.AuthorityGrant)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess)), 0)
        other = self.person("Another person")
        with self.assertRaises(ValueError):
            directory.link_context(self.db, employee_id=other.id, kind="CANDIDATE", target_id=targets["CANDIDATE"].id)

    def test_context_unlink_is_explicit_audited_and_does_not_delete_target(self):
        person = self.person()
        target = m.CandidatePerson(full_name="Candidate")
        self.db.add(target); self.db.flush()
        link = directory.link_context(self.db, employee_id=person.id, kind="CANDIDATE", target_id=target.id)
        directory.unlink_context(self.db, employee_id=person.id, link_id=link.id)
        self.assertIsNotNone(self.db.get(m.CandidatePerson, target.id))
        self.assertIsNone(directory.context_person_id(self.db, "CANDIDATE", target.id))
        self.assertEqual(list(self.db.scalars(select(m.EmployeeDirectoryEvent.action)))[-1], "CONTEXT_UNLINK")

    def test_nonhuman_identity_and_conflicting_training_links_are_refused(self):
        person, other = self.person(), self.person("Other")
        targets = self.contexts()
        directory.link_context(self.db, employee_id=person.id, kind="ACTING_IDENTITY", target_id=targets["ACTING_IDENTITY"].id)
        with self.assertRaises(ValueError):
            directory.link_context(self.db, employee_id=other.id, kind="TRAINING", target_id=targets["TRAINING"].id)
        actor = m.ActingIdentity(kind="AI_AGENT", display_name="Agent")
        self.db.add(actor); self.db.flush()
        with self.assertRaises(ValueError):
            directory.link_context(self.db, employee_id=person.id, kind="ACTING_IDENTITY", target_id=actor.id)

    def test_bank_new_assignments_resolve_confirmed_actor_and_retired_id(self):
        person = self.person()
        actor = m.ActingIdentity(kind="HUMAN_USER", display_name="Different label")
        retired = self.person("Old copy")
        self.db.add(actor); self.db.flush()
        directory.link_context(self.db, employee_id=person.id, kind="ACTING_IDENTITY", target_id=actor.id)
        directory.consolidate(self.db, from_employee_id=retired.id, into_employee_id=person.id)
        for kind, actor_id, person_id in ((m.CARD_HOLDER_KIND_ACTING_IDENTITY, actor.id, None),
                                        (m.CARD_HOLDER_KIND_EMPLOYEE, None, retired.id)):
            holder = cards._validated_holder(self.db, holder_kind=kind, holder_acting_identity_id=actor_id,
                holder_employee_id=person_id, holder_display_name=None)
            self.assertEqual(holder["holder_employee_id"], person.id)
            self.assertEqual(holder["holder_display_name"], person.display_name)
        choices = cardholder_candidates(self.db)
        self.assertEqual([(choice["kind"], choice["id"]) for choice in choices], [(m.CARD_HOLDER_KIND_EMPLOYEE, person.id)])

    def test_project_uses_reference_identity_preserves_local_label_and_external_people(self):
        person = self.person("Reference Name")
        project = projects.create_project(self.db, name="Independent Project")
        responsible = projects.create_responsible(self.db, project.id, name="", employee_id=person.id)
        self.assertEqual(projects.create_responsible(self.db, project.id, name="", employee_id=person.id).id, responsible.id)
        person.display_name = "Updated Reference"
        self.db.flush()
        self.assertEqual(projects.list_responsibles(self.db, project.id)[0].name, "Updated Reference")
        self.assertEqual(responsible.name, "Reference Name")
        with self.assertRaises(projects.ProjectValidationError):
            projects.rename_responsible(self.db, project.id, responsible.id, name="Silent edit")
        external = projects.create_responsible(self.db, project.id, name="External")
        self.assertIsNone(directory.context_person_id(self.db, "PROJECT_RESPONSIBLE", external.id))
        projects.delete_project(self.db, project.id)
        self.assertIsNotNone(self.db.get(m.Employee, person.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.EmployeeContextLink).where(m.EmployeeContextLink.rfone_account_id.is_(None))), 0)

    def test_project_homonyms_require_id_and_keep_native_identity(self):
        first, second = self.person("Equal Name"), self.person("Equal Name")
        project = projects.create_project(self.db, name="Homonyms")
        one = projects.create_responsible(self.db, project.id, name="", employee_id=first.id)
        two = projects.create_responsible(self.db, project.id, name="", employee_id=second.id)
        self.assertNotEqual(one.id, two.id)
        with self.assertRaises(projects.ProjectValidationError):
            projects._resolve_responsible(self.db, project.id, "Equal Name")
        self.assertEqual(projects._resolve_responsible(self.db, project.id, "", two.id), two.id)

    def test_context_database_enforces_exactly_one_target(self):
        person = self.person()
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(m.EmployeeContextLink(employee_id=person.id))
                self.db.flush()


if __name__ == "__main__":
    unittest.main(verbosity=2)
