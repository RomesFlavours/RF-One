"""CLOVER_ACQUISITION_ENGINE_001 — the shared Clover acquisition engine
(`rfone_data_store.operational_acquisition`).

Proves, in isolation, with two Clover merchants (Winter Park and Mount Dora):
  1. the ordinary download runs at the common time (initial 00:00
     America/New_York) for both sites, each with its own merchant connection,
     once per day, and records each site's outcome and covered period;
  2. changing the time moves the next download; a download already done that
     day is not repeated;
  3. when one site fails the other completes; the failure records no coverage,
     and the next download re-reads the failed site's missing period;
  4. Live stays off without requests; only an authorized account may start it;
     a Live download for one site reads only that site and the requested data,
     and stops by itself;
  5. repeating a download never duplicates data.

Disposable SQLite file built from the models, fake Clover clients only: never
contacts Clover and never touches a real database.

Usage:
    python -m unittest test_operational_acquisition
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store import operational_acquisition as oa
from rfone_data_store.clover_acquisition_validation import FakeCloverClient, _FakeResult
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.technical.connectors.clover import acquisition, shared_cycle

UTC = timezone.utc
WP_MERCHANT, MD_MERCHANT = "WPMERCHANT01", "MDMERCHANT01"
BACKFILL_START = datetime(2026, 6, 1, tzinfo=UTC)
BACKFILL_END = datetime(2026, 6, 8, tzinfo=UTC)
# 2026-06-09 00:00 in America/New_York (EDT, UTC-4) = 04:00 UTC.
MIDNIGHT_ET = datetime(2026, 6, 9, 4, 0, tzinfo=UTC)
T0 = BACKFILL_START + timedelta(days=1, hours=18)


def _utc(value: datetime) -> datetime:
    """SQLite returns naive UTC, PostgreSQL an aware value in the session's zone."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


class _BrokenClover(FakeCloverClient):
    """A merchant whose Clover answers nothing (e.g. revoked token)."""

    def get(self, path, params=None):
        self.calls.append((path, params))
        return _FakeResult(ok=False, error="401 Unauthorized", status_code=401)


def _client(merchant_id: str, prefix: str, cls=FakeCloverClient) -> FakeCloverClient:
    client = cls(merchant_id=merchant_id)
    client.tenders = [{"id": f"TND-{merchant_id}", "label": "Credit Card", "labelKey": "com.clover.tender.credit_card",
                       "enabled": True}]
    client.orders_by_id[f"{prefix}-ORDER"] = {
        "id": f"{prefix}-ORDER", "employee": {"id": f"{prefix}-EMP"}, "createdTime": _ms(T0),
        "modifiedTime": _ms(T0), "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 5000,
        "lineItems": {"elements": []},
    }
    client.payments.append({
        "id": f"{prefix}-PAY", "order": {"id": f"{prefix}-ORDER"}, "employee": {"id": f"{prefix}-EMP"},
        "tender": {"id": f"TND-{merchant_id}", "label": "Credit Card"}, "amount": 5000, "taxAmount": 0,
        "tipAmount": 500, "createdTime": _ms(T0), "modifiedTime": _ms(T0), "result": "SUCCESS",
    })
    return client


class CloverAcquisitionEngineTest(unittest.TestCase):
    def setUp(self):
        # RFONE_ACQ_TEST_PG_URL: run the same proofs on a DISPOSABLE PostgreSQL database (dropped and
        # recreated from the models at every test); never point it at a real database.
        pg_url = os.environ.get("RFONE_ACQ_TEST_PG_URL")
        if pg_url:
            self.path = None
            self.engine = create_configured_engine(pg_url)
            with self.engine.begin() as conn:
                conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
            # Some unrelated models carry SQLite-only server defaults; create every table PostgreSQL
            # accepts (the acquisition tables and their references all are).
            for table in m.Base.metadata.sorted_tables:
                try:
                    table.create(self.engine)
                except Exception:  # noqa: BLE001 — an unrelated table, not used by these proofs
                    pass
            self.factory = create_session_factory(self.engine)
        else:
            fd, self.path = tempfile.mkstemp(suffix=".db", prefix="clover_acquisition_engine_")
            os.close(fd)
            self.engine = create_configured_engine("sqlite:///" + self.path.replace(os.sep, "/"))
            m.Base.metadata.create_all(self.engine)
            self.factory = create_session_factory(self.engine)
        with self.factory() as s:
            source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
            s.add(source)
            s.flush()
            self.wp_id = self._site(s, source, "Rome's Flavours - WP", WP_MERCHANT)
            self.md_id = self._site(s, source, "Rome's Flavours - MD", MD_MERCHANT)
            s.commit()
        self.clients = {self.wp_id: _client(WP_MERCHANT, "WP"), self.md_id: _client(MD_MERCHANT, "MD")}
        with self.factory() as s:
            for location_id in (self.wp_id, self.md_id):
                # The existing starting point of each site: a completed Historical Backfill.
                acquisition.import_clover_period(s, location_id=location_id, period_start=BACKFILL_START,
                                                 period_end=BACKFILL_END, client=self.clients[location_id])
                s.commit()

    def tearDown(self):
        if self.path is None:
            self.engine.dispose()
            return
        self.engine.dispose()
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    @staticmethod
    def _site(s, source, name, merchant_id):
        merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=name, active=True)
        s.add(merchant)
        s.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                              name=name, currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=time(4, 0), active=True)
        restaurant = m.Restaurant(name=name, default_currency="USD")
        s.add_all([location, restaurant])
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        return location.id

    # -- helpers ----------------------------------------------------------------
    def worker(self, location_id, factory=None):
        return oa.LocationWorker(factory or self.factory, location_id, client_factory=lambda lid: self.clients[lid])

    def second_factory(self):
        """A second, independent engine on the same test database (another instance of the service)."""
        url = os.environ.get("RFONE_ACQ_TEST_PG_URL") or "sqlite:///" + self.path.replace(os.sep, "/")
        engine = create_configured_engine(url)
        self.addCleanup(engine.dispose)
        return create_session_factory(engine)

    def tick_all(self, now):
        return {location_id: self.worker(location_id).tick(now) for location_id in (self.wp_id, self.md_id)}

    def requests(self, **where):
        with self.factory() as s:
            stmt = select(m.OperationalAcquisitionRequest).order_by(m.OperationalAcquisitionRequest.id)
            for key, value in where.items():
                stmt = stmt.where(getattr(m.OperationalAcquisitionRequest, key) == value)
            rows = s.scalars(stmt).all()
            s.expunge_all()
            return rows

    def runs(self, location_id, **where):
        with self.factory() as s:
            stmt = select(m.IngestionRun).where(m.IngestionRun.location_id == location_id)
            for key, value in where.items():
                stmt = stmt.where(getattr(m.IngestionRun, key) == value)
            rows = s.scalars(stmt.order_by(m.IngestionRun.id)).all()
            s.expunge_all()
            return rows

    def status(self, location_id):
        with self.factory() as s:
            return oa.describe_site_status(s, location_id)

    def counts(self):
        with self.factory() as s:
            return {
                "orders": s.scalar(select(func.count()).select_from(m.Order)),
                "payments": s.scalar(select(func.count()).select_from(m.Payment)),
                "orders_by_site": dict(s.execute(select(m.Order.location_id, func.count()).group_by(m.Order.location_id)).all()),
            }

    def account(self, *, access=True):
        with self.factory() as s:
            account = m.RFOneAccount(username=f"user{access}", display_name="Rossi M.", password_hash="x", status="ACTIVE")
            s.add(account)
            s.flush()
            if access:
                s.add(m.RFOneAccountDomainAccess(account_id=account.id, domain_code="CLOVER_ACQUISITION", enabled=True))
            s.commit()
            return account.id

    # -- 1. ordinary download: both sites, own merchant, once per day -----------
    def test_ordinary_download_at_common_time_for_both_sites(self):
        with self.factory() as s:
            schedule = oa.get_schedule(s)
        self.assertEqual((schedule.run_time, schedule.timezone), (time(0, 0), "America/New_York"))
        self.assertEqual(schedule.next_run(MIDNIGHT_ET - timedelta(hours=1)), MIDNIGHT_ET)

        outcomes = self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        for location_id, outcome in outcomes.items():
            self.assertEqual(outcome.status, shared_cycle.OUTCOME_COMPLETE, outcome.summary)
        rows = self.requests(kind="SCHEDULED")
        self.assertEqual(sorted((r.location_id, str(r.scheduled_local_date), r.status) for r in rows),
                         sorted([(self.wp_id, "2026-06-09", "COMPLETE"), (self.md_id, "2026-06-09", "COMPLETE")]))
        for location_id, merchant in ((self.wp_id, WP_MERCHANT), (self.md_id, MD_MERCHANT)):
            # Each site was read only with its own merchant.
            self.assertTrue(all(merchant in path for path, _ in self.clients[location_id].calls
                                if path.startswith("/v3/merchants/")))
            row = next(r for r in rows if r.location_id == location_id)
            self.assertEqual(_utc(row.coverage_start), BACKFILL_END)
            self.assertEqual(_utc(row.coverage_end), MIDNIGHT_ET + timedelta(seconds=5))
            sync = self.runs(location_id, acquisition_mode=acquisition.MODE_SYNC_NOW)
            self.assertEqual([r.status for r in sync], ["COMPLETE"])
            self.assertEqual({r.resource_type for r in self.runs(location_id) if r.resource_type},
                             {"orders", "payments", "refunds"})
            status = self.status(location_id)
            self.assertEqual(status.last_attempt.status, "COMPLETE")
            self.assertEqual(status.covered_through, MIDNIGHT_ET + timedelta(seconds=5))
        self.assertEqual(self.counts()["orders_by_site"], {self.wp_id: 1, self.md_id: 1})

        # Same day, until 23:59 ET: no second download. Next day at 00:00 ET: a new one, continuing the coverage.
        self.assertEqual(self.tick_all(MIDNIGHT_ET + timedelta(hours=10)), {self.wp_id: None, self.md_id: None})
        self.assertEqual(self.tick_all(MIDNIGHT_ET + timedelta(days=1, minutes=-1)), {self.wp_id: None, self.md_id: None})
        next_day = MIDNIGHT_ET + timedelta(days=1, seconds=5)
        self.assertTrue(all(o.status == "COMPLETE" for o in self.tick_all(next_day).values()))
        self.assertEqual(len(self.requests(kind="SCHEDULED")), 4)
        status = self.status(self.wp_id)
        self.assertEqual((status.covered_from, status.covered_through), (BACKFILL_END, next_day))

    # -- 2. the user changes the time -------------------------------------------
    def test_change_of_time(self):
        account_id = self.account()
        with self.factory() as s:
            schedule = oa.set_schedule(s, run_time=time(3, 30), account_id=account_id)
            s.commit()
        self.assertEqual((schedule.run_time, schedule.timezone, schedule.updated_by_account_id),
                         (time(3, 30), "America/New_York", account_id))
        # Yesterday's download was never run (first start): it is caught up at once; today's waits for 03:30.
        self.assertTrue(all(o.status == "COMPLETE" for o in self.tick_all(MIDNIGHT_ET + timedelta(minutes=1)).values()))
        self.assertEqual({str(r.scheduled_local_date) for r in self.requests(kind="SCHEDULED")}, {"2026-06-08"})
        self.assertEqual(self.tick_all(MIDNIGHT_ET + timedelta(minutes=2)), {self.wp_id: None, self.md_id: None})
        at_0330 = MIDNIGHT_ET + timedelta(hours=3, minutes=30)
        self.assertTrue(all(o.status == "COMPLETE" for o in self.tick_all(at_0330).values()))
        # Moving the time later the same day does not repeat today's download.
        with self.factory() as s:
            oa.set_schedule(s, run_time=time(20, 0))
            s.commit()
        self.assertEqual(self.tick_all(MIDNIGHT_ET + timedelta(hours=20, minutes=1)), {self.wp_id: None, self.md_id: None})
        self.assertEqual(len(self.requests(kind="SCHEDULED")), 4)  # 2 sites x (yesterday caught up + today)
        with self.factory() as s:
            self.assertRaises(ValueError, oa.set_schedule, s, run_time=time(1, 0), timezone_name="Mars/Base")
            self.assertEqual(oa.get_schedule(s).run_time, time(20, 0))

    # -- 3. one site fails, the other completes ----------------------------------
    def test_one_site_failure_does_not_stop_the_other_and_records_no_coverage(self):
        self.clients[self.md_id] = _client(MD_MERCHANT, "MD", cls=_BrokenClover)
        outcomes = self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        self.assertEqual(outcomes[self.wp_id].status, "COMPLETE", outcomes[self.wp_id].summary)
        self.assertEqual(outcomes[self.md_id].status, "FAILED")
        md_row = self.requests(location_id=self.md_id)[0]
        self.assertEqual(md_row.status, "FAILED")
        self.assertIsNone(md_row.coverage_start)
        self.assertIsNone(md_row.coverage_end)
        self.assertTrue(md_row.outcome)
        md = self.status(self.md_id)
        self.assertEqual(md.last_attempt.status, "FAILED")
        self.assertIsNone(md.last_success)
        self.assertIsNone(md.covered_through)
        self.assertEqual([r.status for r in self.runs(self.md_id, acquisition_mode=acquisition.MODE_SYNC_NOW)], ["FAILED"])
        self.assertEqual(self.status(self.wp_id).last_success.location_id, self.wp_id)

        # Mount Dora's connection works again the next day: its download re-reads the missed period.
        self.clients[self.md_id] = _client(MD_MERCHANT, "MD")
        next_day = MIDNIGHT_ET + timedelta(days=1, seconds=5)
        self.assertTrue(all(o.status == "COMPLETE" for o in self.tick_all(next_day).values()))
        md_ok = self.requests(location_id=self.md_id)[-1]
        self.assertEqual(_utc(md_ok.coverage_start), BACKFILL_END)
        wp_ok = self.requests(location_id=self.wp_id)[-1]
        self.assertEqual(_utc(wp_ok.coverage_start),
                         MIDNIGHT_ET + timedelta(seconds=5) - oa.SCHEDULED_OVERLAP)

    # -- 4. Live: off by default, on request only, limited ---------------------
    def test_live_only_on_authorized_request_for_requested_site_and_data(self):
        # Ordinary download done for today, so the ticks below can only be Live.
        self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        now = MIDNIGHT_ET + timedelta(hours=12)
        before = {lid: len(self.runs(lid)) for lid in (self.wp_id, self.md_id)}
        self.assertEqual(self.tick_all(now), {self.wp_id: None, self.md_id: None})  # off without requests
        self.assertEqual({lid: len(self.runs(lid)) for lid in (self.wp_id, self.md_id)}, before)

        no_access = self.account(access=False)
        allowed = self.account(access=True)
        with self.factory() as s:
            with self.assertRaises(oa.LiveRequestNotAuthorized):
                oa.request_live(s, account=s.get(m.RFOneAccount, no_access), application="TIPS",
                                location_ids=[self.md_id], resources=["payments"], live_until=now + timedelta(hours=1),
                                now=now)
            with self.assertRaises(ValueError):
                oa.request_live(s, account=s.get(m.RFOneAccount, allowed), application="TIPS",
                                location_ids=[self.md_id], resources=["shifts"], live_until=now + timedelta(hours=1),
                                now=now)
            rows = oa.request_live(s, account=s.get(m.RFOneAccount, allowed), application="TIPS",
                                   location_ids=[self.md_id], resources=["payments"],
                                   live_until=now + timedelta(minutes=2), now=now)
            s.commit()
            live_ids = [r.id for r in rows]
        self.assertEqual(len(self.requests(kind="LIVE")), 1)

        md_worker, wp_worker = self.worker(self.md_id), self.worker(self.wp_id)
        self.assertIsNone(wp_worker.tick(now))  # the other site is not touched
        outcome = md_worker.tick(now)
        self.assertEqual(outcome.status, "COMPLETE", outcome.summary)
        new_md = self.runs(self.md_id)[before[self.md_id]:]
        self.assertEqual(sorted(r.resource_type or r.acquisition_mode for r in new_md), ["CORRECTION", "payments"])
        self.assertEqual(len(self.runs(self.wp_id)), before[self.wp_id])
        self.assertIsNone(md_worker.tick(now + timedelta(seconds=10)))  # 30-second rhythm
        self.assertEqual(md_worker.tick(now + timedelta(seconds=31)).status, "COMPLETE")
        # Expired: Live stops by itself.
        self.assertIsNone(md_worker.tick(now + timedelta(minutes=3)))
        self.assertEqual(self.requests(id=live_ids[0])[0].status, "ENDED")
        # A Live download never counts as ordinary coverage.
        self.assertEqual(self.status(self.md_id).covered_through, MIDNIGHT_ET + timedelta(seconds=5))

        # Ended early by the function.
        with self.factory() as s:
            rows = oa.request_live(s, account=s.get(m.RFOneAccount, allowed), application="TIPS",
                                   location_ids=[self.wp_id], resources=["orders", "refunds"],
                                   live_until=now + timedelta(hours=1), now=now + timedelta(minutes=5))
            s.commit()
            oa.end_live(s, request_ids=[r.id for r in rows])
            s.commit()
        self.assertIsNone(wp_worker.tick(now + timedelta(minutes=6)))

    # -- 5. no duplicates on repetition -----------------------------------------
    def test_repeated_download_does_not_duplicate(self):
        self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        first = self.counts()
        self.assertEqual((first["orders"], first["payments"]), (2, 2))
        # Next day the same Clover records are read again (the fake ignores the window): same rows.
        self.tick_all(MIDNIGHT_ET + timedelta(days=1, seconds=5))
        self.assertEqual(self.counts(), first)
        # A download repeated after a restart (RUNNING left behind) also adds nothing.
        with self.factory() as s:
            row = s.scalars(select(m.OperationalAcquisitionRequest).order_by(m.OperationalAcquisitionRequest.id.desc())).first()
            row.status = "RUNNING"
            s.commit()
        worker = self.worker(row.location_id)
        worker.recover_interrupted()
        self.assertEqual(worker.tick(MIDNIGHT_ET + timedelta(days=1, hours=1)).status, "COMPLETE")
        self.assertEqual(self.counts(), first)


    # -- 6. audit fixes (Codex 2026-11-23) ---------------------------------------
    def test_restart_after_a_missed_day_catches_up_before_todays_time(self):
        with self.factory() as s:
            oa.set_schedule(s, run_time=time(9, 0))
            s.commit()
        nine_am = MIDNIGHT_ET + timedelta(hours=9)
        self.tick_all(nine_am)                                    # 2026-06-09 done
        restart = nine_am + timedelta(days=2, hours=-1)           # 2026-06-11 08:00: the 06-10 download was missed
        outcomes = self.tick_all(restart)
        self.assertTrue(all(o.status == "COMPLETE" for o in outcomes.values()))
        self.assertEqual(sorted({str(r.scheduled_local_date) for r in self.requests(kind="SCHEDULED")}),
                         ["2026-06-09", "2026-06-10"])

    def test_a_partial_acquisition_is_never_a_starting_point(self):
        with self.factory() as s:
            # The only acquisitions of Winter Park ended PARTIAL: no COMPLETE starting point.
            for run in s.scalars(select(m.IngestionRun).where(m.IngestionRun.location_id == self.wp_id,
                                                              m.IngestionRun.resource_type.is_(None))):
                run.status = "PARTIAL"
            s.commit()
        outcomes = self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        self.assertEqual(outcomes[self.wp_id].status, "FAILED")
        self.assertIn("no completed download", outcomes[self.wp_id].summary)
        self.assertEqual(outcomes[self.md_id].status, "COMPLETE")
        self.assertIsNone(self.status(self.wp_id).covered_through)

    def test_a_running_download_cannot_be_claimed_twice(self):
        now = MIDNIGHT_ET + timedelta(seconds=5)
        # Two instances, each with its own database connection pool on the same test database.
        first, second = self.worker(self.wp_id), self.worker(self.wp_id, factory=self.second_factory())
        with second.session_factory() as s:  # both record the day: still one request per site and date
            second._ensure_scheduled(s, now)
        with self.factory() as s:
            first._ensure_scheduled(s, now)
            claimed = first._claim_scheduled(s, now)
        self.assertIsNotNone(claimed)
        # A second instance starting now neither recovers nor claims it while the lease holds.
        second.recover_interrupted(now)
        with self.factory() as s:
            self.assertIsNone(second._claim_scheduled(s, now + timedelta(minutes=5)))
        self.assertEqual(self.requests(id=claimed.id)[0].status, "RUNNING")
        # Lease expired (first instance gone): the second takes over and records the outcome...
        later = now + oa.LEASE_DURATION + timedelta(seconds=1)
        with self.factory() as s:
            taken = second._claim_scheduled(s, later)
            self.assertEqual(taken.id, claimed.id)
            outcome = second._run_scheduled(s, taken, later)
        self.assertEqual(outcome.status, "COMPLETE")
        row = self.requests(id=claimed.id)[0]
        self.assertEqual((row.status, row.claimed_by, row.attempts), ("COMPLETE", None, 2))
        # ...and the first instance, coming back late, cannot overwrite it.
        with self.factory() as s:
            first._run_scheduled(s, s.get(m.OperationalAcquisitionRequest, claimed.id), later)
        self.assertEqual(self.requests(id=claimed.id)[0].coverage_end, row.coverage_end)
        self.assertEqual(len(self.requests(location_id=self.wp_id, kind="SCHEDULED")), 1)

    def test_nightly_download_gate_requires_every_active_site(self):
        self.clients[self.md_id] = _client(MD_MERCHANT, "MD", cls=_BrokenClover)
        self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        with self.factory() as s:
            gate = oa.describe_nightly_download(s, now=MIDNIGHT_ET + timedelta(hours=9))
        self.assertFalse(gate.ready)
        self.assertIn("MD", gate.reason)
        # An inactive site is not required.
        with self.factory() as s:
            s.get(m.Location, self.md_id).active = False
            s.commit()
            self.assertTrue(oa.describe_nightly_download(s, now=MIDNIGHT_ET + timedelta(hours=9)).ready)
            # The next night's download is due and not done yet: not ready.
            self.assertFalse(oa.describe_nightly_download(s, now=MIDNIGHT_ET + timedelta(days=1, minutes=1)).ready)

    # -- 7. independent audit blockers (2026-11-23) -------------------------------
    def test_first_ordinary_download_after_backfill_ignores_a_later_partial_sync_now(self):
        with self.factory() as s:
            # After the COMPLETE Historical Backfill, a Sync Now over a later window ended PARTIAL.
            s.add(m.IngestionRun(source_system_id=s.scalar(select(m.SourceSystem.id)), location_id=self.wp_id,
                                 started_at=BACKFILL_END + timedelta(hours=1), status="PARTIAL",
                                 source_window_start=BACKFILL_END, source_window_end=BACKFILL_END + timedelta(hours=20),
                                 acquisition_mode=acquisition.MODE_SYNC_NOW))
            s.commit()
        outcome = self.worker(self.wp_id).tick(MIDNIGHT_ET + timedelta(seconds=5))
        self.assertEqual(outcome.status, "COMPLETE", outcome.summary)
        row = self.requests(location_id=self.wp_id)[0]
        self.assertEqual(_utc(row.coverage_start), BACKFILL_END)  # from the Backfill, not the PARTIAL window

    def test_partial_or_busy_ordinary_download_advances_neither_coverage_nor_start(self):
        from unittest import mock
        original = shared_cycle.import_clover_period

        def ends_partial(session, **kwargs):
            original(session, **kwargs)
            kwargs["ingestion_run"].status = "PARTIAL"

        first = MIDNIGHT_ET + timedelta(seconds=5)
        with mock.patch.object(shared_cycle, "import_clover_period", ends_partial):
            outcome = self.worker(self.wp_id).tick(first)
        self.assertEqual(outcome.status, "FAILED")
        row = self.requests(location_id=self.wp_id)[0]
        self.assertEqual((row.status, row.coverage_start, row.coverage_end), ("FAILED", None, None))
        self.assertIsNone(self.status(self.wp_id).covered_through)

        # Next day the site is busy (another acquisition holds its lock): nothing recorded, retried later.
        next_day = MIDNIGHT_ET + timedelta(days=1, seconds=5)
        with self.factory() as s:
            lock = acquisition._acquire_import_lock(
                s, location_id=self.wp_id, source_system_id=s.scalar(select(m.SourceSystem.id)),
                period_start=BACKFILL_END, period_end=next_day, mode=acquisition.MODE_SYNC_NOW)
            lock_id = lock.id
        outcome = self.worker(self.wp_id).tick(next_day)
        self.assertEqual(outcome.status, shared_cycle.OUTCOME_BUSY)
        busy = self.requests(location_id=self.wp_id)[-1]
        self.assertEqual((busy.status, busy.coverage_end), ("PENDING", None))
        self.assertIsNone(self.status(self.wp_id).covered_through)
        with self.factory() as s:
            run = s.get(m.IngestionRun, lock_id)
            run.status, run.lock_key = "FAILED", None
            s.commit()

        # Once free, the download starts again from the last COMPLETE point (the Backfill).
        outcome = self.worker(self.wp_id).tick(next_day + timedelta(minutes=1))
        self.assertEqual(outcome.status, "COMPLETE", outcome.summary)
        done = self.requests(location_id=self.wp_id)[-1]
        self.assertEqual(_utc(done.coverage_start), BACKFILL_END)

    def test_a_download_failed_on_updates_never_moves_the_start(self):
        from unittest import mock
        first = MIDNIGHT_ET + timedelta(seconds=5)
        # New records imported COMPLETE, then the updates step fails: the download is FAILED.
        with mock.patch.object(shared_cycle, "run_correction_cycle", side_effect=RuntimeError("updates down")):
            outcome = self.worker(self.wp_id).tick(first)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual([r.status for r in self.runs(self.wp_id, acquisition_mode=acquisition.MODE_SYNC_NOW)],
                         ["COMPLETE"])
        # The next download restarts from the Backfill, not from the end of that import.
        outcome = self.worker(self.wp_id).tick(MIDNIGHT_ET + timedelta(days=1, seconds=5))
        self.assertEqual(outcome.status, "COMPLETE", outcome.summary)
        self.assertEqual(_utc(self.requests(location_id=self.wp_id)[-1].coverage_start), BACKFILL_END)

    def _restaurant_of(self, location_id):
        with self.factory() as s:
            return s.scalar(select(m.RestaurantLocation.restaurant_id).where(
                m.RestaurantLocation.location_id == location_id))

    def test_tips_wait_for_every_active_site_also_of_another_restaurant(self):
        from rfone_data_store.tips import payment_readiness, readiness
        wp_restaurant = self._restaurant_of(self.wp_id)
        self.assertNotEqual(wp_restaurant, self._restaurant_of(self.md_id))  # distinct restaurants
        self.clients[self.md_id] = _client(MD_MERCHANT, "MD", cls=_BrokenClover)
        outcomes = self.tick_all(MIDNIGHT_ET + timedelta(seconds=5))
        self.assertEqual((outcomes[self.wp_id].status, outcomes[self.md_id].status), ("COMPLETE", "FAILED"))
        nine_am = MIDNIGHT_ET + timedelta(hours=9)
        with self.factory() as s:
            calc = readiness.describe_readiness(s, wp_restaurant, now=nine_am)
            pay = payment_readiness.describe_payment_readiness(s, wp_restaurant, now=nine_am)
        self.assertFalse(calc.ready_to_calculate)
        self.assertIn("MD", calc.reconciliation_reason)
        self.assertFalse(pay.ready)
        self.assertIn("MD", pay.reconciliation_reason)
        # Mount Dora inactive: it no longer blocks Tips; the nightly download done = ready at 09:00.
        with self.factory() as s:
            s.get(m.Location, self.md_id).active = False
            s.commit()
        with self.factory() as s:
            calc = readiness.describe_readiness(s, wp_restaurant, now=nine_am)
            pay = payment_readiness.describe_payment_readiness(s, wp_restaurant, now=nine_am)
        self.assertTrue(calc.ready_to_calculate, calc.reconciliation_reason)
        self.assertTrue(pay.ready, pay.reason)

if __name__ == "__main__":
    unittest.main()
