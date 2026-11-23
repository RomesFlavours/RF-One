#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — the Server Course automatic invitation with the training site of its code
(Product Owner 2026-11-22). Course side (Server Course/rf_training.py, local store in a temporary folder) and
Training side (POST /training/courses/server/invite, throwaway SQLite) joined end to end: the course's request
goes to the Training test client, Training's call back reads the course's own record.

  1. A Winter Park hire and a Mount Dora hire: one invitation, one email, the Registry card at the site the
     manager chose (role Server, Trainee) and, after activation, no permission beyond Training.
  2. No site is ever assumed: a hire without a site gets no code; a code whose site is unknown or missing
     at Training, or a site without a unique Server role, is refused with nothing saved and no email.
  3. Asking again with the same code and email: the same invitation's link is sent again (same card and
     site, no second invitation or account). The link already received keeps working until the email service
     accepts the new email (a refused send changes nothing); after a successful resend the new link works.
     Activated (also while the new email is being sent): never reopened, sign in. Another code or email: no
     resend.
  4. Codes issued before the switch: an active RF-One invitation stays usable; a code still valid without a
     site is bound to the site confirmed for the hire, and used there.
Never sends mail, never contacts AWS, Clover or the real course.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COURSE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "Server Course"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import test_registry_training_http as base  # noqa: E402  (same app, database and trainer set-up)
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m, people_registry as people  # noqa: E402
from rfone_data_store import employee_directory as directory  # noqa: E402
from rfone_data_store.training import enrollment as en  # noqa: E402

LINK_RE = re.compile(r"/training/activate/([A-Za-z0-9_-]{43})")


def _load_course(store_dir):
    """The course's rf_training + store modules, on their own local store."""
    os.environ["RFONE_TRAINER_STORE"] = store_dir
    os.environ.pop("RFONE_TRAINER_BUCKET", None)
    if COURSE_DIR not in sys.path:
        sys.path.insert(0, COURSE_DIR)
    for name in ("store", "rf_training"):
        sys.modules.pop(name, None)
    store = importlib.import_module("store")
    rf_training = importlib.import_module("rf_training")
    return store, rf_training


class ServerCourseInviteTest(base.RegistryTrainingHttpTest):
    def setUp(self):
        super().setUp()
        with self.factory() as db:
            server = m.RestaurantRole(name="Server", code="SERVER"); db.add(server); db.flush()
            db.add(m.OperationalAreaRole(operational_area_id=self.area_id, restaurant_role_id=server.id))
            db.commit(); self.server_id = server.id
        folder = tempfile.mkdtemp(prefix="server_course_store_")
        self.store, self.course = _load_course(folder)
        import training_server_course as sc
        self.sc = sc
        self.sent, self.fail_send, self.on_send = [], False, None
        trainer_id = self.trainer_id
        patches = [
            # the course asks Training: the request goes to the Training test client
            patch.object(self.course, "_post", self._course_post),
            # Training calls the course back on its fixed address: answered by the course's own record
            patch.object(sc.urllib.request, "urlopen", self._course_callback),
            patch.object(sc, "default_trainer", lambda db: db.get(m.RFOneAccount, trainer_id)),
            patch("rfone_data_store.technical.account_email.send_email", self._send),
            # SQLite gives back naive datetimes (PostgreSQL keeps the zone): the invitation clock follows it here
            patch.object(en, "now", lambda: en.datetime.now(en.timezone.utc).replace(tzinfo=None)),
        ]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    # ------------------------------------------------------------------ the two sides joined
    def _course_post(self, path, payload):
        response = self.client.post(path, json=payload)
        return response.status_code, response.get_json() or {}

    def _course_callback(self, request, timeout=None):
        code = request.full_url.rsplit("/api/training-link/", 1)[1]
        details = self.course.invite_details(urllib.parse.unquote(code))
        if details is None:
            raise urllib.error.HTTPError(request.full_url, 404, "Not found", {}, io.BytesIO(b"{}"))
        body = json.dumps(details).encode()

        class Answer(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        return Answer(body)

    def _send(self, *, to_address, subject, text_body, **kwargs):
        from rfone_data_store.technical import account_email
        if self.on_send:
            self.on_send()
        if self.fail_send:
            raise account_email.EmailSendError("the email service refused the message")
        self.sent.append((to_address, text_body))

    def _hire(self, location, name="New Server"):
        hid = os.urandom(10).hex()
        self.store.add_hire({"id": hid, "name": name, "location": location, "created": "2026-11-22T10:00:00"})
        return hid

    def _counts(self):
        with self.factory() as db:
            return (len(list(db.scalars(select(en.EnrollmentInvitation)))), len(list(db.scalars(select(m.Employee)))),
                    len(list(db.scalars(select(m.RFOneAccountDomainAccess)))), len(list(db.scalars(select(m.RFOneAccount)))))

    def _activate(self, link_token):
        self.client.get(f"/training/activate/{link_token}")
        page = self.client.get("/training/activate").get_data(as_text=True)
        csrf = base.CSRF_RE.search(page).group(1)
        return self.client.post("/training/activate", data={
            "csrf_token": csrf, "first_name": "Nora", "last_name": "Trainee", "phone": "",
            "password": "Trainee-Pass-2026!", "password_confirm": "Trainee-Pass-2026!"})

    def _entry(self, location, site_id, email):
        before = self._counts()
        hid = self._hire(location)
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        # one invitation, one email to that address
        self.assertEqual([to for to, _ in self.sent], [email])
        with self.factory() as db:
            invitations = list(db.scalars(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == email)))
            self.assertEqual(len(invitations), 1)
            person_id = invitations[0].person_id
            card = directory.card_for_person(db, person_id)
            self.assertEqual(directory.employee_site_ids(db, card.id), {site_id})
            rows = list(db.scalars(select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == card.id)))
            self.assertEqual([(r.restaurant_id, r.restaurant_role_id) for r in rows], [(site_id, self.server_id)])
            self.assertIsNotNone(db.get(base.registry.PersonQualification, (person_id, "STUDENT")))   # Trainee
            self.assertNotIn("EMPLOYEE", people.company_statuses(db, person_id))
        # the code now carries the site the manager chose
        self.assertEqual(self.store.get_hire(hid)["training_invite"]["site"], location)
        self.assertEqual(self._counts()[2:], before[2:])   # no account and no permission before activation
        # after activation: Training only
        token = LINK_RE.search(self.sent[0][1]).group(1)
        done = self._activate(token)
        self.assertEqual(done.status_code, 302, done.get_data(as_text=True)[:400])
        with self.factory() as db:
            account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email == email))
            self.assertFalse(account.is_admin or account.is_owner)
            domains = {r.domain_code for r in db.scalars(select(m.RFOneAccountDomainAccess).where(
                m.RFOneAccountDomainAccess.account_id == account.id, m.RFOneAccountDomainAccess.enabled.is_(True)))}
            self.assertLessEqual(domains, {"TRAINING"})
            from rfone_data_store import access_profiles as profiles
            self.assertEqual(list(db.scalars(select(profiles.CompanyMembership).where(
                profiles.CompanyMembership.account_id == account.id))), [])
            # the card is still the one at the chosen site, still Trainee
            card = directory.card_for_person(db, people.person_for_account(db, account.id).id)
            self.assertEqual(directory.employee_site_ids(db, card.id), {site_id})
        self.assertEqual(len(self.sent), 1)
        return hid

    # ------------------------------------------------------------------ 1. WP and MD
    def test_winter_park_entry(self):
        self._entry("Winter Park", self.wp_id, "wp.server@example.invalid")

    def test_mount_dora_entry(self):
        self._entry("Mount Dora", self.md_id, "md.server@example.invalid")

    # ------------------------------------------------------------------ automatic resend (same code, same email)
    def _resend_flow(self, location, site_id, email):
        hid = self._hire(location)
        self.assertTrue(self.course.request_invite(hid, email)[0])
        code = self.store.get_hire(hid)["training_invite"]["code"]
        with self.factory() as db:
            first = db.scalar(select(en.EnrollmentInvitation))
            first_id, first_digest = first.id, first.token_digest
            card_id = directory.card_for_person(db, first.person_id).id
        before = self._counts()
        old_token = LINK_RE.search(self.sent[0][1]).group(1)
        # asked again while the email service refuses it: nothing changes, the link already received still works
        self.fail_send = True
        ok, message = self.course.request_invite(hid, email)
        self.fail_send = False
        self.assertFalse(ok)
        self.assertIn("still works", message)
        self.assertEqual(len(self.sent), 1)
        with self.factory() as db:
            row = db.get(en.EnrollmentInvitation, first_id)
            self.assertEqual((row.token_digest, row.revoked_at, row.consumed_at), (first_digest, None, None))
            self.assertIsNotNone(en.lookup(db, old_token))
            self.assertEqual(db.scalar(select(m.EmployeeDirectoryEvent.id).where(
                m.EmployeeDirectoryEvent.action == "SERVER_COURSE_RESEND")), None)
        self.assertEqual(self._counts(), before)
        # asked again: same code, same invitation, link sent again to the same address
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        self.assertEqual(self.store.get_hire(hid)["training_invite"]["code"], code)
        self.assertEqual([to for to, _ in self.sent], [email, email])
        self.assertEqual(self._counts(), before)   # no second invitation, card, account or permission
        with self.factory() as db:
            rows = list(db.scalars(select(en.EnrollmentInvitation)))
            self.assertEqual([(r.id, r.revoked_at, r.consumed_at) for r in rows], [(first_id, None, None)])
            self.assertNotEqual(rows[0].token_digest, first_digest)
            self.assertEqual(directory.card_for_person(db, rows[0].person_id).id, card_id)
            self.assertEqual(directory.employee_site_ids(db, card_id), {site_id})
            new_token = LINK_RE.search(self.sent[1][1]).group(1)
            self.assertIsNone(en.lookup(db, old_token))        # only the newest email's link works
            self.assertIsNotNone(en.lookup(db, new_token))
            actions = [e.action for e in db.scalars(select(m.EmployeeDirectoryEvent).where(
                m.EmployeeDirectoryEvent.employee_id == card_id).order_by(m.EmployeeDirectoryEvent.id))]
            self.assertEqual(actions[-2:], ["SERVER_COURSE_INVITE", "SERVER_COURSE_RESEND"])
        # at once again: the limit of one per minute, nothing sent
        self.assertFalse(self.course.request_invite(hid, email)[0])
        self.assertEqual(len(self.sent), 2)
        # activated: no link, the person is sent to sign in
        self.assertEqual(self._activate(new_token).status_code, 302)
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        self.assertIn("already activated", message)
        self.assertIn("/training/access", message)   # the Training sign-in page
        self.assertEqual(len(self.sent), 2)
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)
            self.assertEqual(len(list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.email == email)))), 1)
            self.assertEqual(len(list(db.scalars(select(m.Employee)))), 1)

    def _activated_during_the_resend(self, location, site_id, email):
        """The candidate activates with the link already received while the new email is being sent: the
        activated invitation is never reopened and the new link never works."""
        hid = self._hire(location)
        self.assertTrue(self.course.request_invite(hid, email)[0])
        old_token = LINK_RE.search(self.sent[0][1]).group(1)
        with self.factory() as db:
            first = db.scalar(select(en.EnrollmentInvitation)); first_id, first_digest = first.id, first.token_digest
        self.on_send = lambda: self.assertEqual(self._activate(old_token).status_code, 302)
        ok, message = self.course.request_invite(hid, email)
        self.on_send = None
        self.assertTrue(ok, message)
        self.assertIn("already activated", message)
        with self.factory() as db:
            row = db.get(en.EnrollmentInvitation, first_id)
            self.assertIsNotNone(row.consumed_at)
            self.assertEqual(row.token_digest, first_digest)
            self.assertIsNone(en.lookup(db, LINK_RE.search(self.sent[1][1]).group(1)))
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)
            self.assertEqual(len(list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.email == email)))), 1)
            card = directory.card_for_person(db, row.person_id)
            self.assertEqual(directory.employee_site_ids(db, card.id), {site_id})

    def test_activated_during_resend_winter_park(self):
        self._activated_during_the_resend("Winter Park", self.wp_id, "wp.race@example.invalid")

    def test_activated_during_resend_mount_dora(self):
        self._activated_during_the_resend("Mount Dora", self.md_id, "md.race@example.invalid")

    def test_resend_winter_park(self):
        self._resend_flow("Winter Park", self.wp_id, "wp.again@example.invalid")

    def test_resend_mount_dora(self):
        self._resend_flow("Mount Dora", self.md_id, "md.again@example.invalid")

    def test_no_resend_when_the_code_or_the_email_does_not_match(self):
        hid = self._hire("Winter Park")
        self.assertTrue(self.course.request_invite(hid, "first@example.invalid")[0])
        code = self.store.get_hire(hid)["training_invite"]["code"]
        with self.factory() as db:
            digest = db.scalar(select(en.EnrollmentInvitation)).token_digest
        # the same code, but the course record now gives another email: refused, nothing sent
        self.store.update_hire(hid, lambda h: h["training_invite"].update(email="other@example.invalid"))
        response = self.client.post("/training/courses/server/invite", json={"code": code})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "refused")
        # another email from the course page: a new code, never the first invitation's link
        self.store.update_hire(hid, lambda h: h["training_invite"].update(email="first@example.invalid"))
        self.course.request_invite(hid, "second@example.invalid")
        self.assertNotEqual(self.store.get_hire(hid)["training_invite"]["code"], code)
        with self.factory() as db:
            first = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == "first@example.invalid"))
            self.assertEqual((first.token_digest, first.revoked_at), (digest, None))
        self.assertEqual([to for to, _ in self.sent].count("first@example.invalid"), 1)
        self.assertNotIn("other@example.invalid", [to for to, _ in self.sent])

    # ------------------------------------------------------------------ 2. never a default site
    def test_a_hire_without_a_site_gets_no_code_and_nothing_is_created(self):
        before = self._counts()
        hid = self._hire("")
        ok, message = self.course.request_invite(hid, "nosite@example.invalid")
        self.assertFalse(ok)
        self.assertIn("training site", message)
        self.assertNotIn("training_invite", self.store.get_hire(hid))
        self.assertEqual((self._counts(), self.sent), (before, []))

    def test_a_code_without_a_known_site_is_refused_at_training(self):
        before = self._counts()
        for location in ("", "Orlando"):
            hid = self._hire(location)
            code = f"{hid}.{'A' * 32}"
            self.store.update_hire(hid, lambda h: h.__setitem__("training_invite", {
                "email": "x@example.invalid", "code": code, "at": self.course._now().isoformat(timespec="seconds"),
                "sent": False, **({"site": location} if location else {})}))
            response = self.client.post("/training/courses/server/invite", json={"code": code})
            self.assertEqual(response.status_code, 409)
            self.assertIn("training site", response.get_json()["message"])
        self.assertEqual((self._counts(), self.sent), (before, []))

    def test_site_missing_or_not_unique_in_registry_is_refused(self):
        with self.factory() as db:
            db.get(m.Restaurant, self.md_id).name = "Somewhere else"
            db.commit()
        before = self._counts()
        ok, message = self.course.request_invite(self._hire("Mount Dora"), "md2@example.invalid")
        self.assertFalse(ok)
        self.assertIn("training site", message)
        self.assertEqual((self._counts(), self.sent), (before, []))

    def test_a_site_without_the_server_role_is_refused(self):
        with self.factory() as db:
            db.get(m.RestaurantRole, self.server_id).active = False
            db.commit()
        before = self._counts()
        ok, message = self.course.request_invite(self._hire("Winter Park"), "wp2@example.invalid")
        self.assertFalse(ok)
        self.assertIn("Server role", message)
        self.assertEqual((self._counts(), self.sent), (before, []))

    # ------------------------------------------------------------------ 3. codes issued before the switch
    def test_codes_issued_before_the_switch(self):
        # an RF-One invitation already sent (no card, no site) stays active and usable
        with self.factory() as db:
            stamp = en.now()
            legacy = en.EnrollmentInvitation(token_digest=en.digest("L" * 43), email="earlier@example.invalid",
                                             name="", phone="", created_by_id=self.trainer_id, created_at=stamp,
                                             expires_at=stamp + en.timedelta(hours=48), failed_attempts=0)
            db.add(legacy); db.commit()
        # a course code still valid, issued without a site, for a hire the manager put at Mount Dora
        hid = self._hire("Mount Dora")
        code = f"{hid}.{'B' * 32}"
        self.store.update_hire(hid, lambda h: h.__setitem__("training_invite", {
            "email": "pending@example.invalid", "code": code,
            "at": self.course._now().isoformat(timespec="seconds"), "sent": False}))
        response = self.client.post("/training/courses/server/invite", json={"code": code})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.store.get_hire(hid)["training_invite"]["site"], "Mount Dora")
        with self.factory() as db:
            invitation = db.scalar(select(en.EnrollmentInvitation).where(
                en.EnrollmentInvitation.email == "pending@example.invalid"))
            self.assertEqual(directory.employee_site_ids(db, directory.card_for_person(db, invitation.person_id).id),
                             {self.md_id})
            self.assertIsNotNone(en.lookup(db, "L" * 43))   # the earlier invitation is untouched
        self.assertEqual([to for to, _ in self.sent], ["pending@example.invalid"])
        # an invitation already sent by the course keeps its state
        sent_hid = self._hire("Winter Park")
        self.store.update_hire(sent_hid, lambda h: h.__setitem__("training_invite", {
            "email": "sent@example.invalid", "code": f"{sent_hid}.{'C' * 32}", "at": "2026-11-20T10:00:00+00:00",
            "sent": True}))
        with patch.object(self.course, "training_ready", return_value=True):
            self.assertEqual(self.course.status(self.store.get_hire(sent_hid)),
                             {"state": "invited", "email": "sent@example.invalid"})


# Only this file's tests: the inherited set-up is reused, its tests run in their own module.
for _name in dir(base.RegistryTrainingHttpTest):
    if _name.startswith("test_") and _name not in ServerCourseInviteTest.__dict__:
        setattr(ServerCourseInviteTest, _name, None)


if __name__ == "__main__":
    unittest.main()
