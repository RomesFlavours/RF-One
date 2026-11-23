#!/usr/bin/env python
"""REGISTRY_MULTISITE_001 — the Server Course automatic invitation; the invitation belongs to the person
(Product Owner 2026-11-22). Course side (Server Course/rf_training.py, local store in a temporary folder) and
Training side (POST /training/courses/server/invite, throwaway SQLite) joined end to end: the course's request
goes to the Training test client, Training's call back reads the course's own record.

For a person WITHOUT a site, a person ASSIGNED TO WP and a person ASSIGNED TO MD (Registry cards made before):
  1. one invitation, one email; no site is required, none is assigned or changed (the card keeps exactly its
     sites); the course's Server role is the one of Registry's catalog (stored as a WP role, like on AWS) and is
     noted on the card as the role trained for; no account or permission before activation, only Training after.
  2. asking again (same code, same email): a refused send changes nothing and the link already received keeps
     working; a successful resend uses the same invitation with the new link; no second invitation or account;
     once activated: never reopened (also when activated while the new email is being sent), sign in.
  3. another code or email: no resend. A code without a role indication, or a catalog without a unique Server
     role: the invitation is still sent, without a role.
  4. codes issued before (with or without a site in the course record) are usable; an active RF-One invitation
     stays usable.
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
from rfone_data_store.training import workspace as _workspace  # noqa: E402,F401  (its tables exist from the first test)

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
            # stored with Winter Park's restaurant, as on AWS: Registry reads it from the one catalog
            server = m.RestaurantRole(name="Server", code="SERVER", restaurant_id=self.wp_id); db.add(server); db.flush()
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

    PEOPLE = {"none": None, "wp": "wp_id", "md": "md_id"}

    def _person(self, kind, email):
        """The Registry card of the person before Training: none, or assigned (only) to WP or to MD."""
        if kind == "none":
            return None, set()
        site_id = getattr(self, self.PEOPLE[kind])
        with self.factory() as db:
            card = directory.create_person(db, display_name=f"Person {kind.upper()}", email=email,
                                           restaurant_id=site_id, role_id=self.cook_id, area_id=self.area_id)
            db.commit()
            return card.id, {site_id}

    def _card_of(self, db, email):
        invitation = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == email))
        return invitation, directory.card_for_person(db, invitation.person_id)

    def _flow(self, kind):
        email = f"{kind}.server@example.invalid"
        card_before, sites_before = self._person(kind, email)
        before = self._counts()
        hid = self._hire("")                      # the course record needs no site either
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        self.assertEqual([to for to, _ in self.sent], [email])                      # one email
        with self.factory() as db:
            invitation, card = self._card_of(db, email)
            first_id, first_digest = invitation.id, invitation.token_digest
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)   # one invitation
            if card_before is not None:
                self.assertEqual(card.id, card_before)                               # the person's own card
            self.assertEqual(directory.employee_site_ids(db, card.id), sites_before)  # no site assigned/changed
            self.assertIsNotNone(db.get(base.registry.PersonQualification, (invitation.person_id, "STUDENT")))
            noted = db.scalar(select(m.EmployeeDirectoryEvent).where(m.EmployeeDirectoryEvent.employee_id == card.id,
                              m.EmployeeDirectoryEvent.action == "TRAINING_ROLE"))
            self.assertEqual((noted.details["role_id"], noted.details["role"]), (self.server_id, "Server"))
            card_id = card.id
        after_invite = self._counts()
        self.assertEqual(after_invite[2:], before[2:])        # no account, no permission before activation
        old_token = LINK_RE.search(self.sent[0][1]).group(1)

        # asked again while the email service refuses it: nothing changes, the received link still works
        self.fail_send = True
        ok, message = self.course.request_invite(hid, email)
        self.fail_send = False
        self.assertFalse(ok)
        self.assertIn("still works", message)
        with self.factory() as db:
            row = db.get(en.EnrollmentInvitation, first_id)
            self.assertEqual((row.token_digest, row.revoked_at, row.consumed_at), (first_digest, None, None))
            self.assertIsNotNone(en.lookup(db, old_token))
        self.assertEqual((len(self.sent), self._counts()), (1, after_invite))

        # asked again: same code, same invitation, new link to the same address
        code = self.store.get_hire(hid)["training_invite"]["code"]
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        self.assertEqual(self.store.get_hire(hid)["training_invite"]["code"], code)
        self.assertEqual([to for to, _ in self.sent], [email, email])
        self.assertEqual(self._counts(), after_invite)          # no second invitation, card, account or permission
        new_token = LINK_RE.search(self.sent[1][1]).group(1)
        with self.factory() as db:
            rows = list(db.scalars(select(en.EnrollmentInvitation)))
            self.assertEqual([(r.id, r.revoked_at, r.consumed_at) for r in rows], [(first_id, None, None)])
            self.assertIsNone(en.lookup(db, old_token))
            self.assertIsNotNone(en.lookup(db, new_token))
            self.assertEqual(directory.employee_site_ids(db, card_id), sites_before)

        # activation: Training only, sites unchanged; asking again afterwards: sign in, nothing sent
        self.assertEqual(self._activate(new_token).status_code, 302)
        with self.factory() as db:
            account = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email == email))
            self.assertFalse(account.is_admin or account.is_owner)
            domains = {r.domain_code for r in db.scalars(select(m.RFOneAccountDomainAccess).where(
                m.RFOneAccountDomainAccess.account_id == account.id, m.RFOneAccountDomainAccess.enabled.is_(True)))}
            self.assertLessEqual(domains, {"TRAINING"})
            from rfone_data_store import access_profiles as profiles
            self.assertEqual(list(db.scalars(select(profiles.CompanyMembership).where(
                profiles.CompanyMembership.account_id == account.id))), [])
            self.assertEqual(directory.employee_site_ids(db, card_id), sites_before)
        ok, message = self.course.request_invite(hid, email)
        self.assertTrue(ok, message)
        self.assertIn("already activated", message)
        self.assertIn("/training/access", message)
        self.assertEqual(len(self.sent), 2)
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)
            self.assertEqual(len(list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.email == email)))), 1)

    def test_person_without_a_site(self):
        self._flow("none")

    def test_person_assigned_to_winter_park(self):
        self._flow("wp")

    def test_person_assigned_to_mount_dora(self):
        self._flow("md")

    def _activated_during_the_resend(self, kind):
        email = f"{kind}.race@example.invalid"
        _card, sites = self._person(kind, email)
        hid = self._hire("")
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
            self.assertIsNotNone(row.consumed_at)                       # never reopened
            self.assertEqual(row.token_digest, first_digest)
            self.assertIsNone(en.lookup(db, LINK_RE.search(self.sent[1][1]).group(1)))
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 1)
            self.assertEqual(directory.employee_site_ids(db, directory.card_for_person(db, row.person_id).id), sites)

    def test_activated_during_resend_without_a_site(self):
        self._activated_during_the_resend("none")

    def test_activated_during_resend_wp(self):
        self._activated_during_the_resend("wp")

    def test_activated_during_resend_md(self):
        self._activated_during_the_resend("md")

    def test_no_resend_when_the_code_or_the_email_does_not_match(self):
        hid = self._hire("Winter Park")
        self.assertTrue(self.course.request_invite(hid, "first@example.invalid")[0])
        code = self.store.get_hire(hid)["training_invite"]["code"]
        with self.factory() as db:
            digest = db.scalar(select(en.EnrollmentInvitation)).token_digest
        self.store.update_hire(hid, lambda h: h["training_invite"].update(email="other@example.invalid"))
        response = self.client.post("/training/courses/server/invite", json={"code": code})
        self.assertEqual((response.status_code, response.get_json()["status"]), (409, "refused"))
        self.store.update_hire(hid, lambda h: h["training_invite"].update(email="first@example.invalid"))
        self.course.request_invite(hid, "second@example.invalid")
        self.assertNotEqual(self.store.get_hire(hid)["training_invite"]["code"], code)
        with self.factory() as db:
            first = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == "first@example.invalid"))
            self.assertEqual((first.token_digest, first.revoked_at), (digest, None))
        self.assertEqual([to for to, _ in self.sent].count("first@example.invalid"), 1)
        self.assertNotIn("other@example.invalid", [to for to, _ in self.sent])

    def test_without_a_role_indication_or_a_unique_server_role_the_invitation_is_still_sent(self):
        with patch.object(self.course, "ROLE", ""):                     # a course that indicates no role
            self.assertTrue(self.course.request_invite(self._hire(""), "norole@example.invalid")[0])
        with self.factory() as db:
            db.get(m.RestaurantRole, self.server_id).active = False       # no Server role in the catalog
            db.commit()
        self.assertTrue(self.course.request_invite(self._hire(""), "noserver@example.invalid")[0])
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(en.EnrollmentInvitation)))), 2)
            self.assertIsNone(db.scalar(select(m.EmployeeDirectoryEvent.id).where(
                m.EmployeeDirectoryEvent.action == "TRAINING_ROLE")))
            self.assertEqual(len(list(db.scalars(select(m.EmployeeAssignment)))), 0)
        self.assertEqual(len(self.sent), 2)

    def test_codes_issued_before_and_active_invitations(self):
        with self.factory() as db:
            stamp = en.now()
            db.add(en.EnrollmentInvitation(token_digest=en.digest("L" * 43), email="earlier@example.invalid",
                                           name="", phone="", created_by_id=self.trainer_id, created_at=stamp,
                                           expires_at=stamp + en.timedelta(hours=48), failed_attempts=0))
            db.commit()
        for i, record in enumerate(({}, {"site": "Mount Dora"})):        # without a site, or with the older site key
            hid = self._hire("")
            code = f"{hid}.{chr(66 + i) * 32}"
            self.store.update_hire(hid, lambda h, r=record, c=code, n=i: h.__setitem__("training_invite", {
                "email": f"pending{n}@example.invalid", "code": c,
                "at": self.course._now().isoformat(timespec="seconds"), "sent": False, **r}))
            response = self.client.post("/training/courses/server/invite", json={"code": code})
            self.assertEqual(response.status_code, 200, response.get_json())
        with self.factory() as db:
            for n in (0, 1):
                _invitation, card = self._card_of(db, f"pending{n}@example.invalid")
                self.assertEqual(directory.employee_site_ids(db, card.id), set())
            self.assertIsNotNone(en.lookup(db, "L" * 43))                 # the earlier invitation is untouched
        self.assertEqual([to for to, _ in self.sent], ["pending0@example.invalid", "pending1@example.invalid"])


# Only this file's tests: the inherited set-up is reused, its tests run in their own module.
for _name in dir(base.RegistryTrainingHttpTest):
    if _name.startswith("test_") and _name not in ServerCourseInviteTest.__dict__:
        setattr(ServerCourseInviteTest, _name, None)


if __name__ == "__main__":
    unittest.main()
