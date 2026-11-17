"""Standalone worker: python -m rfone_data_store.email_worker --help.

Global database lease serializes workers and persists rate limiting across
restarts. No network occurs in dry-run mode; it does not consume messages.
"""
import argparse
from datetime import timedelta
import os
import signal
import time
import uuid

from sqlalchemy import select, update
from . import email_service as e
from .database import create_configured_engine, create_session_factory
from .technical.aruba_smtp import ArubaSMTP, SendFailure, load_secret

LEASE_SECONDS = 300
MAX_ATTEMPTS = 5


def run_once(factory, transport, *, interval=2, clock=e.now):
    if interval < 1:
        raise ValueError('SMTP interval must be at least one second')
    stamp, owner = clock(), str(uuid.uuid4())
    with factory.begin() as db:
        acquired = db.execute(update(e.EmailWorkerState).where(
            e.EmailWorkerState.id == 1, e.EmailWorkerState.lease_until <= stamp
        ).values(owner=owner, lease_until=stamp + timedelta(seconds=LEASE_SECONDS),
                 heartbeat=stamp, mode='RUNNING')).rowcount
        if not acquired:
            return False
        # A process died after committing SENDING: never guess whether SMTP accepted it.
        stale = list(db.scalars(select(e.EmailRequest).where(e.EmailRequest.status == 'SENDING')))
        for row in stale:
            row.status, row.error, row.updated_at = 'UNCERTAIN', 'WORKER_INTERRUPTED', stamp
            db.execute(update(e.EmailAttempt).where(e.EmailAttempt.request_id == row.id,
                e.EmailAttempt.outcome == 'SENDING').values(
                    outcome='UNCERTAIN', error='WORKER_INTERRUPTED', finished_at=stamp))
        state = db.get(e.EmailWorkerState, 1)
        due = db.scalar(select(e.EmailWorkerState.id).where(e.EmailWorkerState.next_send_at <= stamp))
        row = None
        if due:
            row = db.scalar(select(e.EmailRequest).where(e.EmailRequest.status.in_(('QUEUED', 'RETRY')),
                e.EmailRequest.available_at <= stamp).order_by(e.EmailRequest.available_at, e.EmailRequest.id).limit(1))
        if row is None:
            state.lease_until, state.owner, state.mode = stamp, None, 'IDLE'
            return False
        # CAS is necessary even on SQLite; cancellation can race this claim.
        claimed = db.execute(update(e.EmailRequest).where(e.EmailRequest.id == row.id,
            e.EmailRequest.status.in_(('QUEUED', 'RETRY'))).values(status='SENDING',
                attempts=e.EmailRequest.attempts + 1, updated_at=stamp)).rowcount
        if not claimed:
            state.lease_until, state.owner = stamp, None
            return False
        db.refresh(row)
        request_id, number = row.id, row.attempts
        db.add(e.EmailAttempt(request_id=request_id, number=number, started_at=stamp))
        state.next_send_at = stamp + timedelta(seconds=interval)
        db.expunge(row)
    outcome, category, retry = 'ACCEPTED', None, False
    try:
        transport.send(row)
    except SendFailure as exc:
        category = exc.category
        outcome = 'UNCERTAIN' if exc.uncertain else 'FAILED'
        retry = exc.temporary and number < MAX_ATTEMPTS and not exc.uncertain
    except Exception:
        # Unknown transport bugs are conservatively uncertain; no traceback with payload.
        outcome, category = 'UNCERTAIN', 'TRANSPORT_UNKNOWN'
    finished = clock()
    with factory.begin() as db:
        # A paused old worker may not overwrite recovery performed by a new lease holder.
        owns = db.execute(update(e.EmailWorkerState).where(e.EmailWorkerState.id == 1,
            e.EmailWorkerState.owner == owner).values(owner=None, lease_until=finished,
                heartbeat=finished, next_send_at=finished + timedelta(seconds=interval), mode='IDLE')).rowcount
        if not owns:
            return True
        db.execute(update(e.EmailRequest).where(e.EmailRequest.id == request_id,
            e.EmailRequest.status == 'SENDING').values(status='RETRY' if retry else outcome,
                error=category, updated_at=finished,
                available_at=finished + timedelta(seconds=min(3600, 30 * 2 ** (number - 1))) if retry else finished))
        db.execute(update(e.EmailAttempt).where(e.EmailAttempt.request_id == request_id,
            e.EmailAttempt.number == number, e.EmailAttempt.outcome == 'SENDING').values(
                outcome=outcome, error=category, finished_at=finished))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('RFONE_DATABASE_URL'),
                        help='Explicit target, or RFONE_DATABASE_URL environment; no .env fallback')
    parser.add_argument('--send', action='store_true', help='Enable real sends (requires operator authorization)')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()
    if not args.database_url:
        parser.error('Set RFONE_DATABASE_URL or --database-url explicitly')
    if args.interval < 1:
        parser.error('--interval must be >= 1')
    factory = create_session_factory(create_configured_engine(args.database_url))
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    transport = None
    if args.send:
        transport = ArubaSMTP(load_secret(os.environ['RFONE_EMAIL_SMTP_SECRET_ID'], os.environ.get('AWS_REGION', 'us-east-1')))
    while not stopped:
        if transport:
            run_once(factory, transport, interval=args.interval)
        else:
            with factory() as db:
                db.scalar(select(e.EmailWorkerState.id).where(e.EmailWorkerState.id == 1))
            print('Email worker dry-run: database reachable; no email sent or consumed.')
        if args.once:
            break
        time.sleep(1)


if __name__ == '__main__':
    main()
