#!/usr/bin/env python
"""Trainer resend of the existing Training invitation from the person's page (Product Owner 2026-11-23).

Training app over HTTP, throwaway SQLite; the person is identified by the Registry ID of their card.
  1. Resend to the same address: same invitation, the new link works and the old one no longer does.
  2. Resend to a corrected address: the same invitation goes to the new address; activation uses it.
  3. Failed send: nothing changes — the link already sent and the registered recipient stay valid.
  4. Always one active invitation per Registry ID: a second invitation (also with another address) is refused
     and the page links to the person's page; activation is never reopened; after it, sign in.
Never sends mail, never contacts AWS or Clover.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import test_registry_training_http as base  # noqa: E402  (same app, database and trainer set-up)
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import employee_directory as directory  # noqa: E402
from rfone_data_store.training import enrollment as en  # noqa: E402
from rfone_data_store.training import workspace as _workspace  # noqa: E402,F401  (its tables exist from the first test)

LINK_RE = re.compile(r"/training/activate/([A-Za-z0-9_-]{43})")


class TrainerResendTest(base.RegistryTrainingHttpTest):
    def setUp(self):
        super().setUp()
        self.sent, self.fail_send, self.on_send = [], False, None
        for p in (patch("rfone_data_store.technical.account_email.send_email", self._send),
                  # SQLite gives back naive datetimes (PostgreSQL keeps the zone): the invitation clock follows it
                  patch.object(en, "now", lambda: en.datetime.now(en.timezone.utc).replace(tzinfo=None))):
            p.start(); self.addCleanup(p.stop)
        self.app.config['TRAINING_ENROLLMENT_LOCAL'] = False          # the invitation is emailed
        # the first invitation, as Invite student / Selection / the Server Course create it
        response = self.client.post("/training/manage/enrollment", data={
            "csrf_token": self.csrf("/training/manage/enrollment"), "mode": "direct",
            "email": "first@example.invalid", "name": "Nora Trainee"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation))
            self.invitation_id, self.first_digest = invitation.id, invitation.token_digest
            self.card_id = directory.card_for_person(db, invitation.person_id).id
        self.first_token = LINK_RE.search(self.sent[0][1]).group(1)
        self.page = f"/training/manage/people/{self.card_id}"

    def _send(self, *, to_address, subject, text_body, **kwargs):
        from rfone_data_store.technical import account_email
        if self.on_send:
            self.on_send()
        if self.fail_send:
            raise account_email.EmailSendError("the email service refused the message")
        self.sent.append((to_address, text_body))

    def _resend(self, email):
        return self.client.post(self.page, data={"csrf_token": self.csrf("/training/manage/enrollment"), "email": email})

    def _active(self, db):
        return [r for r in db.scalars(select(en.EnrollmentInvitation)) if en.is_active(r)]

    def _activate(self, token):
        self.client.get(f"/training/activate/{token}")
        csrf = base.CSRF_RE.search(self.client.get("/training/activate").get_data(as_text=True)).group(1)
        return self.client.post("/training/activate", data={"csrf_token": csrf, "first_name": "Nora",
                                "last_name": "Trainee", "phone": "", "password": "Trainee-Pass-2026!",
                                "password_confirm": "Trainee-Pass-2026!"})

    def test_the_page_identifies_the_person_by_registry_id_and_lists_the_invitation(self):
        page = self.client.get(self.page).get_data(as_text=True)
        self.assertIn(f"Registry ID {self.card_id}", page)
        self.assertIn("first@example.invalid", page)
        self.assertIn("Resend invitation", page)
        students = self.client.get("/training/manage/students").get_data(as_text=True)
        self.assertIn("Invitations waiting for activation", students)
        self.assertIn(self.page, students)

    def test_resend_to_the_same_address(self):
        response = self._resend("first@example.invalid")
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True)[:300])
        self.assertEqual([to for to, _ in self.sent], ["first@example.invalid", "first@example.invalid"])
        new_token = LINK_RE.search(self.sent[1][1]).group(1)
        with self.factory() as db:
            active = self._active(db)
            self.assertEqual([(r.id, r.email) for r in active], [(self.invitation_id, "first@example.invalid")])
            self.assertIsNone(en.lookup(db, self.first_token))
            self.assertIsNotNone(en.lookup(db, new_token))
            self.assertEqual(directory.card_for_person(db, active[0].person_id).id, self.card_id)   # same card
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)

    def test_resend_to_a_corrected_address(self):
        response = self._resend("Corrected@Example.invalid")
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True)[:300])
        self.assertEqual([to for to, _ in self.sent], ["first@example.invalid", "corrected@example.invalid"])
        new_token = LINK_RE.search(self.sent[1][1]).group(1)
        with self.factory() as db:
            active = self._active(db)
            self.assertEqual([(r.id, r.email) for r in active], [(self.invitation_id, "corrected@example.invalid")])
            self.assertIsNone(en.lookup(db, self.first_token))
            events = [e.details for e in db.scalars(select(m.EmployeeDirectoryEvent).where(
                m.EmployeeDirectoryEvent.employee_id == self.card_id,
                m.EmployeeDirectoryEvent.action == en.RESEND_ACTION))]
            self.assertEqual(events, [{"invitation_id": self.invitation_id, "email": "corrected@example.invalid",
                                       "corrected": True}])
        # activation with the new link: the account takes the corrected address; afterwards, sign in
        self.assertEqual(self._activate(new_token).status_code, 302)
        with self.factory() as db:
            account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email == "corrected@example.invalid"))
            self.assertIsNotNone(account)
            self.assertEqual(directory.card_for_person(db, db.get(en.EnrollmentInvitation, self.invitation_id).person_id).id,
                             self.card_id)
        self.client = self.app.test_client()          # back as the Trainer
        with self.client.session_transaction() as session:
            import auth
            session[auth.SESSION_ACCOUNT_KEY] = self.trainer_id
            session[auth.SESSION_VERSION_KEY] = self.trainer_version
        self.assertIn("signs in to Training", self.client.get(self.page).get_data(as_text=True))
        refused = self._resend("corrected@example.invalid")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("already activated", refused.get_data(as_text=True))
        self.assertEqual(len(self.sent), 2)

    def test_failed_send_keeps_the_previous_link_and_recipient(self):
        for address in ("first@example.invalid", "corrected@example.invalid"):
            self.fail_send = True
            response = self._resend(address)
            self.fail_send = False
            self.assertEqual(response.status_code, 400)
            self.assertIn("still works", response.get_data(as_text=True))
            with self.factory() as db:
                row = db.get(en.EnrollmentInvitation, self.invitation_id)
                self.assertEqual((row.token_digest, row.email, row.revoked_at, row.consumed_at),
                                 (self.first_digest, "first@example.invalid", None, None))
                self.assertIsNotNone(en.lookup(db, self.first_token))
                self.assertEqual(len(self._active(db)), 1)
                self.assertIsNone(db.scalar(select(m.EmployeeDirectoryEvent.id).where(
                    m.EmployeeDirectoryEvent.action == en.RESEND_ACTION)))
        self.assertEqual(len(self.sent), 1)
        # the link already received still activates
        self.assertEqual(self._activate(self.first_token).status_code, 302)

    def test_activated_while_the_resend_email_is_sent_is_never_reopened(self):
        token = self.first_token

        def activate_meanwhile():
            other = self.app.test_client()
            other.get(f"/training/activate/{token}")
            csrf = base.CSRF_RE.search(other.get("/training/activate").get_data(as_text=True)).group(1)
            other.post("/training/activate", data={"csrf_token": csrf, "first_name": "Nora", "last_name": "Trainee",
                       "phone": "", "password": "Trainee-Pass-2026!", "password_confirm": "Trainee-Pass-2026!"})
        self.on_send = activate_meanwhile
        response = self._resend("first@example.invalid")
        self.on_send = None
        self.assertEqual(response.status_code, 400)
        self.assertIn("activated meanwhile", response.get_data(as_text=True))
        with self.factory() as db:
            row = db.get(en.EnrollmentInvitation, self.invitation_id)
            self.assertIsNotNone(row.consumed_at)
            self.assertEqual(row.token_digest, self.first_digest)
            self.assertIsNone(en.lookup(db, LINK_RE.search(self.sent[1][1]).group(1)))

    def test_one_active_invitation_per_registry_id_even_with_another_address(self):
        with self.factory() as db:
            row = db.get(en.EnrollmentInvitation, self.invitation_id)
            row.created_at = row.created_at.replace(year=row.created_at.year - 1)      # past the rate limit
            person_id = row.person_id
            db.commit()
        for address in ("first@example.invalid", "another@example.invalid"):
            response = self.client.post("/training/manage/enrollment", data={
                "csrf_token": self.csrf("/training/manage/enrollment"), "mode": "direct", "email": address,
                "name": "Nora Trainee", "confirmation": f"person:{person_id}"})
            self.assertEqual(response.status_code, 400)
            body = response.get_data(as_text=True)
            self.assertIn(f"Registry ID {self.card_id}", body)
            self.assertIn(self.page, body)                                       # link to resend it
        with self.factory() as db:
            self.assertEqual([r.id for r in self._active(db)], [self.invitation_id])
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)
        self.assertEqual(len(self.sent), 1)

    def test_an_address_of_another_identity_is_refused(self):
        with self.factory() as db:
            directory.create_person(db, display_name="Someone Else", email="someone@example.invalid",
                                    restaurant_id=self.wp_id, role_id=self.cook_id, area_id=self.area_id)
            db.commit()
        response = self._resend("someone@example.invalid")
        self.assertEqual(response.status_code, 400)
        self.assertIn("another RF-One identity", response.get_data(as_text=True))
        self.assertEqual(len(self.sent), 1)


# Only this file's tests: the inherited set-up is reused, its tests run in their own module.
for _name in dir(base.RegistryTrainingHttpTest):
    if _name.startswith("test_") and _name not in TrainerResendTest.__dict__:
        setattr(TrainerResendTest, _name, None)


if __name__ == "__main__":
    unittest.main()
