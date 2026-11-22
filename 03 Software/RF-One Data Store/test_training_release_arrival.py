"""Approved sequence Selection -> Training -> Registry (Product Owner 2026-11-21, OQ-7 completion).

Disposable SQLite, no network, no Clover. Checks: the release puts the candidate in charge of a Training
operator without a Student, invitation or Clover record; only the arrival confirmation registers the
existing person as a Student and allows the enrollment; repeated confirmations duplicate nothing; a link
issued without an arrival confirmation cannot be used.
"""
from datetime import timedelta
import unittest

from sqlalchemy import func, select

from rfone_data_store import models as m, people_registry as people, student_registry as registry
from rfone_data_store import access_profiles as profiles
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.training import enrollment as en


class ReleaseAndArrival(unittest.TestCase):
    def setUp(self):
        self.engine = create_configured_engine("sqlite:///:memory:")
        m.Base.metadata.create_all(self.engine)
        db = self.db = create_session_factory(self.engine)()
        self.hirer = accounts.create_account(db, username="hirer", display_name="Hirer", password="Hirer-Pass-9",
                                             email="hirer@example.invalid")
        self.trainer = accounts.create_account(db, username="trainer", display_name="Trainer T.", password="Trainer-Pass-9",
                                               email="trainer@example.invalid")
        self.other = accounts.create_account(db, username="other", display_name="Other", password="Other-Pass-99",
                                             email="other@example.invalid")
        db.flush()
        accounts.set_domain_access(db, account_id=self.hirer.id, domain_code="SELECTION", enabled=True, role_code="OWNER")
        db.flush()
        requirements = m.RequirementSet(name="Server")
        db.add(requirements); db.flush()
        self.position = ps.WorkspacePosition(title="Server", role_code="SERVER", location_label="Winter Park",
            timezone="America/New_York", manager_account_id=self.hirer.id, created_by_account_id=self.hirer.id,
            requirement_set_id=requirements.id)
        db.add(self.position); db.flush()
        self.person = people.create_identity(db, full_name="Maria Rossi", email="maria@example.invalid",
                                             normalized_name="maria rossi")
        candidate = m.Candidate(full_name="Maria Rossi", email="maria@example.invalid", phone="+1 407 555 0100",
                                parsing_mode="DEMO")
        db.add(candidate); db.flush()
        application = m.Application(person_id=self.person.id, candidate_id=candidate.id)
        db.add(application); db.flush()
        self.pc = ps.WorkspacePositionCandidate(position_id=self.position.id, application_id=application.id,
                                                candidate_id=candidate.id, channel="MANUAL_UPLOAD")
        db.add(self.pc); db.flush()
        db.add(ps.WorkspaceDecision(position_candidate_id=self.pc.id, decision=ps.D_HIRED,
                                    actor_account_id=self.hirer.id, actor_name="Hirer"))
        db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def count(self, model, *where):
        return self.db.scalar(select(func.count()).select_from(model).where(*where))

    def events(self, action):
        return [e for e in self.db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == action))
                if e.details.get("selection_id") == self.pc.id]

    def student(self):
        return self.db.get(registry.PersonQualification, (self.person.id, "STUDENT")) is not None

    def release(self):
        status = en.release(self.db, selection_id=self.pc.id, released_by=self.hirer, operator=self.trainer)
        self.db.commit()
        return status

    def nothing_created_outside_the_hand_off(self):
        self.assertFalse(self.student())
        self.assertEqual(self.count(en.EnrollmentInvitation), 0)
        self.assertEqual(self.count(m.TrainingAccount), 0)
        self.assertEqual(self.count(m.Employee), 0)                 # no Anagrafica employee record
        self.assertEqual(self.count(m.EmployeeCloverLink), 0)       # nothing towards Clover
        self.assertEqual(self.count(people.PersonEmployeeLink), 0)

    # 1. release -----------------------------------------------------------------------------------
    def test_release_puts_the_candidate_in_charge_of_training_and_creates_nothing_else(self):
        self.assertEqual(self.release(), "released")
        [event] = self.events(en.RELEASED)
        self.assertEqual((event.details["operator_account_id"], event.account_id), (self.trainer.id, self.hirer.id))
        self.nothing_created_outside_the_hand_off()
        self.assertEqual(self.release(), "already")
        self.assertEqual(len(self.events(en.RELEASED)), 1)

    def test_the_operator_in_charge_sees_the_candidate_without_selection_rights(self):
        self.assertEqual(en.confirmed_candidates(self.db, self.trainer), [])
        self.release()
        [row] = en.confirmed_candidates(self.db, self.trainer)
        self.assertEqual((row["id"], row["released"], row["arrived"]), (self.pc.id, True, False))
        self.assertEqual(en.confirmed_candidates(self.db, self.other), [])
        with self.assertRaises(ValueError):
            en.confirm_arrival(self.db, actor=self.other, selection_id=self.pc.id)

    def test_release_requires_a_current_hired_decision(self):
        self.db.add(ps.WorkspaceDecision(position_candidate_id=self.pc.id, decision=ps.D_NOT_SELECTED,
                                         actor_account_id=self.hirer.id, actor_name="Hirer"))
        self.db.commit()
        with self.assertRaises(ValueError):
            self.release()

    # 2. arrival confirmation ----------------------------------------------------------------------
    def test_arrival_confirmation_registers_the_existing_person_as_student_once(self):
        self.release()
        person_id, first = en.confirm_arrival(self.db, actor=self.trainer, selection_id=self.pc.id)
        self.db.commit()
        self.assertEqual((person_id, first), (self.person.id, True))
        self.assertTrue(self.student())
        self.assertEqual(self.count(m.CandidatePerson), 1)          # existing identity reused
        person_id, again = en.confirm_arrival(self.db, actor=self.trainer, selection_id=self.pc.id)
        self.db.commit()
        self.assertFalse(again)
        self.assertEqual(len(self.events(en.ARRIVED)), 1)
        self.assertEqual(self.count(registry.PersonQualification), 1)
        self.assertEqual(self.count(m.EmployeeCloverLink), 0)       # still nothing towards Clover

    def test_enrollment_follows_the_arrival_and_is_never_duplicated(self):
        self.release()
        invitation, _ = en.issue(self.db, actor=self.trainer, email="maria@example.invalid", selection_id=self.pc.id)
        self.db.commit()
        self.assertTrue(self.student())
        self.assertEqual((invitation.person_id, invitation.selection_id), (self.person.id, self.pc.id))
        self.assertEqual(len(self.events(en.ARRIVED)), 1)
        invitation.created_at -= timedelta(seconds=61); self.db.commit()   # past the rate limit
        with self.assertRaises(ValueError):
            en.issue(self.db, actor=self.trainer, email="maria@example.invalid", selection_id=self.pc.id)
        self.db.rollback()
        self.assertEqual(self.count(en.EnrollmentInvitation), 1)
        self.assertEqual(len(self.events(en.ARRIVED)), 1)
        # A completed enrollment is not enrolled again either.
        invitation = self.db.scalar(select(en.EnrollmentInvitation))
        invitation.consumed_at = en.now(); self.db.commit()
        with self.assertRaises(ValueError):
            en.issue(self.db, actor=self.trainer, email="maria@example.invalid", selection_id=self.pc.id)
        self.db.rollback()
        self.assertEqual(self.count(en.EnrollmentInvitation), 1)

    # Codex review 2026-11-22 §3 — the arrival can never skip the release ----------------------------
    def test_selection_rights_without_release_never_confirm_the_arrival(self):
        # Codex reproduced: released=False, then Student registered with zero RELEASED events.
        [row] = en.confirmed_candidates(self.db, self.hirer)        # the list still shows it (release entry)
        self.assertFalse(row["released"])
        with self.assertRaisesRegex(ValueError, "not released"):
            en.confirm_arrival(self.db, actor=self.hirer, selection_id=self.pc.id)
        self.db.rollback()
        with self.assertRaisesRegex(ValueError, "not released"):   # the alternative entry: Invite student
            en.issue(self.db, actor=self.hirer, email="maria@example.invalid", selection_id=self.pc.id)
        self.db.rollback()
        self.nothing_created_outside_the_hand_off()
        self.assertEqual(self.events(en.ARRIVED), [])
        self.assertEqual(self.events(en.RELEASED), [])

    def test_only_the_operator_in_charge_confirms_the_arrival(self):
        self.release()                                               # in charge: self.trainer
        with self.assertRaisesRegex(ValueError, "another Training operator"):
            en.confirm_arrival(self.db, actor=self.hirer, selection_id=self.pc.id)
        self.db.rollback()
        self.assertFalse(self.student())
        self.assertEqual(self.events(en.ARRIVED), [])
        self.assertEqual(en.confirm_arrival(self.db, actor=self.trainer, selection_id=self.pc.id), (self.person.id, True))

    def test_a_legacy_arrival_without_release_does_not_enroll(self):
        # An ARRIVED event written before this check (no RELEASED event) never lets `issue` continue.
        profiles.event(self.db, en.ARRIVED, actor=self.hirer.id, selection_id=self.pc.id, person_id=self.person.id,
                       at=en.now().isoformat())
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "not released"):
            en.issue(self.db, actor=self.hirer, email="maria@example.invalid", selection_id=self.pc.id)
        self.db.rollback()
        self.assertEqual(self.count(en.EnrollmentInvitation), 0)

    def test_direct_invitation_outside_selection_is_unchanged(self):
        invitation, _ = en.issue(self.db, actor=self.trainer, email="new.person@example.invalid", name="New Person")
        self.db.commit()
        self.assertIsNone(invitation.selection_id)
        self.assertFalse(self.student())                             # Student only after activation, as before

    def test_a_link_issued_before_the_arrival_is_not_accepted(self):
        # A pending invitation from the former automatic path (sent at release time, no arrival).
        self.release()
        stamp = en.now()
        self.db.add(en.EnrollmentInvitation(token_digest="x" * 64, email="maria@example.invalid", name="Maria Rossi",
            phone="", person_id=self.person.id, selection_id=self.pc.id, created_by_id=self.trainer.id,
            created_at=stamp, expires_at=stamp + timedelta(hours=48), failed_attempts=0))
        self.db.commit()
        [row] = en.confirmed_candidates(self.db, self.trainer)
        self.assertFalse(row["arrived"])                              # activation refuses it (route check)
        self.assertFalse(self.student())


if __name__ == "__main__":
    unittest.main()
