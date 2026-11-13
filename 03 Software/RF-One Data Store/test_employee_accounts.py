"""EMPLOYEE_ACCOUNTS_001 acceptance: positions per site, cessation, admission,
one RF-One account per employee, external accounts, session revocation and
shared selectors. Disposable SQLite only, fake Clover rosters only.
"""
from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import models as m
from rfone_data_store import employee_directory as directory
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store import rfone_web_session as sessions
from rfone_data_store.database import create_configured_engine, create_session_factory

UTC = timezone.utc
PASSWORD = "correct-horse-battery-1"
T0 = datetime(2026, 10, 1, 14, tzinfo=UTC)


class EmployeeAccountsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover")
        self.db.add(self.source)
        self.db.flush()
        merchant = m.Merchant(name="Test Merchant", source_system_id=self.source.id, source_merchant_id="WP")
        self.db.add(merchant)
        self.db.flush()
        self.wp = m.Location(name="Winter Park", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="WP", timezone="America/New_York")
        self.md = m.Location(name="Mount Dora", merchant_id=merchant.id, source_system_id=self.source.id,
                             source_location_id="MD", timezone="America/New_York")
        self.db.add_all([self.wp, self.md])
        self.db.flush()
        # A colleague keeps both rosters non-empty, as in reality.
        self.colleague = self.employee("Colleague Kept", wp="C1", md="C2")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # --- helpers ---------------------------------------------------------
    def roster(self, location, *external_ids, complete=True):
        return directory.import_snapshot(self.db, location_id=location.id, merchant_id=location.source_location_id,
                                         records=[{"id": e, "name": e} for e in external_ids], complete=complete)

    def employee(self, name, *, wp=None, md=None, shifts=True):
        """A confirmed person with Clover records at the given sites and clock-ins there."""
        person = directory.create_person(self.db, display_name=name)
        for location, external_id in ((self.wp, wp), (self.md, md)):
            if external_id is None:
                continue
            link = m.EmployeeCloverLink(employee_id=person.id, location_id=location.id,
                                       merchant_id=location.source_location_id,
                                       external_employee_id=external_id, state="PRESENT")
            self.db.add(link)
            if shifts:
                self.shift(person, location, T0)
        self.db.flush()
        return person

    def shift(self, person, location, clock_in, clock_out="auto"):
        out = clock_in + timedelta(hours=6) if clock_out == "auto" else clock_out
        self.db.add(m.Shift(employee_id=person.id, location_id=location.id if location else None,
                            source_system_id=self.source.id, clock_in=clock_in, clock_out=out,
                            source_shift_id=f"S-{person.id}-{clock_in.timestamp()}-{location.id if location else 0}"))
        self.db.flush()

    def account(self, username, *, person=None, **kwargs):
        account = accounts.create_account(self.db, username=username, display_name=username, password=PASSWORD,
                                          email=f"{username}@example.test", **kwargs)
        if person is not None:
            directory.link_context(self.db, employee_id=person.id, kind="RFONE_ACCOUNT", target_id=account.id)
        return account

    def state(self, person):
        return directory.employment_states(self.db, [person.id])[person.id]

    def events(self, person, action):
        return list(self.db.scalars(select(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.employee_id == person.id, m.EmployeeDirectoryEvent.action == action)))

    def hold_shift(self, location, external_id, in_time=T0):
        run = m.IngestionRun(source_system_id=self.source.id, location_id=location.id, status="COMPLETE", started_at=in_time)
        self.db.add(run)
        self.db.flush()
        self.db.add(m.SourceRecord(ingestion_run_id=run.id, source_system_id=self.source.id, entity_type="shift",
                                   source_id=f"HELD-{external_id}", retrieved_at=in_time,
                                   raw_json={"id": f"HELD-{external_id}", "employee": {"id": external_id},
                                             "inTime": int(in_time.timestamp() * 1000)}))
        self.db.flush()

    # --- 1. presence and cessation per site ------------------------------
    def test_removed_from_one_site_ends_only_that_position(self):
        anna = self.employee("Anna Two Sites", wp="A-WP", md="A-MD")
        self.shift(anna, self.md, T0 + timedelta(days=3))
        login = self.account("anna", person=anna)
        self.roster(self.wp, "C1", "A-WP")
        self.roster(self.md, "C2")  # Anna no longer in Mount Dora
        state = self.state(anna)
        positions = {p.location_id: p for p in state.positions}
        self.assertEqual(positions[self.md.id].status, directory.POSITION_ENDED)
        self.assertEqual(positions[self.md.id].last_clock_in, T0 + timedelta(days=3))
        self.assertEqual(positions[self.wp.id].status, directory.POSITION_ACTIVE)
        self.assertEqual(state.status, directory.STATUS_ACTIVE)
        self.assertEqual((login.status, login.session_version), ("ACTIVE", 1))
        self.assertEqual([e.details["location_id"] for e in self.events(anna, "POSITION_END")], [self.md.id])
        self.assertFalse(self.events(anna, "CEASE"))
        # Current selectors keep her, with only the site where she still works.
        option = next(o for o in directory.employee_options(self.db) if o.id == anna.id)
        self.assertTrue(option.is_active)
        self.assertEqual(option.location_ids, (self.wp.id,))

    def test_removed_from_last_site_ceases_person_and_disables_access(self):
        bruno = self.employee("Bruno Last Site", wp="B-WP", md="B-MD")
        self.shift(bruno, self.wp, T0 + timedelta(days=9))  # last clock-in anywhere
        self.shift(bruno, self.md, T0 + timedelta(days=5))
        login = self.account("bruno", person=bruno)
        self.roster(self.md, "C2")
        self.assertEqual(self.state(bruno).status, directory.STATUS_ACTIVE)
        self.roster(self.wp, "C1")
        state = self.state(bruno)
        self.assertEqual(state.status, directory.STATUS_CEASED)
        self.assertEqual(state.ceased_at, T0 + timedelta(days=9))
        self.assertEqual((login.status, login.session_version), ("INACTIVE", 2))
        self.assertEqual(len(self.events(bruno, "CEASE")), 1)
        self.assertEqual(self.events(bruno, "ACCESS_DISABLED")[0].details["rfone_account_id"], login.id)
        # Person, account, links and work history are kept.
        self.assertIsNotNone(self.db.get(m.Employee, bruno.id))
        self.assertIsNotNone(self.db.get(m.RFOneAccount, login.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Shift).where(m.Shift.employee_id == bruno.id)), 4)
        self.assertEqual(directory.person_account(self.db, bruno.id).id, login.id)
        # Repeated imports change nothing more.
        self.roster(self.wp, "C1")
        self.assertEqual((len(self.events(bruno, "CEASE")), login.session_version), (1, 2))

    def test_last_clock_in_without_clock_out_is_the_cessation_date(self):
        carla = self.employee("Carla Open Shift", wp="CA")
        open_in = T0 + timedelta(days=20, hours=3)
        self.shift(carla, self.wp, open_in, clock_out=None)
        self.shift(carla, None, T0 + timedelta(days=2))  # site unknown, older
        self.roster(self.wp, "C1")
        state = self.state(carla)
        self.assertEqual(state.status, directory.STATUS_CEASED)
        self.assertEqual(state.ceased_at, open_in)
        self.assertEqual(state.positions[0].last_clock_in, open_in)

    def test_failed_or_incomplete_import_ceases_nobody(self):
        dario = self.employee("Dario Kept", wp="D1")
        login = self.account("dario", person=dario)
        with self.assertRaises(ValueError):
            self.roster(self.wp, "C1", complete=False)
        with self.assertRaises(ValueError):
            directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id="WP", records=[{"name": "no id"}])
        with self.assertRaises(ValueError):  # wrong merchant for the site
            directory.import_snapshot(self.db, location_id=self.wp.id, merchant_id="MD", records=[])
        self.assertEqual(self.state(dario).status, directory.STATUS_ACTIVE)
        self.assertEqual(login.status, "ACTIVE")
        self.assertFalse(self.events(dario, "POSITION_END"))

    def test_failed_transaction_publishes_no_cessation(self):
        elena = self.employee("Elena Rolled Back", wp="E1")
        login = self.account("elena", person=elena)
        self.db.commit()
        self.roster(self.wp, "C1")
        self.assertEqual(login.status, "INACTIVE")
        self.db.rollback()  # the acquisition run failed after the roster step
        self.assertEqual(self.db.get(m.RFOneAccount, login.id).status, "ACTIVE")
        self.assertEqual(self.state(elena).status, directory.STATUS_ACTIVE)

    def test_unconfigured_site_and_empty_roster_end_nothing(self):
        # Mount Dora never had a complete roster: its absences are not evidence.
        fabio = directory.create_person(self.db, display_name="Fabio MD Only")
        self.db.add(m.EmployeeCloverLink(employee_id=fabio.id, location_id=self.md.id, merchant_id="MD",
                                         external_employee_id="F-MD", state="MISSING_REVIEW"))
        self.db.query(m.EmployeeCloverLink).filter_by(merchant_id="MD", external_employee_id="C2").update(
            {"state": "UNVERIFIED"})
        self.shift(fabio, self.md, T0)
        self.assertEqual(self.state(fabio).status, directory.STATUS_ACTIVE)
        # An empty complete roster (e.g. a misconfigured read) ends nothing either.
        gina = self.employee("Gina WP", wp="G1")
        self.roster(self.wp)
        self.assertEqual(self.state(gina).status, directory.STATUS_ACTIVE)
        self.assertEqual(self.state(self.colleague).status, directory.STATUS_ACTIVE)

    def test_returning_person_is_active_again_but_access_needs_an_administrator(self):
        hugo = self.employee("Hugo Returns", wp="H1")
        login = self.account("hugo", person=hugo)
        self.roster(self.wp, "C1")
        self.assertEqual(login.status, "INACTIVE")
        self.roster(self.wp, "C1", "H1")
        self.assertEqual(self.state(hugo).status, directory.STATUS_ACTIVE)
        self.assertEqual(len(self.events(hugo, "REACTIVATE")), 1)
        self.assertEqual(len(self.events(hugo, "POSITION_REOPEN")), 1)
        self.assertEqual(login.status, "INACTIVE")  # never re-enabled by an import

    # --- 2. admission -------------------------------------------------------
    def test_clover_name_without_punches_is_not_registered(self):
        _, pending = self.roster(self.wp, "C1", "NO-PUNCH")
        link = self.db.get(m.EmployeeCloverLink, pending[0])
        self.assertEqual(directory.held_punch_counts(self.db, [link]), {})
        before = self.db.scalar(select(func.count()).select_from(m.Employee))
        with self.assertRaisesRegex(ValueError, "no clock-in or clock-out"):
            directory.attach_link(self.db, link_id=link.id, create_new=True)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)), before)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccount)), 0)
        # It can still be linked to an existing RF-One person, explicitly.
        directory.attach_link(self.db, link_id=link.id, employee_id=self.colleague.id)
        self.assertEqual(link.employee_id, self.colleague.id)

    def test_punches_allow_registration_only_after_explicit_approval(self):
        _, pending = self.roster(self.wp, "C1", "NEW-HIRE")
        self.hold_shift(self.wp, "NEW-HIRE")
        link = self.db.get(m.EmployeeCloverLink, pending[0])
        self.assertEqual(directory.held_punch_counts(self.db, [link]), {link.id: 1})
        self.assertIsNone(link.employee_id)  # punches never link automatically
        person = directory.attach_link(self.db, link_id=link.id, create_new=True)
        self.assertTrue(self.state(person).is_employee)
        self.assertIsNone(directory.person_account(self.db, person.id))  # no automatic account

    def test_several_pos_records_one_person_one_position_per_site(self):
        ivo = self.employee("Ivo Two Records", wp="I1")
        self.db.add(m.EmployeeCloverLink(employee_id=ivo.id, location_id=self.wp.id, merchant_id="WP",
                                         external_employee_id="I2", state="PRESENT"))
        self.db.flush()
        self.roster(self.wp, "C1", "I2")  # one of his two records disappears
        self.assertEqual([p.status for p in self.state(ivo).positions], [directory.POSITION_ACTIVE])
        self.roster(self.wp, "C1")
        self.assertEqual(self.state(ivo).status, directory.STATUS_CEASED)

    def test_confirming_an_absent_record_records_the_cessation_and_access(self):
        zeno = self.employee("Zeno No Clover Link")  # punches below, no Clover link yet
        self.shift(zeno, self.wp, T0)
        login = self.account("zeno", person=zeno)
        self.roster(self.wp, "C1", "Z-OLD")
        self.roster(self.wp, "C1")  # Z-OLD left the roster while still unconfirmed
        old = self.db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.external_employee_id == "Z-OLD"))
        directory.attach_link(self.db, link_id=old.id, employee_id=zeno.id)
        self.assertEqual(self.state(zeno).status, directory.STATUS_CEASED)
        self.assertEqual(len(self.events(zeno, "CEASE")), 1)
        self.assertEqual(login.status, "INACTIVE")

    # --- 3. one account per employee -----------------------------------------
    def test_one_account_per_person_and_one_person_per_account(self):
        luca = self.employee("Luca One Account", wp="L1")
        mara = self.employee("Mara Other", wp="M1")
        first = self.account("luca", person=luca)
        second = self.account("luca-two")
        with self.assertRaisesRegex(ValueError, "already has an RF-One account"):
            directory.link_context(self.db, employee_id=luca.id, kind="RFONE_ACCOUNT", target_id=second.id)
        with self.assertRaisesRegex(ValueError, "existing confirmed person association|Already linked to another person"):
            directory.link_context(self.db, employee_id=mara.id, kind="RFONE_ACCOUNT", target_id=first.id)
        # The database enforces it too.
        with self.assertRaises(IntegrityError), self.db.begin_nested():
            self.db.add(m.EmployeeContextLink(employee_id=luca.id, rfone_account_id=second.id))
            self.db.flush()
        self.assertEqual(directory.person_account(self.db, luca.id).id, first.id)
        # Linking grants nothing.
        self.assertFalse(accounts.list_domain_access_for_account(self.db, first.id))

    def test_consolidating_two_people_with_accounts_is_refused_entirely(self):
        nora = self.employee("Nora", wp="N1")
        copy = self.employee("Nora copy", md="N2")
        self.account("nora", person=nora)
        self.account("nora-copy", person=copy)
        with self.assertRaisesRegex(ValueError, "Nothing was moved"):
            directory.consolidate(self.db, from_employee_id=copy.id, into_employee_id=nora.id)
        self.assertEqual(directory.resolve_employee_id(self.db, copy.id), copy.id)
        # With one account only, the account follows the kept person.
        other = self.employee("Oreste copy", md="O2")
        oreste = self.employee("Oreste", wp="O1")
        login = self.account("oreste", person=other)
        directory.consolidate(self.db, from_employee_id=other.id, into_employee_id=oreste.id)
        self.assertEqual(directory.person_account(self.db, oreste.id).id, login.id)

    def test_linking_an_account_to_a_ceased_person_disables_it(self):
        pia = self.employee("Pia Ceased", wp="P1")
        self.roster(self.wp, "C1")
        login = self.account("pia", person=pia)
        self.assertEqual((login.status, login.session_version), ("INACTIVE", 2))

    def test_owner_and_last_administrator_are_never_disabled_automatically(self):
        owner_person = self.employee("Owner Person", wp="OW")
        owner = self.account("owner", person=owner_person, is_admin=True)
        owner.is_owner = True
        self.db.flush()
        self.roster(self.wp, "C1")
        self.roster(self.wp, "C1")
        self.assertEqual(owner.status, "ACTIVE")
        kept = self.events(owner_person, "ACCESS_KEPT")
        self.assertEqual([e.details["reason"] for e in kept], ["OWNER"])  # recorded once

    # --- 4. external accounts -------------------------------------------------
    def test_external_account_needs_no_person_and_ignores_clover(self):
        shelbi = self.account("shelbi")
        quinto = self.employee("Quinto", wp="Q1")
        self.account("quinto", person=quinto)
        self.roster(self.wp)
        self.roster(self.wp, "C1")
        self.assertEqual(shelbi.status, "ACTIVE")
        self.assertNotIn(shelbi.id, directory.account_person_ids(self.db))
        self.assertEqual(directory.enforce_cessation_access(self.db), [])

    # --- session revocation -------------------------------------------------------
    def test_sessions_of_a_ceased_person_end(self):
        rita = self.employee("Rita Session", wp="R1")
        login = self.account("rita", person=rita)
        self.db.commit()
        issued = login.session_version
        self.assertIsNotNone(sessions.account_for_session(self.db, account_id=login.id, session_version=issued))
        self.roster(self.wp, "C1")
        self.db.commit()
        self.assertIsNone(sessions.account_for_session(self.db, account_id=login.id, session_version=issued))
        # Even a cookie carrying the new version is refused while INACTIVE.
        self.assertIsNone(sessions.account_for_session(self.db, account_id=login.id,
                                                       session_version=login.session_version))
        self.assertFalse(sessions.account_may_enter_domain(self.db, login, "EMPLOYEES"))
        self.assertIsNone(accounts.verify_login(self.db, "rita", PASSWORD).account)

    def test_inactive_status_alone_ends_an_existing_session(self):
        admin_set = self.account("admin-set")
        self.db.commit()
        admin_set.status = "INACTIVE"  # as an administrator does in Accounts
        self.db.commit()
        self.assertIsNone(sessions.account_for_session(self.db, account_id=admin_set.id,
                                                       session_version=admin_set.session_version))

    # --- 5. selectors and history ------------------------------------------------
    def test_ceased_people_leave_selectors_but_history_keeps_them(self):
        sara = self.employee("Sara Ceased", wp="S1")
        self.roster(self.wp, "C1")
        current = {o.id for o in directory.employee_options(self.db)}
        scoped = {o.id for o in directory.employee_options(self.db, location_ids=[self.wp.id])}
        self.assertNotIn(sara.id, current)
        self.assertNotIn(sara.id, scoped)
        self.assertIn(self.colleague.id, current)
        historical = {o.id: o for o in directory.employee_options(self.db, location_ids=[self.wp.id], include_inactive=True)}
        self.assertFalse(historical[sara.id].is_active)
        kept = {o.id: o for o in directory.employee_options(self.db, selected_employee_ids=[sara.id])}
        self.assertTrue(kept[sara.id].is_selected)  # an existing selection keeps showing her
        from rfone_data_store.bank_reconciliation.configuration import cardholder_candidates
        self.assertNotIn(sara.id, {c["id"] for c in cardholder_candidates(self.db) if c["kind"] == m.CARD_HOLDER_KIND_EMPLOYEE})
        # Work history still resolves to her canonical identity and name.
        shift = self.db.scalar(select(m.Shift).where(m.Shift.employee_id == sara.id))
        self.assertEqual(self.db.get(m.Employee, shift.employee_id).display_name, "Sara Ceased")

    def test_people_without_punches_are_not_employees_and_stay_selectable(self):
        tina = directory.create_person(self.db, display_name="Tina Consultant")
        state = self.state(tina)
        self.assertEqual(state.status, directory.STATUS_NOT_EMPLOYEE)
        self.assertIn(tina.id, {o.id for o in directory.employee_options(self.db)})
        # Former staff whose punches predate the acquired history: Clover record
        # gone, no punches -> not an employee, not offered for new choices.
        ugo = self.employee("Ugo Before 2026", wp="U-OLD", shifts=False)
        self.roster(self.wp, "C1")
        self.assertEqual(self.state(ugo).status, directory.STATUS_NOT_EMPLOYEE)
        self.assertNotIn(ugo.id, {o.id for o in directory.employee_options(self.db)})
        self.assertIn(ugo.id, {o.id for o in directory.employee_options(self.db, include_inactive=True)})


if __name__ == "__main__":
    unittest.main()
