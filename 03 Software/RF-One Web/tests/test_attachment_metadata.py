"""Attachment descriptors only: fake IMAP, isolated databases, no file downloads/AI."""
from dataclasses import replace
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_incoming_email as fixture
from sqlalchemy import select, text
from rfone_data_store import incoming_email as incoming, models as m, email_service as outgoing
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.incoming_email_worker import check_one
from rfone_data_store.technical.imap_mailbox import HeaderMailboxClient, STRUCTURE_FETCH
from rfone_data_store.technical.imap_structure import fetch_fields, attachment_metadata, StructureError
from run_email_control_local import prepare_database, upgrade_database, _apply_local_migration

TEXT = b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 20 1)'
HTML = b'("TEXT" "HTML" NIL NIL NIL "7BIT" 45 1)'
PDF = b'("APPLICATION" "PDF" ("NAME" "cv.pdf") NIL NIL "BASE64" 124000 NIL ("ATTACHMENT" ("FILENAME" "cv.pdf")))'
FILES = (dict(part='2', name='cv.pdf', content_type='application/pdf', size_bytes=124000,
              encoding='BASE64', disposition='attachment'),)


def metadata(body):
    return attachment_metadata(fetch_fields([b'1 (UID 11 BODYSTRUCTURE ' + body + b')'], 11))


class StructureTests(unittest.TestCase):
    def test_nested_alternative_body_and_pdf_attachment(self):
        body = b'((' + TEXT + HTML + b' "ALTERNATIVE")' + PDF + b' "MIXED")'
        files, error = metadata(body)
        self.assertIsNone(error)
        self.assertEqual(files, FILES)

    def test_no_attachments_is_distinct_from_missing_structure(self):
        self.assertEqual(metadata(b'(' + TEXT + HTML + b' "ALTERNATIVE")'), ((), None))
        self.assertEqual(attachment_metadata({b'UID':11}), (None, 'UNAVAILABLE'))

    def test_escaped_quotes_and_parentheses_in_filename(self):
        body = PDF.replace(b'cv.pdf', b'report \\"final\\" (v2).pdf')
        files, error = metadata(body)
        self.assertIsNone(error)
        self.assertEqual(files[0]['name'], 'report "final" (v2).pdf')

    def test_literal_filename_is_not_interpreted_as_protocol(self):
        filename = b'BODYSTRUCTURE (not syntax).pdf'
        prefix = b'1 (UID 11 BODYSTRUCTURE ("APPLICATION" "PDF" ("NAME" {' + str(len(filename)).encode() + b'}'
        fields = fetch_fields([(prefix, filename), b') NIL NIL "BASE64" 200 NIL ("ATTACHMENT" NIL)))'], 11)
        files, error = attachment_metadata(fields)
        self.assertIsNone(error)
        self.assertEqual(files[0]['name'], filename.decode())

    def test_rfc2231_extended_and_continued_filename(self):
        body = b'("APPLICATION" "PDF" NIL NIL NIL "BASE64" 200 NIL ("ATTACHMENT" ("FILENAME*0*" "utf-8\'\'r%C3%A9sum%C3%A9" "FILENAME*1*" "%20Alex.pdf")))'
        files, error = metadata(body)
        self.assertIsNone(error)
        self.assertEqual(files[0]['name'], 'résumé Alex.pdf')

    def test_encoded_word_filename(self):
        body = PDF.replace(b'cv.pdf', b'=?UTF-8?Q?r=C3=A9sum=C3=A9.pdf?=')
        self.assertEqual(metadata(body)[0][0]['name'], 'résumé.pdf')

    def test_inline_file_is_labelled_and_unnamed_binary_is_not_lost(self):
        image = b'("IMAGE" "PNG" ("NAME" "logo.png") "<logo>" NIL "BASE64" 200 NIL ("INLINE" ("FILENAME" "logo.png")))'
        unnamed = b'("APPLICATION" "OCTET-STREAM" NIL NIL NIL "BASE64" 500 NIL ("ATTACHMENT" NIL))'
        files, error = metadata(b'(' + TEXT + image + unnamed + b' "MIXED")')
        self.assertIsNone(error)
        self.assertEqual(len(files), 2)
        self.assertEqual(files[0]['disposition'], 'inline')
        self.assertIsNone(files[1]['name'])
        self.assertEqual(files[1]['content_type'], 'application/octet-stream')

    def test_attached_email_is_one_file_not_its_nested_contents(self):
        envelope = b'(NIL NIL NIL NIL NIL NIL NIL NIL NIL NIL)'
        body = b'("MESSAGE" "RFC822" ("NAME" "forwarded.eml") NIL NIL "7BIT" 2048 ' + envelope + b' (' + TEXT + PDF + b' "MIXED") 10 NIL ("ATTACHMENT" ("FILENAME" "forwarded.eml")))'
        files, error = metadata(body)
        self.assertIsNone(error)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['name'], 'forwarded.eml')
        self.assertEqual(files[0]['content_type'], 'message/rfc822')

    def test_unknown_container_size_is_not_invented(self):
        files, error = metadata(b'(' + TEXT + b' "MIXED" NIL ("ATTACHMENT" ("FILENAME" "bundle.mime")))')
        self.assertIsNone(error)
        self.assertIsNone(files[0]['size_bytes'])

    def test_semantically_invalid_structure_does_not_claim_no_attachments(self):
        self.assertEqual(metadata(b'("APPLICATION")'), (None, 'INVALID_STRUCTURE'))

    def test_header_literal_cannot_spoof_bodystructure(self):
        header = b'Subject: BODYSTRUCTURE ' + PDF + b'\r\n\r\n'
        prefix = b'1 (BODY[HEADER.FIELDS (SUBJECT)]<0> {' + str(len(header)).encode() + b'}'
        fields = fetch_fields([(prefix, header), b' UID 11 BODYSTRUCTURE ' + TEXT + b')'], 11)
        self.assertEqual(attachment_metadata(fields), ((), None))

    def test_response_limits_uid_selection_and_unsolicited_flags(self):
        fields = fetch_fields([b'9 (UID 99 FLAGS (\\Seen))', b'1 (UID 11 BODYSTRUCTURE ' + TEXT + b')',
                               b'1 (UID 11 FLAGS (\\Seen))'], 11)
        self.assertEqual(attachment_metadata(fields), ((), None))
        self.assertIsNone(fetch_fields([b'9 (UID 99 BODYSTRUCTURE ' + PDF + b')'], 11))
        for data in [[b'1 (UID 11 BODYSTRUCTURE ' + b'(' * 60 + b'NIL' + b')' * 60 + b')'],
                     [(b'1 (UID 11 BODYSTRUCTURE {999}', b'no')]]:
            with self.assertRaises(StructureError):
                fetch_fields(data, 11)


class AttachmentWorkerTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.IncomingTests()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def metadata_poll(self, files=FILES, error=None, during=None, seconds=61):
        f = self.f
        f.stamp += timedelta(seconds=seconds)
        def factory(box, password):
            client = fixture.FakeClient(box, password, f.server)
            def lookup(uid):
                if during:
                    during(uid)
                return files, error
            client.attachments_for = lookup
            return client
        return check_one(f.factory, f.vault, client_factory=factory, clock=lambda:f.stamp)

    def arrival(self):
        with self.f.factory() as db:
            return db.scalar(select(incoming.Arrival))

    def pending_arrival(self):
        bid = self.f.add(); self.f.poll(); self.f.headers(11); self.f.poll(61)
        return bid

    def test_new_message_metadata_commits_with_arrival(self):
        self.f.add(); self.f.poll(); self.f.headers(11)
        self.f.server['headers'] = [replace(self.f.server['headers'][0], attachments=FILES)]
        self.f.poll(61)
        row = self.arrival()
        self.assertEqual(row.attachments, list(FILES))
        self.assertIsNotNone(row.attachments_checked_at)

    def test_backfill_enriches_existing_arrival_without_duplicate_or_cursor_change(self):
        bid = self.pending_arrival()
        self.assertIsNone(self.arrival().attachments_checked_at)
        self.metadata_poll()
        self.assertEqual(self.f.count(), 1)
        self.assertEqual(self.arrival().attachments, list(FILES))
        self.assertEqual(self.f.box(bid).last_uid, 11)
        with self.f.factory() as db:
            run = db.scalar(select(incoming.MailboxCheck).order_by(incoming.MailboxCheck.id.desc()))
            self.assertEqual(run.found, 0)

    def test_changed_source_is_never_looked_up_with_old_uid(self):
        bid = self.pending_arrival()
        with self.f.factory.begin() as db:
            incoming.configure(db, owner=1, mailbox_id=bid, label='Archive', address='mail@example.test',
                host='imaps.aruba.it', username='mail@example.test', folder='Archive', interval_seconds=60)
        self.metadata_poll(during=lambda uid:self.fail('An old source UID must not be fetched'))
        self.assertEqual(self.arrival().attachment_error, 'SOURCE_CHANGED')

    def test_pause_fences_attachment_metadata_as_well_as_headers(self):
        bid = self.pending_arrival()
        def pause(uid):
            with self.f.factory.begin() as db:
                incoming.control(db, owner=1, mailbox_id=bid, action='pause')
        self.metadata_poll(during=pause)
        self.assertIsNone(self.arrival().attachments_checked_at)
        self.assertFalse(self.f.box(bid).enabled)

    def test_vanished_message_is_unknown_not_empty_attachment_list(self):
        self.pending_arrival(); self.metadata_poll(files=None, error='MESSAGE_UNAVAILABLE')
        self.assertIsNone(self.arrival().attachments)
        page = self.f.client.get('/administration/email/incoming').get_data(as_text=True)
        self.assertIn('Message no longer available', page)
        self.assertNotIn('No attachments', page)

    def test_metadata_is_escaped_and_still_owner_scoped(self):
        self.pending_arrival()
        files = (dict(FILES[0], name='<img src=x onerror=alert(1)>.pdf'),)
        self.metadata_poll(files=files)
        page = self.f.client.get('/administration/email/incoming').get_data(as_text=True)
        self.assertIn('&lt;img', page)
        self.assertNotIn('<img src=x', page)
        self.assertIn('application/pdf', page)
        self.assertIn('121.1 KiB', page)
        self.assertNotIn(' download=', page)
        self.f.login(2)
        self.assertNotIn('application/pdf', self.f.client.get('/administration/email/incoming').get_data(as_text=True))

    def test_pending_and_verified_empty_lists_are_different(self):
        self.pending_arrival()
        page = self.f.client.get('/administration/email/incoming').get_data(as_text=True)
        self.assertIn('Attachment list pending', page)
        self.metadata_poll(files=())
        page = self.f.client.get('/administration/email/incoming').get_data(as_text=True)
        self.assertIn('No attachments', page)
        self.assertNotIn('Attachment list pending', page)

    def test_backfill_respects_shared_twenty_fetch_budget(self):
        bid = self.f.add(); self.f.poll()
        with self.f.factory.begin() as db:
            box = db.get(incoming.Mailbox, bid); box.last_uid = 35
            for uid in range(11,36):
                db.add(incoming.Arrival(mailbox_id=bid,generation=1,uidvalidity='100',uid=uid,
                    sender='s@example.test',recipient='r@example.test',subject='Existing message'))
        self.f.server['next'] = 36
        calls = []
        self.metadata_poll(during=lambda uid:calls.append(uid))
        self.assertEqual(len(calls),20)
        self.metadata_poll(during=lambda uid:calls.append(uid),seconds=2)
        self.assertEqual(len(calls),25)
        self.assertEqual(self.f.count(),25)


class MetadataProtocolTests(unittest.TestCase):
    def test_existing_message_fetch_requests_structure_only_in_readonly_folder(self):
        box = type('Box', (), dict(host='imaps.aruba.it',username='test@example.test',folder='INBOX'))()
        commands=[]
        class Connection:
            def login(self,*args):pass
            def select(self,folder,readonly):
                self.readonly=readonly
                return 'OK',[b'1']
            def status(self,*args):return 'OK',[b'"INBOX" (UIDVALIDITY 100 UIDNEXT 12)']
            def uid(self,*args):
                commands.append(args)
                return 'OK',[b'1 (UID 11 BODYSTRUCTURE '+PDF+b')']
            def logout(self):pass
        connection=Connection()
        client=HeaderMailboxClient(box,'not-real',resolver=lambda host:'93.184.216.34',factory=lambda *args:connection)
        snap=client.open()
        result,error=client.attachments_for(11)
        client.verify(snap);client.close()
        self.assertTrue(connection.readonly)
        self.assertEqual(commands,[('fetch','11',STRUCTURE_FETCH)])
        self.assertEqual(result[0]['name'],'cv.pdf')
        self.assertIsNone(error)


class SandboxUpgradeTests(unittest.TestCase):
    def test_explicit_upgrade_backs_up_and_preserves_existing_metadata_and_cursor(self):
        with tempfile.TemporaryDirectory(prefix='rfone_test_attachment_upgrade_') as directory:
            path=Path(directory)/'existing.db'
            engine=create_configured_engine('sqlite:///'+path.as_posix(),sqlite_immediate=True)
            with engine.begin() as db:
                m.Base.metadata.create_all(db,tables=[m.RFOneAccount.__table__]+outgoing.TABLES)
                _apply_local_migration(db,'i9a120261117_incoming_email_monitoring.py')
                db.execute(text('CREATE TABLE _email_control_sandbox (version VARCHAR(30) NOT NULL)'))
                db.execute(text("INSERT INTO _email_control_sandbox VALUES ('i9a120261117')"))
                db.execute(m.RFOneAccount.__table__.insert().values(id=1,username='local',display_name='Local',password_hash='unused',is_owner=True,is_admin=True))
            factory=create_session_factory(engine)
            with factory.begin() as db:
                box=incoming.configure(db,owner=1,credential_ref='local:'+'0'*32,label='Existing',address='r@example.test',
                    host='imaps.aruba.it',username='r@example.test',folder='INBOX',interval_seconds=60)
                box.uidvalidity,box.last_uid='100',11
                db.flush();bid=box.id
                db.execute(text("INSERT INTO email_arrivals (id,mailbox_id,generation,uidvalidity,uid,sender,recipient,subject,detected_at) VALUES ('old',:bid,1,'100',11,'s@example.test','r@example.test','Existing CV',CURRENT_TIMESTAMP)"),dict(bid=bid))
            engine.dispose()
            with self.assertRaises(RuntimeError):prepare_database(path)
            backup=upgrade_database(path)
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(str(backup))) as db:
                self.assertNotIn('attachments',{r[1] for r in db.execute('PRAGMA table_info(email_arrivals)')})
                self.assertEqual(db.execute('SELECT subject FROM email_arrivals').fetchone()[0],'Existing CV')
            engine=prepare_database(path)
            try:
                with create_session_factory(engine)() as db:
                    row=db.get(incoming.Arrival,'old')
                    self.assertEqual(row.subject,'Existing CV')
                    self.assertIsNone(row.attachments_checked_at)
                    self.assertEqual(db.get(incoming.Mailbox,bid).last_uid,11)
                    self.assertEqual(db.get(incoming.Mailbox,bid).credential_ref,'local:'+'0'*32)
                self.assertIsNone(upgrade_database(path))
            finally:engine.dispose()


if __name__=='__main__':
    unittest.main()
