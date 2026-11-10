"""Order-only specialization of the existing Clover Live Sync acquisition path."""
import logging
import signal
import threading
from datetime import timedelta, timezone

import bootstrap  # noqa: F401
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.technical.connectors.clover import acquisition as a
from rfone_data_store.technical.connectors.clover.historical_backfill_detail import ingest_order_item_and_modifier_detail
from rfone_data_store.technical.connectors.clover.source_guard import require_complete, require_ok
from store import Board, now, save_ticket

LOG = logging.getLogger('kitchen_live_sync')


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


def ticket_payload(order_raw, lines):
    """Provider values stay verbatim; never infer seats, quantities or covers."""
    return {
        'title': order_raw.get('title') or order_raw['id'],
        'note': order_raw.get('note'),
        # The employee Clover already returns with the order (expand=employee).
        'server': ((order_raw.get('employee') or {}).get('name') or None),
        'lines': [{
            'id': line.get('id'), 'name': line.get('name') or '',
            'quantity': (line['unitQty'] / 1000 if line.get('unitQty') is not None else None),
            'guest': line.get('binName') or '', 'note': line.get('note'),
            'modifiers': [mod.get('name') or '' for mod in (line.get('modifications') or {}).get('elements', [])],
        } for line in lines if not line.get('isOrderFee')],
    }


def run_cycle(session, location_id, client=None):
    board = session.get(Board, location_id)
    if board is None:
        raise ValueError('Kitchen Board is not initialized for this Location')
    merchant = a._resolve_clover_merchant(session, location_id)
    if merchant is None:
        raise ValueError('Location is not a configured Clover Location')
    source_system_id, merchant_id = merchant
    client = client or a.get_default_client()
    end = now()
    start = a._aware_utc(board.last_sync or board.since) - timedelta(minutes=2)
    try:
        # CORRECTION lock mode is deliberately excluded from other consumers' Live
        # Cursor: an order-only run must never claim payment/refund coverage.
        lock = a._acquire_import_lock(session, location_id=location_id,
            source_system_id=source_system_id, period_start=start, period_end=end,
            mode=a.MODE_CORRECTION if hasattr(a, 'MODE_CORRECTION') else 'CORRECTION')
    except a.ImportAlreadyRunningError:
        return False
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
        for raw in orders:
            # Unknown creation timestamps are errors, never silently omitted tickets.
            if not raw.get('id') or raw.get('createdTime') is None:
                raise ValueError('Clover order is missing its identifier or creation time')
            from datetime import datetime
            created = datetime.fromtimestamp(raw['createdTime']/1000, timezone.utc)
            if created < since:
                continue
            order, _ = a._ingest_order(session, raw, location_id=location_id,
                source_system_id=source_system_id, employee_by_source_id=employees,
                ingestion_run_id=lock.id, retrieved_at=end)
            capture = DetailCapture(client)
            ingest_order_item_and_modifier_detail(session, capture, raw, order,
                source_system_id=source_system_id, ingestion_run_id=lock.id,
                retrieved_at=end, mirror_source_record=a._mirror_source_record)
            save_ticket(session, location_id=location_id, order=order,
                        payload=ticket_payload(raw, capture.lines), synced_at=end)
            summary.orders_updated += 1
            lock.heartbeat_at = now()
        board.last_sync = end
        board.sync_error = None
        a._finalize_import_run(lock, summary, location_id=location_id, mode='CORRECTION')
        lock.resource_type = 'kitchen_orders'
        session.commit()
        return True
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
    while not stop.is_set():
        try:
            with session_factory() as session:
                run_cycle(session, location_id)
        except Exception:
            # Do not log credentials, raw responses or exception strings.
            LOG.error('Kitchen order sync failed for Location %s; next cycle will retry', location_id)
        stop.wait(interval)
