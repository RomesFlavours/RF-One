"""Independent incoming-email poller. Explicit DB target; never reads .env.

python -m rfone_data_store.incoming_email_worker --database-url sqlite:///... --run
No network connections are made without --run. Each mailbox has its own lease.
"""
import argparse
from datetime import timedelta
import os
import signal
import time
import uuid

from sqlalchemy import select, update, or_
from . import incoming_email as incoming, models as m
from . import rfone_web_session as identity
from .email_service import now, EmailWorkerState
from .database import create_configured_engine, create_session_factory
from .technical.imap_mailbox import HeaderMailboxClient, MailboxError, BATCH_SIZE
from .technical.mailbox_credentials import LocalMailboxVault, CredentialError


def check_one(factory, vault, *, client_factory=HeaderMailboxClient, clock=now):
    stamp, token = clock(), str(uuid.uuid4())
    lease_free = or_(incoming.Mailbox.lease_until.is_(None), incoming.Mailbox.lease_until <= stamp)
    with factory.begin() as db:
        # UPDATE first also serializes SQLite workers before their read transaction.
        candidate = select(incoming.Mailbox.id).join(m.RFOneAccount,
            m.RFOneAccount.id == incoming.Mailbox.owner_account_id).where(
                incoming.Mailbox.enabled.is_(True), m.RFOneAccount.status == 'ACTIVE',
                incoming.Mailbox.next_check_at <= stamp, lease_free).order_by(
                    incoming.Mailbox.next_check_at, incoming.Mailbox.id).limit(1).scalar_subquery()
        claimed = db.execute(update(incoming.Mailbox).where(incoming.Mailbox.id == candidate,
            incoming.Mailbox.enabled.is_(True), lease_free).values(
                lease_owner=token, lease_until=stamp + timedelta(seconds=incoming.LEASE_SECONDS)))
        if claimed.rowcount != 1:
            return False
        box = db.scalar(select(incoming.Mailbox).where(incoming.Mailbox.lease_owner == token))
        db.execute(update(incoming.MailboxCheck).where(incoming.MailboxCheck.mailbox_id == box.id,
            incoming.MailboxCheck.outcome == 'CHECKING').values(
                outcome='INTERRUPTED', error='CHECK_INTERRUPTED', finished_at=stamp))
        owner = db.get(m.RFOneAccount, box.owner_account_id)
        if identity.account_for_session(db, account_id=owner.id, session_version=owner.session_version) is None:
            box.enabled, box.lease_owner, box.lease_until = False, None, None
            box.last_error, box.last_checked_at = 'OWNER_INACTIVE', stamp
            db.add(incoming.MailboxCheck(mailbox_id=box.id, lease_owner=token, started_at=stamp,
                finished_at=stamp, outcome='FAILED', error='OWNER_INACTIVE'))
            return True
        run = incoming.MailboxCheck(mailbox_id=box.id, lease_owner=token, started_at=stamp)
        db.add(run)
        db.flush()
        run_id, version = run.id, box.config_version
        pending = list(db.execute(select(incoming.Arrival.id, incoming.Arrival.uid).where(
            incoming.Arrival.mailbox_id == box.id, incoming.Arrival.generation == box.generation,
            incoming.Arrival.uidvalidity == box.uidvalidity,
            incoming.Arrival.attachments_checked_at.is_(None)).order_by(
                incoming.Arrival.detected_at, incoming.Arrival.id).limit(BATCH_SIZE)))
        db.expunge(box)
    client, result, error, headers, snapshot, enriched = None, 'OK', None, [], None, []
    try:
        client = client_factory(box, vault.load(box.credential_ref))
        snapshot = client.open()
        if box.uidvalidity is None:
            result = 'BASELINED'
        elif box.uidvalidity != snapshot.uidvalidity:
            result, error = 'RESET', 'UIDVALIDITY_CHANGED'
        else:
            headers = client.headers_since(box.last_uid, snapshot)
            # Stay within the original per-check network budget, including old arrivals.
            for arrival_id, uid in pending[:max(0, BATCH_SIZE - len(headers))]:
                files, file_error = client.attachments_for(uid)
                enriched.append((arrival_id, files, file_error))
        client.verify(snapshot)
    except CredentialError:
        result, error = 'FAILED', 'CREDENTIALS_UNAVAILABLE'
    except MailboxError as exc:
        result, error = 'FAILED', exc.code if exc.code in incoming.ERRORS else 'IMAP_FAILED'
    except Exception:
        result, error = 'FAILED', 'IMAP_FAILED'
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    finished = clock()
    with factory.begin() as db:
        # Lock/fence before inserting arrivals or advancing the cursor. Pauses,
        # configuration changes and expired/reassigned leases invalidate old work.
        fenced = db.execute(update(incoming.Mailbox).where(incoming.Mailbox.id == box.id,
            incoming.Mailbox.lease_owner == token, incoming.Mailbox.config_version == version,
            incoming.Mailbox.enabled.is_(True)).values(lease_owner=None, lease_until=None)).rowcount
        if not fenced:
            db.execute(update(incoming.MailboxCheck).where(incoming.MailboxCheck.id == run_id,
                incoming.MailboxCheck.outcome == 'CHECKING').values(outcome='SUPERSEDED', finished_at=finished))
            return True
        row = db.get(incoming.Mailbox, box.id)
        count = 0
        if result != 'FAILED':
            if db.bind.dialect.name == 'sqlite':
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            for header in headers:
                saved = db.execute(insert(incoming.Arrival).values(mailbox_id=box.id, generation=box.generation,
                    uidvalidity=snapshot.uidvalidity, uid=header.uid, sender=header.sender,
                    recipient=header.recipient, subject=header.subject, message_id=header.message_id,
                    message_date=header.message_date, size_bytes=header.size_bytes,
                    attachments=list(header.attachments) if header.attachments is not None else None,
                    attachment_error=header.attachment_error,
                    attachments_checked_at=finished if header.attachments is not None or header.attachment_error else None
                    ).on_conflict_do_nothing(
                        index_elements=['mailbox_id', 'generation', 'uidvalidity', 'uid']))
                count += saved.rowcount
            for arrival_id, files, file_error in enriched:
                db.execute(update(incoming.Arrival).where(incoming.Arrival.id == arrival_id,
                    incoming.Arrival.mailbox_id == box.id, incoming.Arrival.generation == box.generation,
                    incoming.Arrival.uidvalidity == snapshot.uidvalidity).values(
                        attachments=list(files) if files is not None else None,
                        attachment_error=file_error, attachments_checked_at=finished))
            # Old source identities must never be looked up using a newly assigned UID.
            db.execute(update(incoming.Arrival).where(incoming.Arrival.mailbox_id == box.id,
                incoming.Arrival.attachments_checked_at.is_(None),
                or_(incoming.Arrival.generation != box.generation,
                    incoming.Arrival.uidvalidity != snapshot.uidvalidity)).values(
                        attachment_error='SOURCE_CHANGED', attachments_checked_at=finished))
            row.uidvalidity = snapshot.uidvalidity
            if result in ('BASELINED', 'RESET'):
                row.last_uid = snapshot.uidnext - 1
            elif headers:
                row.last_uid = max(row.last_uid, max(h.uid for h in headers))
            else:
                row.last_uid = max(row.last_uid, snapshot.uidnext - 1)
            row.failures, row.last_success_at = 0, finished
            delay = 1 if len(headers) + len(enriched) == BATCH_SIZE else row.interval_seconds
        else:
            row.failures += 1
            delay = 3600 if error == 'AUTHENTICATION_FAILED' else min(3600, row.interval_seconds * 2 ** min(row.failures, 6))
        row.last_error, row.last_checked_at = error, finished
        row.next_check_at = finished + timedelta(seconds=delay)
        db.execute(update(incoming.MailboxCheck).where(incoming.MailboxCheck.id == run_id).values(
            outcome=result, error=error, found=count, finished_at=finished))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('RFONE_DATABASE_URL'))
    parser.add_argument('--run', action='store_true', help='Enable checks of user-configured mailboxes')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not args.database_url:
        parser.error('Set --database-url or RFONE_DATABASE_URL explicitly')
    factory = create_session_factory(create_configured_engine(args.database_url, sqlite_immediate=True))
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    vault = LocalMailboxVault()
    while not stopped:
        if args.run:
            with factory.begin() as db:
                state = db.get(EmailWorkerState, incoming.RECEIVER_STATE_ID)
                if state is None:
                    raise RuntimeError('Apply the incoming email migration before starting the monitor.')
                state.heartbeat, state.mode = now(), 'CHECKING'
                state.lease_until = now() + timedelta(seconds=incoming.LEASE_SECONDS)
            try:
                check_one(factory, vault)
            except Exception:
                # Database/worker faults must not print connection strings or credentials.
                print('Incoming email monitor: check interrupted; retrying.', flush=True)
            with factory.begin() as db:
                state = db.get(EmailWorkerState, incoming.RECEIVER_STATE_ID)
                state.heartbeat, state.mode, state.lease_until = now(), 'IDLE', now()
        else:
            with factory() as db:
                db.scalar(select(incoming.Mailbox.id).limit(1))
            print('Incoming email monitor dry-run: no mailbox connections made.', flush=True)
        if args.once:
            break
        time.sleep(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        print('Incoming email monitor stopped: check the database and local configuration.', flush=True)
        raise SystemExit(1) from None
