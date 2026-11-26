"""Order-only specialization of the existing Clover Live Sync acquisition path."""
import logging
import os
import signal
import threading
from datetime import datetime, timedelta, timezone

import bootstrap  # noqa: F401
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.clover import acquisition as a
from rfone_data_store.technical.connectors.clover.historical_backfill_detail import ingest_order_item_and_modifier_detail
from rfone_data_store.technical.connectors.clover.source_guard import require_complete, require_ok
from kitchen_filter import categories_by_line, is_beverage
from store import Board, Ticket, drop_if_empty, mark_deleted, now, pending, related, save_ticket

LOG = logging.getLogger('kitchen_live_sync')

# The kitchen worker's own lock rows carry this tag, so a lock left by a crashed
# kitchen worker can be cleared in minutes instead of the general 30-minute rule.
LOCK_TAG = 'KITCHEN_BOARD'
# A kitchen cycle takes seconds; a kitchen lock older than this is a crashed worker.
KITCHEN_LOCK_STALE = timedelta(minutes=3)
# Open tickets are re-checked with Clover for this long after the order was created.
RECHECK_FOR = timedelta(hours=24)


class DetailCapture:
    """Observe the existing ingester's paginated GETs, without a second fetch."""
    def __init__(self, client):
        self.client = client
        self.merchant_id = client.merchant_id
        self.lines = []

    def get(self, path, params=None):
        result = self.client.get(path, params=params)
        if result.ok and path.endswith('/line_items'):
            self.lines.extend(result.data.get('elements', []))
        return result


def sent_only():
    """Show only dishes the server sent to the kitchen (Clover 'printed'), like the paper ticket.
    KITCHEN_BOARD_SENT_ONLY=0 shows every dish as soon as it is rung in."""
    return os.environ.get('KITCHEN_BOARD_SENT_ONLY', '1').strip() != '0'


def is_paid(order_raw):
    return order_raw.get('paymentState') == 'PAID' or order_raw.get('state') == 'locked'


def ticket_payload(order_raw, lines, beverage_ids=frozenset()):
    """Provider values stay verbatim; never infer seats, quantities or covers.
    Drinks (by Clover category) never reach the kitchen ticket."""
    food = [line for line in lines if not line.get('isOrderFee') and line.get('id') not in beverage_ids]
    shown = [line for line in food if line.get('printed') is True] if sent_only() else food
    return {
        'title': order_raw.get('title') or order_raw['id'],
        'note': order_raw.get('note'),
        # The employee Clover already returns with the order (expand=employee).
        'server': ((order_raw.get('employee') or {}).get('name') or None),
        # Bookkeeping for the minute check: what Clover had when this was read.
        'modified': order_raw.get('modifiedTime'),
        'paid': is_paid(order_raw),
        'printed_ids': sorted(line['id'] for line in lines if line.get('id') and line.get('printed') is True
                              and not line.get('isOrderFee')),
        'unsent': len(food) - len(shown),
        'lines': [{
            'id': line.get('id'), 'name': line.get('name') or '',
            'quantity': (line['unitQty'] / 1000 if line.get('unitQty') is not None else None),
            'guest': line.get('binName') or '', 'note': line.get('note'),
            'modifiers': [mod.get('name') or '' for mod in (line.get('modifications') or {}).get('elements', [])],
        } for line in shown],
    }


def _family(session, location_id, order_id):
    main = session.get(Ticket, (location_id, order_id))
    return ([main] if main is not None else []) + related(session, location_id, order_id)


def _already_read(session, location_id, raw):
    """Skip an order Clover has not modified since the board last read it.
    The 2-minute overlap would otherwise re-read every busy order about 9 times."""
    stamp = raw.get('modifiedTime')
    return stamp is not None and any(t.payload.get('modified') == stamp
                                     for t in _family(session, location_id, raw['id']))


def _process(session, client, raw, *, location_id, source_system_id, employees, lock, end):
    """Ingest one Clover order and refresh its kitchen ticket."""
    if not raw.get('id') or raw.get('createdTime') is None:
        raise ValueError('Clover order is missing its identifier or creation time')
    order, _ = a._ingest_order(session, raw, location_id=location_id,
        source_system_id=source_system_id, employee_by_source_id=employees,
        ingestion_run_id=lock.id, retrieved_at=end)
    capture = DetailCapture(client)
    ingest_order_item_and_modifier_detail(session, capture, raw, order,
        source_system_id=source_system_id, ingestion_run_id=lock.id,
        retrieved_at=end, mirror_source_record=a._mirror_source_record)
    session.flush()
    categories = categories_by_line(session, location_id, [raw['id']])
    drinks = {line_id for line_id, names in categories.items() if is_beverage(names)}
    payload = ticket_payload(raw, capture.lines, drinks)
    # A ticket also exists while kitchen dishes wait to be sent, so the minute
    # check can see them go out even if Clover does not mark the order modified.
    if payload['lines'] or (payload['unsent'] and not payload['paid']) \
            or session.get(Ticket, (location_id, raw['id'])) is not None:
        save_ticket(session, location_id=location_id, order=order, payload=payload, synced_at=end)


def check_open_tickets(session, client, merchant_id, location_id, seen, process):
    """Once a minute, ask Clover about each open ticket's order (one GET each):
    - deleted in Clover: the ticket stays, flagged DELETED IN CLOVER, until cleared;
    - a dish sent to the kitchen that the board has not shown yet: read it now,
      in case Clover did not mark the order as modified when it was sent;
    - paid with nothing for the kitchen (a bar order): its hidden ticket is dropped.
    Returns the number of orders that could not be read."""
    cutoff = now() - RECHECK_FOR
    failed = 0
    sources = {t.payload.get('addition_to') or t.payload.get('part_of') or t.order_id
               for t in pending(session, location_id)
               if (t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)) >= cutoff}
    for order_id in sorted(sources - seen):
        result = client.get(f'/v3/merchants/{merchant_id}/orders/{order_id}',
                            params={'expand': 'employee,lineItems'})
        if (not result.ok and result.status_code == 404) or (result.ok and (result.data or {}).get('deleted')):
            mark_deleted(session, location_id, order_id)
            continue
        if not result.ok or not isinstance(result.data, dict) or result.data.get('id') != order_id:
            continue  # unknown answer: try again next minute, change nothing
        raw = result.data
        items = (raw.get('lineItems') or {}).get('elements', [])
        printed = {l['id'] for l in items if l.get('id') and l.get('printed') is True and not l.get('isOrderFee')}
        known = set()
        for t in _family(session, location_id, order_id):
            known.update(t.payload.get('printed_ids') or ())
        if printed - known:
            try:
                with session.begin_nested():
                    process(raw)
            except Exception:
                failed += 1
                LOG.error('Kitchen re-check could not read one Clover order for Location %s', location_id)
        elif is_paid(raw):
            drop_if_empty(session, location_id, order_id)
    return failed


def _tag_lock(session, lock):
    lock.notes = f'{LOCK_TAG} kitchen orders; RUNNING'
    session.commit()


def _clear_crashed_kitchen_lock(session, location_id):
    """A kitchen worker that died mid-cycle leaves its lock RUNNING. Only a lock
    tagged by the kitchen worker and older than any real kitchen cycle is cleared."""
    run = session.scalars(select(m.IngestionRun).where(
        m.IngestionRun.lock_key == a._acquisition_lock_key(location_id),
        m.IngestionRun.status == a.STATUS_RUNNING)).first()
    if run is None or not (run.notes or '').startswith(LOCK_TAG):
        return False
    started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
    if now() - started < KITCHEN_LOCK_STALE:
        return False
    run.status = 'FAILED'
    run.finished_at = now()
    run.lock_key = None
    run.error_summary = 'Kitchen worker interrupted mid-cycle; lock cleared by the next kitchen cycle.'
    session.commit()
    return True


def run_cycle(session, location_id, client=None, check_deleted=True):
    board = session.get(Board, location_id)
    if board is None:
        raise ValueError('Kitchen Board is not initialized for this Location')
    merchant = a._resolve_clover_merchant(session, location_id)
    if merchant is None:
        raise ValueError('Location is not a configured Clover Location')
    source_system_id, merchant_id = merchant
    # Each restaurant has its own Clover connection (Mount Dora is not Winter Park's).
    client = client or a.get_location_client(merchant_id)
    end = now()
    start = a._aware_utc(board.last_sync or board.since) - timedelta(minutes=2)
    lock = None
    for attempt in range(2):
        try:
            # CORRECTION lock mode is deliberately excluded from other consumers' Live
            # Cursor: an order-only run must never claim payment/refund coverage.
            lock = a._acquire_import_lock(session, location_id=location_id,
                source_system_id=source_system_id, period_start=start, period_end=end,
                mode=a.MODE_CORRECTION if hasattr(a, 'MODE_CORRECTION') else 'CORRECTION')
            break
        except a.ImportAlreadyRunningError:
            session.rollback()
            if attempt == 0 and _clear_crashed_kitchen_lock(session, location_id):
                continue
            # Another Clover download holds the lock. Say so on the board if it lasts.
            board = session.get(Board, location_id)
            last = a._aware_utc(board.last_sync) if board.last_sync else None
            if last is None or (now() - last).total_seconds() > 60:
                board.sync_error = 'Another Clover download is running; the board updates when it finishes.'
                session.commit()
            return False
    _tag_lock(session, lock)
    summary = a.ImportSummary(location_id=location_id, period_start=start, period_end=end)
    try:
        if getattr(client, 'merchant_id', None) != merchant_id:
            raise ValueError('Clover credentials do not match this Location')
        account = require_ok(client.get(f'/v3/merchants/{merchant_id}'), 'merchant account')
        if account.get('id') != merchant_id:
            raise ValueError('Clover returned a different merchant')
        result = a.paginate(client, f'/v3/merchants/{merchant_id}/orders', extra_params={
            'filter': [f'modifiedTime>={int(start.timestamp()*1000)}', f'modifiedTime<={int(end.timestamp()*1000)}'],
            'expand': 'employee,lineItems',
        })
        orders = require_complete(result, 'Kitchen orders')
        employees = a._existing_ids_by_source(session, m.Employee,
            source_system_id=source_system_id, source_id_column='source_employee_id')
        since = a._aware_utc(board.since)

        def process(raw):
            _process(session, client, raw, location_id=location_id, source_system_id=source_system_id,
                     employees=employees, lock=lock, end=end)

        seen, failed = set(), 0
        for raw in orders:
            if raw.get('id') and raw.get('createdTime') is not None:
                if datetime.fromtimestamp(raw['createdTime']/1000, timezone.utc) < since:
                    continue
                seen.add(raw['id'])
                if _already_read(session, location_id, raw):
                    continue
            # One unreadable order never blocks every other ticket: it is retried
            # (the cursor does not advance) and the board says something is wrong.
            try:
                with session.begin_nested():
                    process(raw)
                summary.orders_updated += 1
            except Exception:
                failed += 1
                LOG.error('Kitchen sync could not read one Clover order for Location %s; will retry', location_id)
            lock.heartbeat_at = now()
        if check_deleted:
            failed += check_open_tickets(session, client, merchant_id, location_id, seen, process)
        board = session.get(Board, location_id)
        if failed:
            board.sync_error = (f'{failed} Clover order(s) could not be read; retrying automatically. '
                                'Check the paper ticket for recent changes.')
            summary.errors.append(board.sync_error)
        else:
            board.last_sync = end
            board.sync_error = None
        a._finalize_import_run(lock, summary, location_id=location_id, mode='CORRECTION')
        lock.resource_type = 'kitchen_orders'
        session.commit()
        return not failed
    except Exception:
        # Roll back the entire window. Retry from the last complete checkpoint;
        # an empty/failed response must not erase tickets or advance the cursor.
        session.rollback()
        board = session.get(Board, location_id)
        board.sync_error = 'Clover synchronization failed; retrying automatically.'
        lock = session.get(m.IngestionRun, lock.id)
        summary.window_scan_failed = True
        summary.errors.append(board.sync_error)
        a._finalize_import_run(lock, summary, location_id=location_id, mode='CORRECTION')
        lock.resource_type = 'kitchen_orders'
        session.commit()
        raise


def run_forever(session_factory, location_id, interval=15):
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    cycle = 0
    while not stop.is_set():
        try:
            with session_factory() as session:
                # Open-ticket check about once a minute, not every 15 seconds.
                run_cycle(session, location_id, check_deleted=(cycle % 4 == 0))
        except Exception:
            # Do not log credentials, raw responses or exception strings.
            LOG.error('Kitchen order sync failed for Location %s; next cycle will retry', location_id)
        cycle += 1
        stop.wait(interval)
