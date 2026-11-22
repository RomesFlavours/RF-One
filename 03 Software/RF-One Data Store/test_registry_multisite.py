"""REGISTRY_MULTISITE_001 — new multi-site Registry (Product Owner specification, 2026-11-22).

Disposable in-memory SQLite and fake Clover clients only. Covers: WP and MD lists, a person at both sites,
an empty MD, manual entry, both Training entries, the POS ID of a new hire, Tips history continuity, and that
a new Clover name (staff list or shifts) never creates, updates or proposes a Registry card.

Usage:
    python -m unittest test_registry_multisite
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import func, select

from rfone_data_store import models as m, people_registry as people, student_registry as registry
from rfone_data_store import access_profiles as profiles
from rfone_data_store import employee_directory as directory
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store.clover_correction_sync_validation import _CorrectionFakeCloverClient
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.technical.connectors.clover import acquisition, identity_holds
from rfone_data_store.technical.connectors.clover.correction_sync import run_correction_cycle
from rfone_data_store.training import enrollment as en

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)


def _ms(value):
    return int(value.timestamp() * 1000)


class RegistryMultisiteTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        db = self.db = create_session_factory(self.engine)()
        self.source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        db.add(self.source); db.flush()
        self.wp, self.wp_loc = self._site("Rome's Flavours - WP", "WPMERCHANT", active=True)
        self.md, self.md_loc = self._site("Rome's Flavours - MD", "MDMERCHANT", active=False)
        self.area = m.OperationalArea(name="Restaurant Operations", restaurant_id=None)
        db.add(self.area); db.flush()
        self.server = self._role("Server", self.wp.id)          # WP-only role
        self.cook = self._role("Cook", None)                    # role of every site
        self.admin = accounts.create_account(db, username="admin", display_name="Admin A.", password="Admin-Pass-99",
                                             email="admin@example.invalid", is_admin=True)
        db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    # -- fixtures -----------------------------------------------------------------------------------
    def _site(self, name, merchant_id, *, active):
        merchant = m.Merchant(source_system_id=self.source.id, source_merchant_id=merchant_id, name=name, active=active)
        self.db.add(merchant); self.db.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=self.source.id, source_location_id=merchant_id,
                              name=name, currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=time(4, 0), active=active)
        restaurant = m.Restaurant(name=name, default_currency="USD")
        self.db.add_all([location, restaurant]); self.db.flush()
        self.db.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        self.db.flush()
        return restaurant, location

    def _role(self, name, restaurant_id):
        role = m.RestaurantRole(name=name, code=name.upper(), restaurant_id=restaurant_id)
        self.db.add(role); self.db.flush()
        self.db.add(m.OperationalAreaRole(operational_area_id=self.area.id, restaurant_role_id=role.id))
        self.db.flush()
        return role

    def card(self, name, site, role=None, **contacts):
        return directory.create_person(self.db, display_name=name, restaurant_id=site.id,
                                       role_id=(role or self.cook).id, area_id=self.area.id, **contacts)

    def count(self, model, *where):
        return self.db.scalar(select(func.count()).select_from(model).where(*where))

    # -- 1. sites -----------------------------------------------------------------------------------
    def test_each_site_lists_only_its_explicit_assignments_and_md_never_falls_back_to_wp(self):
        anna = self.card("Anna Rossi", self.wp, self.server, email="anna@example.invalid")
        luca = self.card("Luca Bianchi", self.wp, self.server)
        self.assertEqual(directory.site_employee_ids(self.db, self.wp.id), {anna.id, luca.id})
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), set())          # MD empty, not WP
        # Neither a Clover link at MD, a company membership in MD nor the card's own location field list Luca at MD.
        self.db.add(m.EmployeeCloverLink(employee_id=luca.id, location_id=self.md_loc.id, merchant_id="MDMERCHANT",
                                         external_employee_id="M-LUCA", state="PRESENT"))
        md_company = profiles.CompanyContext(name="MD", kind="COMPANY", active=True)
        self.db.add(md_company); self.db.flush()
        self.db.add(profiles.CompanyMembership(employee_id=luca.id, company_id=md_company.id))
        luca.location_id = self.md_loc.id
        self.db.flush()
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), set())
        # An explicit assignment of the SAME card to MD lists it at both sites with one RF-One ID.
        directory.assign_site(self.db, employee_id=anna.id, restaurant_id=self.md.id, role_id=self.cook.id,
                              area_id=self.area.id)
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), {anna.id})
        self.assertIn(anna.id, directory.site_employee_ids(self.db, self.wp.id))
        self.assertEqual(directory.employee_site_ids(self.db, anna.id), {self.wp.id, self.md.id})
        self.assertEqual(self.count(m.Employee), 2)
        # A closed assignment no longer lists the person.
        assignment = self.db.scalar(select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == anna.id, m.EmployeeAssignment.restaurant_id == self.md.id))
        assignment.valid_to = datetime.now(UTC) - timedelta(minutes=1)
        self.db.flush()
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), set())

    def test_location_specific_assignment_counts_for_its_site(self):
        person = m.Employee(display_name="Location only")
        self.db.add(person); self.db.flush()
        self.db.add(m.EmployeeAssignment(employee_id=person.id, restaurant_id=None, location_id=self.md_loc.id,
            restaurant_role_id=self.cook.id, operational_area_id=self.area.id, valid_from=NOW - timedelta(days=1),
            assignment_source="MANUAL"))
        self.db.flush()
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), {person.id})
        self.assertEqual(directory.site_employee_ids(self.db, self.wp.id), set())

    def test_site_roles_offer_only_roles_of_that_site(self):
        wp_roles = {role.name for role, _area in directory.site_role_choices(self.db, self.wp.id)}
        md_roles = {role.name for role, _area in directory.site_role_choices(self.db, self.md.id)}
        self.assertEqual((wp_roles, md_roles), ({"Server", "Cook"}, {"Cook"}))
        with self.assertRaisesRegex(ValueError, "role available at this site"):
            self.card("Wrong role", self.md, self.server)

    # -- 2. manual entry ----------------------------------------------------------------------------
    def test_manual_entry_needs_the_site_and_never_duplicates_a_registered_person(self):
        with self.assertRaisesRegex(ValueError, "site"):
            directory.create_person(self.db, display_name="No site")
        anna = self.card("Anna Rossi", self.wp, self.server, email="anna@example.invalid", phone="4075550100")
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.card("Anna R.", self.md, email="ANNA@example.invalid")
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.card("Anna (phone)", self.md, phone="4075550100")
        self.assertEqual(self.count(m.Employee), 1)
        first = directory.assign_site(self.db, employee_id=anna.id, restaurant_id=self.md.id, role_id=self.cook.id,
                                      area_id=self.area.id)
        again = directory.assign_site(self.db, employee_id=anna.id, restaurant_id=self.md.id, role_id=self.cook.id,
                                      area_id=self.area.id)
        self.assertEqual(first.id, again.id)                                                 # idempotent
        events = {e.action for e in self.db.scalars(select(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.employee_id == anna.id))}
        self.assertTrue({"RF1_CREATE", "SITE_ASSIGN"} <= events)

    def test_registry_profile_creation_requires_the_site(self):
        with self.assertRaisesRegex(ValueError, "site"):
            profiles.create_profile_person(self.db, name="No Site", company_ids=[], assignments=[], actor=self.admin.id)
        person = profiles.create_profile_person(self.db, name="With Site", company_ids=[], assignments=[],
                                                actor=self.admin.id, site=(self.md.id, self.cook.id, self.area.id))
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), {person.id})

    # -- 3. Training entries ------------------------------------------------------------------------
    def _trainer(self, username="trainer"):
        trainer = accounts.create_account(self.db, username=username, display_name="Trainer T.",
                                          password="Trainer-Pass-9", email=f"{username}@example.invalid")
        self.db.flush()
        accounts.set_domain_access(self.db, account_id=trainer.id, domain_code="TRAINING", enabled=True,
                                   role_code="trainer")
        self.db.commit()
        return trainer

    def _hired_candidate(self, hirer):
        accounts.set_domain_access(self.db, account_id=hirer.id, domain_code="SELECTION", enabled=True, role_code="OWNER")
        requirements = m.RequirementSet(name="Server"); self.db.add(requirements); self.db.flush()
        position = ps.WorkspacePosition(title="Server", role_code="SERVER", location_label="Mount Dora",
            timezone="America/New_York", manager_account_id=hirer.id, created_by_account_id=hirer.id,
            requirement_set_id=requirements.id)
        self.db.add(position); self.db.flush()
        person = people.create_identity(self.db, full_name="Maria Rossi", email="maria@example.invalid",
                                        normalized_name="maria rossi")
        candidate = m.Candidate(full_name="Maria Rossi", email="maria@example.invalid", parsing_mode="DEMO")
        self.db.add(candidate); self.db.flush()
        application = m.Application(person_id=person.id, candidate_id=candidate.id)
        self.db.add(application); self.db.flush()
        pc = ps.WorkspacePositionCandidate(position_id=position.id, application_id=application.id,
                                           candidate_id=candidate.id, channel="MANUAL_UPLOAD")
        self.db.add(pc); self.db.flush()
        self.db.add(ps.WorkspaceDecision(position_candidate_id=pc.id, decision=ps.D_HIRED,
                                         actor_account_id=hirer.id, actor_name="Hirer"))
        self.db.commit()
        return person, pc

    def test_direct_invitation_creates_a_trainee_card_at_the_training_site_and_reuses_it(self):
        trainer = self._trainer()
        site = dict(restaurant_id=self.md.id, role_id=self.cook.id, area_id=self.area.id)
        invitation, _ = en.issue(self.db, actor=trainer, email="new.cook@example.invalid", name="New Cook", **site)
        self.db.commit()
        card = directory.card_for_person(self.db, invitation.person_id)
        self.assertIsNotNone(card)
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), {card.id})
        self.assertEqual(directory.site_employee_ids(self.db, self.wp.id), set())
        self.assertIsNotNone(self.db.get(registry.PersonQualification, (invitation.person_id, "STUDENT")))
        self.assertNotIn("EMPLOYEE", people.company_statuses(self.db, invitation.person_id))   # Trainee
        # Repeating it (after the rate limit, confirming the same person) reuses identity and card.
        invitation.created_at -= timedelta(seconds=61); self.db.commit()
        again, _ = en.issue(self.db, actor=trainer, email="new.cook@example.invalid", name="New Cook",
                            confirmation=f"person:{invitation.person_id}", **site)
        self.db.commit()
        self.assertEqual(again.person_id, invitation.person_id)
        self.assertEqual(self.count(m.Employee), 1)
        self.assertEqual(self.count(m.EmployeeAssignment), 1)
        self.assertEqual(self.count(m.CandidatePerson), 1)

    def test_training_site_must_be_chosen_and_reachable(self):
        trainer = self._trainer()
        with self.assertRaisesRegex(ValueError, "training site"):
            en.issue(self.db, actor=trainer, email="x@example.invalid", name="X", restaurant_id=None)
        self.db.rollback()
        with self.assertRaisesRegex(ValueError, "role the person trains for"):
            en.issue(self.db, actor=trainer, email="x@example.invalid", name="X", restaurant_id=self.md.id,
                     role_id=self.server.id, area_id=self.area.id)                       # Server is WP-only
        self.db.rollback()
        self.assertEqual(self.count(m.Employee), 0)

    def test_send_to_training_reuses_the_candidate_and_creates_the_card_at_arrival(self):
        hirer = accounts.create_account(self.db, username="hirer", display_name="Hirer", password="Hirer-Pass-99",
                                        email="hirer@example.invalid")
        trainer = self._trainer()
        person, pc = self._hired_candidate(hirer)
        self.assertEqual(en.release(self.db, selection_id=pc.id, released_by=hirer, operator=trainer), "released")
        self.db.commit()
        self.assertEqual(self.count(m.Employee), 0)                     # the release alone creates nothing
        self.assertEqual(en.release(self.db, selection_id=pc.id, released_by=hirer, operator=trainer), "already")
        invitation, _ = en.issue(self.db, actor=trainer, email="maria@example.invalid", selection_id=pc.id,
                                 restaurant_id=self.md.id, role_id=self.cook.id, area_id=self.area.id)
        self.db.commit()
        self.assertEqual(invitation.person_id, person.id)                # the Selection person, reused
        card = directory.card_for_person(self.db, person.id)
        self.assertEqual(directory.site_employee_ids(self.db, self.md.id), {card.id})
        self.assertIsNotNone(self.db.get(registry.PersonQualification, (person.id, "STUDENT")))
        # A second enrollment of the same candidate is refused: no second invitation, no second card.
        invitation.created_at -= timedelta(seconds=61); self.db.commit()
        with self.assertRaises(ValueError):
            en.issue(self.db, actor=trainer, email="maria@example.invalid", selection_id=pc.id,
                     restaurant_id=self.md.id, role_id=self.cook.id, area_id=self.area.id)
        self.db.rollback()
        self.assertEqual((self.count(en.EnrollmentInvitation), self.count(m.Employee)), (1, 1))

    def test_an_employee_keeps_the_status_and_the_card_when_entering_training(self):
        trainer = self._trainer()
        existing = self.card("Gina Verdi", self.wp, self.server, email="gina@example.invalid")
        person = people.create_identity(self.db, full_name="Gina Verdi", email="gina@example.invalid",
                                        normalized_name="gina verdi")
        self.db.add(people.PersonEmployeeLink(employee_id=existing.id, person_id=person.id, linked_by_id=self.admin.id,
                                              linked_at=NOW))
        self.db.add(people.PersonCompanyStatus(person_id=person.id, code="EMPLOYEE"))
        self.db.commit()
        en.issue(self.db, actor=trainer, email="gina@example.invalid", name="Gina Verdi",
                 confirmation=f"person:{person.id}", restaurant_id=self.md.id, role_id=self.cook.id,
                 area_id=self.area.id)
        self.db.commit()
        self.assertEqual(self.count(m.Employee), 1)                                       # same card
        self.assertIsNone(self.db.get(registry.PersonQualification, (person.id, "STUDENT")))
        self.assertIn("EMPLOYEE", people.company_statuses(self.db, person.id))
        self.assertEqual(directory.employee_site_ids(self.db, existing.id), {self.wp.id, self.md.id})

    def test_card_link_alone_no_longer_means_employee(self):
        person = people.create_identity(self.db, full_name="Trainee Card", email="t@example.invalid",
                                        normalized_name="trainee card")
        card = self.card("Trainee Card", self.wp)
        self.db.add(people.PersonEmployeeLink(employee_id=card.id, person_id=person.id, linked_by_id=self.admin.id,
                                              linked_at=NOW))
        self.db.flush()
        self.assertEqual(people.company_statuses(self.db, person.id), set())
        self.db.add(people.PersonCompanyStatus(person_id=person.id, code="EMPLOYEE"))      # Confirm Hire
        self.db.flush()
        self.assertEqual(people.company_statuses(self.db, person.id), {"EMPLOYEE"})
        self.assertEqual(directory.card_for_person(self.db, person.id).id, card.id)       # same card

    # -- 4. POS ID ----------------------------------------------------------------------------------
    def _held_order(self, external_id, source_order_id="O-NEW"):
        order = m.Order(source_system_id=self.source.id, source_order_id=source_order_id, location_id=self.wp_loc.id,
                        source_employee_id=external_id, employee_id=None, created_at=NOW)
        self.db.add(order); self.db.flush()
        return order

    def test_pos_id_of_a_new_hire_attributes_waiting_work_and_is_unique_per_site(self):
        hire = self.card("New Hire", self.wp, self.server)
        other = self.card("Other Person", self.wp, self.server)
        order = self._held_order("U1")
        self.assertEqual(identity_holds.pending_external_ids(self.db, ["WPMERCHANT"]), {"U1"})
        link, counts = directory.set_pos_id(self.db, employee_id=hire.id, restaurant_id=self.wp.id, pos_id="U1")
        self.assertEqual((link.merchant_id, link.external_employee_id, link.employee_id), ("WPMERCHANT", "U1", hire.id))
        self.assertEqual(counts["orders"], 1)
        self.assertEqual(order.employee_id, hire.id)
        self.assertEqual(identity_holds.pending_external_ids(self.db, ["WPMERCHANT"]), set())
        with self.assertRaisesRegex(ValueError, "already belongs"):
            directory.set_pos_id(self.db, employee_id=other.id, restaurant_id=self.wp.id, pos_id="U1")
        # The same Clover number at another site is another identity: allowed once assigned there.
        directory.assign_site(self.db, employee_id=other.id, restaurant_id=self.md.id, role_id=self.cook.id,
                              area_id=self.area.id)
        directory.set_pos_id(self.db, employee_id=other.id, restaurant_id=self.md.id, pos_id="U1")
        self.assertEqual(directory.resolved_identities(self.db, "MDMERCHANT"), {"U1": other.id})
        self.assertEqual(directory.resolved_identities(self.db, "WPMERCHANT"), {"U1": hire.id})

    def test_pos_id_needs_the_site_assignment_and_a_site_with_pos(self):
        person = self.card("Only WP", self.wp, self.server)
        with self.assertRaisesRegex(ValueError, "not assigned to this site"):
            directory.set_pos_id(self.db, employee_id=person.id, restaurant_id=self.md.id, pos_id="M1")
        no_pos = m.Restaurant(name="No POS site"); self.db.add(no_pos); self.db.flush()
        directory.assign_site(self.db, employee_id=person.id, restaurant_id=no_pos.id, role_id=self.cook.id,
                              area_id=self.area.id)
        with self.assertRaisesRegex(ValueError, "no POS connection"):
            directory.set_pos_id(self.db, employee_id=person.id, restaurant_id=no_pos.id, pos_id="X1")
        with self.assertRaisesRegex(ValueError, "without spaces"):
            directory.set_pos_id(self.db, employee_id=person.id, restaurant_id=self.wp.id, pos_id="A B")

    def test_correcting_a_pos_id_never_moves_consolidated_history(self):
        hire = self.card("New Hire", self.wp, self.server)
        attributed = self._held_order("WRONG", "O-OLD")
        directory.set_pos_id(self.db, employee_id=hire.id, restaurant_id=self.wp.id, pos_id="WRONG")
        self.assertEqual(attributed.employee_id, hire.id)                                # consolidated
        shift = m.Shift(source_system_id=self.source.id, source_shift_id="S-OLD", employee_id=hire.id,
                        location_id=self.wp_loc.id, clock_in=NOW - timedelta(days=3))
        self.db.add(shift); self.db.flush()
        waiting = self._held_order("RIGHT", "O-WAITING")
        link, counts = directory.set_pos_id(self.db, employee_id=hire.id, restaurant_id=self.wp.id, pos_id="RIGHT")
        self.assertEqual(waiting.employee_id, hire.id)                                   # waiting work attributed
        self.assertEqual((attributed.employee_id, shift.employee_id), (hire.id, hire.id))  # history unchanged
        old = self.db.scalar(select(m.EmployeeCloverLink).filter_by(external_employee_id="WRONG"))
        self.assertEqual((old.employee_id, old.state), (None, directory.POS_CORRECTED_STATE))
        self.assertEqual(directory.pos_links(self.db, hire.id)[self.wp.id].external_employee_id, "RIGHT")
        actions = [e.action for e in self.db.scalars(select(m.EmployeeDirectoryEvent).where(
            m.EmployeeDirectoryEvent.employee_id == hire.id).order_by(m.EmployeeDirectoryEvent.id))]
        self.assertIn("POS_ID_CORRECTED", actions)
        # The freed number can then be typed for the person it really belongs to.
        other = self.card("Real Owner", self.wp, self.server)
        directory.set_pos_id(self.db, employee_id=other.id, restaurant_id=self.wp.id, pos_id="WRONG")
        self.assertEqual(attributed.employee_id, hire.id)                                # still not moved

    def test_existing_links_keep_resolving_tips_history(self):
        veteran = m.Employee(display_name="Veteran", location_id=self.wp_loc.id)
        self.db.add(veteran); self.db.flush()
        self.db.add(m.EmployeeCloverLink(employee_id=veteran.id, location_id=self.wp_loc.id, merchant_id="WPMERCHANT",
                                         external_employee_id="V1", state="MISSING_REVIEW"))  # former import state
        self.db.flush()
        self.assertEqual(directory.resolved_identities(self.db, "WPMERCHANT"), {"V1": veteran.id})
        self.assertEqual(identity_holds.pending_external_ids(self.db, ["WPMERCHANT"]), set())

    # -- 5. a new Clover name never touches Registry ------------------------------------------------
    def _registry_state(self):
        return (self.count(m.Employee), self.count(m.EmployeeCloverLink), self.count(m.EmployeeDirectoryEvent),
                self.count(m.EmployeeAssignment),
                sorted((l.id, l.employee_id, l.state, str(l.snapshot)) for l in self.db.scalars(select(m.EmployeeCloverLink))))

    def test_a_new_clover_name_in_the_staff_list_or_in_shifts_creates_updates_or_proposes_nothing(self):
        known = self.card("Known Server", self.wp, self.server)
        directory.set_pos_id(self.db, employee_id=known.id, restaurant_id=self.wp.id, pos_id="E1")
        self.db.commit()
        before = self._registry_state()
        # (a) the active poller with a staff list that contains a new name and changed data of a known person
        client = _CorrectionFakeCloverClient("WPMERCHANT")
        client.employees = [{"id": "E1", "name": "Known Server RENAMED", "email": "changed@example.invalid"},
                            {"id": "NEWBIE", "name": "Brand New Name"}]
        at = NOW - timedelta(hours=2)
        client.orders.append({"id": "O-NEWBIE", "employee": {"id": "NEWBIE"}, "createdTime": _ms(at),
                              "modifiedTime": _ms(at), "state": "locked", "paymentState": "PAID", "currency": "USD",
                              "total": 1000, "lineItems": {"elements": []}})
        summary = run_correction_cycle(self.db, location_id=self.wp_loc.id, client=client, now=NOW)
        self.db.commit()
        self.assertEqual(summary.employee_errors, [])
        self.assertNotIn(f"/v3/merchants/WPMERCHANT/employees", [path for path, *_ in getattr(client, "calls", [])])
        self.assertEqual(self._registry_state(), before)
        self.assertEqual(known.display_name, "Known Server")
        # (b) shifts with an unknown employee, read by the acquisition
        run = m.IngestionRun(source_system_id=self.source.id, location_id=self.wp_loc.id, status="RUNNING",
                             started_at=NOW)
        self.db.add(run); self.db.flush()
        shifts = SimpleNamespace(ok=True, truncated_by_safety_guard=False, elements=[
            {"id": "S-NEWBIE", "employee": {"id": "NEWBIE"}, "overrideInEmployee": {"id": "OTHER-NEW"},
             "inTime": _ms(NOW - timedelta(hours=4)), "outTime": _ms(NOW - timedelta(hours=1))}])
        lookups = []
        fake = SimpleNamespace(merchant_id="WPMERCHANT", get=lambda path, params=None: lookups.append(path))
        held = []
        with patch.object(acquisition, "paginate", return_value=shifts):
            touched = acquisition._fetch_and_ingest_shifts(
                fake, self.db, period_start=NOW - timedelta(days=1), period_end=NOW, source_system_id=self.source.id,
                employee_by_source_id=directory.resolved_identities(self.db, "WPMERCHANT"),
                ingestion_run_id=run.id, retrieved_at=NOW, held=held)
        self.db.flush()
        self.assertEqual((touched, len(held), lookups), (0, 1, []))   # held, and no Clover employee lookup
        self.assertEqual(self._registry_state()[:4], before[:4])
        # (c) the shift waits for Tips reconciliation: visible as unattributed work, not as a proposal
        self.assertIn("NEWBIE", identity_holds.pending_external_ids(self.db, ["WPMERCHANT"]))
        self.assertIn("S-NEWBIE", identity_holds.held_shifts(self.db, location_ids=[self.wp_loc.id],
                                                             external_ids={"NEWBIE"}))
        # (d) only the operator's POS ID attributes it
        newbie = self.card("Brand New Name", self.wp, self.server)
        directory.set_pos_id(self.db, employee_id=newbie.id, restaurant_id=self.wp.id, pos_id="NEWBIE")
        shift = self.db.scalar(select(m.Shift).filter_by(source_shift_id="S-NEWBIE"))
        self.assertEqual((shift.employee_id, shift.location_id), (newbie.id, self.wp_loc.id))

    def test_the_period_acquisition_never_reads_the_staff_list(self):
        from rfone_data_store.clover_acquisition_validation import FakeCloverClient
        self.md_loc.active = True; self.db.commit()
        client = FakeCloverClient("MDMERCHANT")
        client.employees = [{"id": "MD-NEW", "name": "Mount Dora Newcomer"}]
        before = self._registry_state()
        acquisition.import_clover_period(self.db, location_id=self.md_loc.id, period_start=NOW - timedelta(days=1),
                                         period_end=NOW, mode="LIVE_SYNC", client=client)
        self.db.commit()
        self.assertEqual(self._registry_state(), before)
        self.assertFalse(any("/employees" in str(call) for call in getattr(client, "calls", [])))


if __name__ == "__main__":
    unittest.main()
