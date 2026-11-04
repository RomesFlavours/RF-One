"""Employee lifecycle acceptance. Disposable SQLite and fake source only."""
import unittest
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m, employee_directory as d, rfone_web_session as auth
from rfone_data_store.database import create_configured_engine, create_session_factory

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
MS = int(NOW.timestamp() * 1000)

class EmployeeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        source = m.SourceSystem(code="CLOVER", name="Clover")
        self.db.add(source); self.db.flush()
        merchant = m.Merchant(name="Test", source_system_id=source.id, source_merchant_id="WP")
        self.db.add(merchant); self.db.flush()
        self.wp = m.Location(name="WP", merchant_id=merchant.id, source_system_id=source.id, source_location_id="WP")
        self.md = m.Location(name="MD", merchant_id=merchant.id, source_system_id=source.id, source_location_id="MD")
        self.db.add_all([self.wp, self.md]); self.db.flush()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def sync(self, ids, *, site=None, clocks=None, **kw):
        site = site or self.wp
        return d.import_snapshot(self.db, location_id=site.id, merchant_id=site.source_location_id,
            records=[{"id": identity, "name": "Source " + identity} for identity in ids],
            clock_records=clocks if clocks is not None else [self.clock(identity) for identity in ids], **kw)

    def clock(self, identity, *, out=False):
        return {"id": "shift-" + identity, "employee": {"id": identity}, "inTime": None if out else MS,
                "outTime": MS + 60000 if out else None}

    def person(self, identity="A", site=None):
        _, pending = self.sync([identity], site=site)
        return d.attach_link(self.db, link_id=pending[0], create_new=True)

    def account(self, person):
        return d.ensure_employee_account(self.db, person)

    def test_no_clocks_never_registers_or_provisions_account(self):
        _, pending = self.sync(["NO-CLOCKS"], clocks=[])
        self.assertEqual(pending, [])
        link = self.db.scalar(select(m.EmployeeCloverLink))
        with self.assertRaises(ValueError): d.attach_link(self.db, link_id=link.id, create_new=True)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), 0)

    def test_two_sites_one_ends_other_keeps_person_and_choices(self):
        person = self.person()
        _, pending = self.sync(["B"], site=self.md)
        d.attach_link(self.db, link_id=pending[0], employee_id=person.id)
        account = self.account(person); account.status = "ACTIVE"; self.db.flush()
        self.sync([], clocks=[self.clock("A")])
        self.assertTrue(person.active)
        self.assertEqual(account.status, "ACTIVE")
        self.assertEqual(d.employee_options(self.db, location_ids=[self.wp.id]), [])
        self.assertEqual([x.id for x in d.employee_options(self.db, location_ids=[self.md.id])], [person.id])
        self.assertEqual({x.state for x in self.db.scalars(select(m.EmployeeCloverLink))}, {"PRESENT", "DISMISSED"})

    def test_last_position_ends_at_clock_in_without_clock_out_and_revokes_session(self):
        person = self.person(); account = self.account(person); account.status = "ACTIVE"; self.db.flush()
        version = account.session_version
        self.assertIsNotNone(auth.account_for_session(self.db, account_id=account.id, session_version=version))
        self.sync([], clocks=[self.clock("A")])
        self.assertFalse(person.active)
        self.assertEqual(d._utc(person.dismissed_at), NOW)
        self.assertEqual(account.status, "INACTIVE")
        self.assertGreater(account.session_version, version)
        self.assertIsNone(auth.account_for_session(self.db, account_id=account.id, session_version=version))
        self.assertEqual(d.employee_options(self.db), [])
        with self.assertRaises(ValueError): d.require_active_employee(self.db, person.id)
        self.assertEqual(d.employee_options(self.db, include_inactive=True)[0].id, person.id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 1)

    def test_out_only_eligible_but_no_fabricated_clock_in_date(self):
        _, pending = self.sync(["A"], clocks=[self.clock("A", out=True)])
        person = d.attach_link(self.db, link_id=pending[0], create_new=True)
        self.sync([], clocks=[self.clock("A", out=True)])
        self.assertFalse(person.active); self.assertIsNone(person.dismissed_at)

    def test_invalid_partial_and_rolled_back_scans_cannot_terminate(self):
        person = self.person(); self.db.commit()
        for kw in ({"complete": False}, {"clocks": [{"employee": {"id": "A"}, "inTime": "invalid"}]}):
            with self.assertRaises(ValueError): self.sync([], **kw)
            self.assertTrue(person.active)
        self.sync([], clocks=[self.clock("A")]); self.db.rollback()
        self.assertTrue(person.active)
        self.assertEqual(self.db.scalar(select(m.EmployeeCloverLink.state)), "PRESENT")

    def test_unverified_second_site_does_not_cause_global_dismissal(self):
        person = self.person()
        self.db.add(m.EmployeeCloverLink(employee_id=person.id, location_id=self.md.id,
            merchant_id="MD", external_employee_id="B", state="UNVERIFIED"))
        self.db.flush(); self.sync([], clocks=[self.clock("A")])
        self.assertTrue(person.active)

    def test_duplicate_accounts_at_one_site_do_not_end_live_position(self):
        person = self.person()
        _, pending = self.sync(["A", "B"])
        d.attach_link(self.db, link_id=pending[0], employee_id=person.id)
        self.sync(["B"], clocks=[self.clock("A"), self.clock("B")])
        self.assertTrue(person.active)
        self.assertEqual(d.source_absence_link_ids(list(self.db.scalars(select(m.EmployeeCloverLink)))), set())

    def test_repeat_scans_and_rehire_do_not_duplicate_or_reactivate_account(self):
        person = self.person(); account = self.account(person); account.status = "ACTIVE"; self.db.flush()
        for _ in range(2): self.sync([], clocks=[self.clock("A")])
        version = account.session_version
        self.sync(["A"])
        self.assertTrue(person.active); self.assertIsNone(person.dismissed_at)
        self.assertEqual(account.status, "INACTIVE"); self.assertEqual(account.session_version, version)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), 1)

    def test_external_account_unaffected_and_native_employee_has_shell(self):
        external = m.RFOneAccount(username="shelbi", display_name="Shelbi", password_hash="!", status="ACTIVE", session_version=1)
        self.db.add(external); self.db.flush()
        self.sync([], clocks=[])
        self.assertTrue(d.account_employee_allows_access(self.db, external.id))
        person = d.create_person(self.db, display_name="Native")
        account = self.account(person)
        self.assertEqual(account.password_hash, "!"); self.assertIsNone(account.email)
        self.assertEqual(account.status, "INACTIVE")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess)), 0)

    def test_account_one_to_one_and_mandatory_link(self):
        person = self.person(); account = self.account(person)
        link = self.db.scalar(select(m.EmployeeContextLink).where(m.EmployeeContextLink.rfone_account_id == account.id))
        with self.assertRaises(ValueError): d.unlink_context(self.db, employee_id=person.id, link_id=link.id)
        extra = m.RFOneAccount(username="extra", display_name="Extra", password_hash="!", status="INACTIVE")
        self.db.add(extra); self.db.flush()
        with self.assertRaises(IntegrityError), self.db.begin_nested():
            self.db.add(m.EmployeeContextLink(employee_id=person.id, rfone_account_id=extra.id)); self.db.flush()

    def test_historical_only_clock_identity_stays_pending_until_approval(self):
        _, pending = self.sync([], clocks=[self.clock("OLD")])
        self.assertEqual(len(pending), 1)
        person = d.attach_link(self.db, link_id=pending[0], create_new=True)
        self.assertFalse(person.active)
        self.assertEqual(d._utc(person.dismissed_at), NOW)
        self.assertEqual(d.employee_options(self.db), [])

    def test_old_rendered_interview_recipient_is_rejected_after_dismissal(self):
        person = self.person(); choice = d.employee_options(self.db)[0]
        self.sync([], clocks=[self.clock("A")])
        with self.assertRaises(ValueError): d.require_active_employee(self.db, choice.id)


    def test_migration_refuses_existing_multiple_accounts_before_any_change(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        person = self.person(); first = self.account(person)
        second = m.RFOneAccount(username="second", display_name="Second", password_hash="!", status="INACTIVE")
        self.db.add(second); self.db.flush()
        self.db.connection().exec_driver_sql("DROP INDEX uq_employee_one_rfone_account")
        self.db.add(m.EmployeeContextLink(employee_id=person.id, rfone_account_id=second.id)); self.db.flush()
        path = Path(__file__).parent / "migrations/versions/e3f120261103_employee_lifecycle.py"
        spec = importlib.util.spec_from_file_location("lifecycle_migration", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module.op = Operations(MigrationContext.configure(self.db.connection()))
        count = self.db.scalar(select(func.count()).select_from(m.RFOneAccount))
        with self.assertRaisesRegex(RuntimeError, "Multiple RF1 accounts"):
            module.upgrade()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), count)

    def test_operational_accounts_cannot_be_multiply_linked_and_external_is_confirmed(self):
        person = self.person()
        target = m.RFOneAccount(username="existing", display_name="Existing", password_hash="real-hash", status="ACTIVE")
        self.db.add(target); self.db.flush()
        d.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=target.id)
        self.assertEqual(d.ensure_employee_account(self.db, person).id, target.id)
        second = m.RFOneAccount(username="another", display_name="Another", password_hash="real-hash", status="ACTIVE")
        self.db.add(second); self.db.flush()
        with self.assertRaises(ValueError):
            d.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=second.id)
        self.assertEqual(d.ensure_employee_account(self.db, person).id, target.id)

    def test_confirmed_training_bridge_reuses_existing_account_and_blocks_training_on_dismissal(self):
        from rfone_data_store.training import service as training
        person = m.Employee(display_name="Legacy person", active=True)
        account = m.RFOneAccount(username="legacy-account", display_name="Legacy", password_hash="!", status="ACTIVE")
        actor = m.ActingIdentity(kind="HUMAN_USER", display_name="Legacy")
        self.db.add_all([person, account, actor]); self.db.flush()
        student = m.TrainingAccount(username="legacy-student", role="student", acting_identity_id=actor.id, password_hash="!")
        self.db.add(student); self.db.flush()
        self.db.add(m.RFOneTrainingIdentityLink(rfone_account_id=account.id, training_account_id=student.id))
        self.db.add(m.EmployeeContextLink(employee_id=person.id, training_account_id=student.id)); self.db.flush()
        self.assertEqual(d.ensure_employee_account(self.db, person).id, account.id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), 1)
        self.assertEqual([a.id for a in training.list_all_students(self.db)], [student.id])
        d.update_management(self.db, person, display_name=person.display_name, custom_id="", active=False, account_id=None)
        self.assertEqual(training.list_all_students(self.db), [])
        self.assertFalse(d.context_employee_allows_access(self.db, "TRAINING", student.id))
        self.assertIsNotNone(training.get_account(self.db, student.id))  # History survives.

    # --- Review completion (2026-11-03) -----------------------------------

    def test_pending_clock_identity_suspends_cessation_until_attributed(self):
        person = self.person(); account = self.account(person); account.status = "ACTIVE"; self.db.flush()
        _, pending = self.sync([], clocks=[self.clock("A"), self.clock("NEW")])
        link = self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "A"))
        self.assertEqual(link.state, "MISSING_REVIEW")  # suspended, not ended
        self.assertTrue(person.active); self.assertEqual(account.status, "ACTIVE")
        self.assertEqual([x.id for x in d.employee_options(self.db)], [person.id])
        self.assertFalse(d.clock_scan_due(self.db, merchant_id="WP", roster_ids=[], now=NOW))
        d.attach_link(self.db, link_id=pending[0], employee_id=person.id)  # NEW was A's other account
        self.assertTrue(d.clock_scan_due(self.db, merchant_id="WP", roster_ids=[], now=NOW))
        self.sync([], clocks=[self.clock("A"), self.clock("NEW")])
        self.assertFalse(person.active); self.assertEqual(account.status, "INACTIVE")

    def test_retained_clock_survives_source_retention(self):
        person = self.person()
        self.sync(["A"], clocks=[])  # Clover aged out every shift
        link = self.db.scalar(select(m.EmployeeCloverLink))
        self.assertEqual(d._utc(link.last_clock_in), NOW)
        self.sync([], clocks=[])
        self.assertEqual(d._utc(person.dismissed_at), NOW)

    def test_offline_snapshot_records_evidence_but_never_ends_positions(self):
        person = self.person()
        later = {"employee": {"id": "A"}, "inTime": MS + 3600000}
        self.sync([], clocks=[later], clock_decisions=False)
        link = self.db.scalar(select(m.EmployeeCloverLink))
        self.assertEqual(link.state, "MISSING_REVIEW"); self.assertTrue(person.active)
        self.assertEqual(d._utc(link.last_clock_in).hour, 13)

    def test_owner_account_is_never_locked_out_by_dismissal(self):
        person = self.person()
        owner = m.RFOneAccount(username="owner", display_name="Owner", password_hash="real", status="ACTIVE",
                               is_admin=True, is_owner=True, session_version=1)
        self.db.add(owner); self.db.flush()
        d.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=owner.id)
        self.sync([], clocks=[self.clock("A")])
        self.assertFalse(person.active)
        self.assertEqual((owner.status, owner.session_version), ("ACTIVE", 1))
        self.assertTrue(d.account_employee_allows_access(self.db, owner.id))
        protected = select(func.count()).select_from(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.action == "OWNER_ACCESS_PROTECTED")
        self.assertEqual(self.db.scalar(protected), 1)
        self.sync([], clocks=[self.clock("A")])  # repeated scans do not repeat the event
        self.assertEqual(self.db.scalar(protected), 1)
        # PO decision 2026-11-03: the exception covers access only. The person stays dismissed.
        self.assertFalse(d.employee_is_active(person, []))
        self.assertIsNotNone(person.dismissed_at)
        self.assertEqual(d.employee_options(self.db), [])
        self.assertEqual(d.employee_options(self.db), [])
        with self.assertRaises(ValueError):
            d.require_active_employee(self.db, person.id)
        self.assertEqual([x.id for x in d.employee_options(self.db, include_inactive=True)], [person.id])
        self.assertIsNotNone(auth.account_for_session(self.db, account_id=owner.id, session_version=1))

    def test_replaced_provisional_account_stays_inactive_unlinked_and_unusable(self):
        from rfone_data_store import rfone_account_service as accounts
        person = self.person(); shell = self.account(person)
        real = m.RFOneAccount(username="real-staff", display_name="Real", password_hash="real-hash", status="ACTIVE")
        self.db.add(real); self.db.flush()
        d.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=real.id)
        self.assertIsNotNone(self.db.get(m.RFOneAccount, shell.id))  # retained, never deleted
        self.assertEqual((shell.status, shell.password_hash, shell.email), ("INACTIVE", "!", None))
        self.assertIsNone(d.context_person_id(self.db, "RFONE_ACCOUNT", shell.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess).where(
            m.RFOneAccountDomainAccess.account_id == shell.id)), 0)
        for password in ("", "!", "anything"):
            self.assertIsNone(accounts.verify_login(self.db, shell.username, password).account)
        self.assertIsNone(auth.account_for_session(self.db, account_id=shell.id, session_version=shell.session_version))
        event = self.db.scalar(select(m.EmployeeDirectoryEvent).where(m.EmployeeDirectoryEvent.action == "ACCOUNT_REPLACED"))
        self.assertEqual((event.employee_id, event.details), (person.id,
                         {"previous_account_id": shell.id, "account_id": real.id}))
        # An orphaned shell can never be attached again as someone's real account.
        other = self.person("B", site=self.md)
        with self.assertRaises(ValueError):
            d.link_context(self.db, employee_id=other.id, kind="RFONE_ACCOUNT", target_id=shell.id)

    def test_reenabling_account_of_dismissed_person_still_blocks_access(self):
        person = self.person(); account = self.account(person)
        self.sync([], clocks=[self.clock("A")])
        account.status = "ACTIVE"; self.db.flush()  # e.g. an administrator in Accounts
        self.assertFalse(d.account_employee_allows_access(self.db, account.id))
        self.assertIsNone(auth.account_for_session(self.db, account_id=account.id, session_version=account.session_version))

    def test_native_manual_dismissal_and_reactivation_do_not_restore_access(self):
        person = d.create_person(self.db, display_name="Native")
        account = self.account(person); account.status = "ACTIVE"; self.db.flush()
        d.update_management(self.db, person, display_name="Native", custom_id="", active=False, account_id=None)
        self.assertEqual(account.status, "INACTIVE")
        self.assertEqual(d.employee_options(self.db), [])
        d.update_management(self.db, person, display_name="Native", custom_id="", active=True, account_id=None)
        self.assertEqual(account.status, "INACTIVE")
        self.assertEqual([x.id for x in d.employee_options(self.db)], [person.id])

    def test_clock_linked_status_cannot_be_overridden_manually(self):
        person = self.person()
        with self.assertRaises(ValueError):
            d.update_management(self.db, person, display_name="X", custom_id="", active=False, account_id=None)

    def test_interview_scope_cannot_be_widened_and_aliases_resolve(self):
        person = self.person(); other = self.person("B", site=self.md)
        self.assertEqual(d.employee_options(self.db, location_ids=[]), [])
        self.assertEqual([x.id for x in d.employee_options(self.db, location_ids=[self.md.id])], [other.id])
        # Shared Interview contract: the scope is always stated by the caller.
        self.assertEqual(d.interview_employee_options(self.db, location_ids=[]), [])
        self.assertEqual([x.id for x in d.interview_employee_options(self.db, location_ids=[self.md.id])], [other.id])
        self.assertEqual({x.id for x in d.interview_employee_options(self.db, location_ids=None)}, {person.id, other.id})
        with self.assertRaises(TypeError):
            d.interview_employee_options(self.db)
        with self.assertRaises(ValueError):
            d.require_active_employee(self.db, person.id, location_ids=[self.md.id])
        with self.assertRaises(ValueError):
            d.require_active_employee(self.db, person.id, location_ids=[])
        d.consolidate(self.db, from_employee_id=other.id, into_employee_id=person.id)
        self.assertEqual(d.require_active_employee(self.db, other.id, location_ids=[self.md.id]).id, person.id)

    def test_consolidation_keeps_operational_account_and_refuses_two(self):
        first, second = self.person(), self.person("B", site=self.md)
        self.account(first)
        real = m.RFOneAccount(username="real", display_name="Real", password_hash="real-hash", status="ACTIVE")
        self.db.add(real); self.db.flush()
        d.link_context(self.db, employee_id=second.id, kind="RFONE_ACCOUNT", target_id=real.id)
        d.consolidate(self.db, from_employee_id=second.id, into_employee_id=first.id)
        self.assertEqual(d.employee_account(self.db, first.id).id, real.id)
        third = self.person("C")
        other_real = m.RFOneAccount(username="real2", display_name="Real2", password_hash="real-hash", status="ACTIVE")
        self.db.add(other_real); self.db.flush()
        d.link_context(self.db, employee_id=third.id, kind="RFONE_ACCOUNT", target_id=other_real.id)
        with self.assertRaisesRegex(ValueError, "operational RF1 accounts"):
            d.consolidate(self.db, from_employee_id=third.id, into_employee_id=first.id)
        self.assertEqual(d.employee_account(self.db, third.id).id, other_real.id)

    def test_training_refuses_new_work_for_dismissed_student_but_keeps_history(self):
        from rfone_data_store.training import service as training
        person = self.person()
        actor = m.ActingIdentity(kind="HUMAN_USER", display_name="Student")
        self.db.add(actor); self.db.flush()
        student = m.TrainingAccount(username="student", role="student", acting_identity_id=actor.id, password_hash="!")
        self.db.add(student); self.db.flush()
        d.link_context(self.db, employee_id=person.id, kind="TRAINING", target_id=student.id)
        need = training.create_need(self.db, student_account_id=student.id, text="Before", origin=None,
                                    created_by_account_id=student.id)
        self.sync([], clocks=[self.clock("A")])
        with self.assertRaises(ValueError):
            training.create_need(self.db, student_account_id=student.id, text="After", origin=None,
                                 created_by_account_id=student.id)
        with self.assertRaises(ValueError):
            training.assign_pills_bulk(self.db, need_id=need.id, pill_ids=[1], assigned_by_account_id=student.id)
        self.assertEqual([a.id for a in training.list_all_students(self.db, dismissed=True)], [student.id])
        self.assertEqual(training.list_all_students(self.db), [])
        self.assertIsNotNone(self.db.get(m.TrainingNeed, need.id))

    def test_no_clock_legacy_person_becomes_technical_observation(self):
        person = m.Employee(display_name="Legacy no clocks", location_id=self.wp.id,
                            source_system_id=self.wp.source_system_id, source_employee_id="LEGACY")
        self.db.add(person); self.db.flush()
        self.sync(["LEGACY"], clocks=[])
        self.assertFalse(person.directory_eligible)
        self.assertEqual(d.employee_options(self.db), [])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), 1)

    def test_fetch_reference_catalogs_reuses_the_single_shift_read(self):
        from rfone_data_store.clover_acquisition_validation import FakeCloverClient
        from rfone_data_store.technical.connectors.clover import acquisition
        client = FakeCloverClient("WP")
        client.employees = [{"id": "A", "name": "Source A"}]
        from unittest.mock import patch
        with patch.object(acquisition, "_mirror_source_record"):
            acquisition._fetch_reference_catalogs(client, self.db, location_id=self.wp.id,
                source_system_id=self.wp.source_system_id, ingestion_run_id=None, retrieved_at=NOW,
                mode="LIVE_SYNC", shifts_raw=[self.clock("A")])
        self.assertFalse([path for path, _ in client.calls if path.endswith("/shifts")])
        self.assertTrue(d.has_clock_evidence(self.db.scalar(select(m.EmployeeCloverLink))))
