# TASK 5D-MICRO-FIX — Session-Level Interview Scheduling Windows — Report

**Status:** Complete
**Scope:** Selection Domain runtime (`03 Software/Selection/`, `03 Software/RF-One Data Store/rfone_data_store/selection/`) — no file outside Selection was touched. No broader refactor: only `InterviewSchedulingWindow`/`InterviewAppointment` and the scheduling service/routes/templates that touch them were changed; Communication Templates, triggers, reminders, inbound classification, and every other Task 5D concept are unchanged.

---

## 1. Change made

`InterviewSchedulingWindow` was Application-scoped (`application_id` required) — a restaurant had to recreate an identical window for every candidate. It is now **primarily Selection-Session-scoped**: `application_id` was widened to nullable, and a window normally carries `session_id` instead, shared by every eligible Application linked to that Session. A genuinely exceptional Application-specific window remains fully supported as an explicit override (`application_id` set) — a new DB check constraint (`ck_scheduling_window_session_or_application`) requires at least one of the two, never neither. `InterviewAppointment` is unchanged in scope (still Application-specific) but now books against the shared pool correctly, and gained a `slot_ordinal` column backed by a new partial unique index that gives the shared-capacity guard real database-level teeth (see §3).

---

## 2. Revised scheduling model

- **`InterviewSchedulingWindow`**: `session_id` (nullable FK to `selection_sessions`, the normal path) and `application_id` (nullable FK to `applications`, the override path) — exactly one is required, enforced by `ck_scheduling_window_session_or_application`.
- **`scheduling_service.create_scheduling_window`** now takes `session_id=` or `application_id=` as keyword arguments (no more positional `application_id`); a new `list_windows_for_session()` is the primary listing, `list_windows_for_application()` now returns only that Application's own override windows.
- **`scheduling_service.list_applicable_windows_for_application()`** (new) — the one function that resolves what a specific Application/candidate is actually allowed to see: its Selection Session's shared windows (if it belongs to one) **plus** its own override windows. `list_available_slots()` and the candidate-facing page both read through this.
- **`scheduling_service._window_applies_to_application()`** (new) — the one place that decides whether a booking attempt against a given window is legitimate for a given Application (exact match for an override window; same-Session match for a shared window).

---

## 3. Shared capacity behavior

Capacity was already keyed by `scheduling_window_id` + slot start time (never per-Application) — the missing piece was simply that every Application previously had its *own* window row, so no capacity was ever actually shared. With windows now genuinely shared, the existing capacity logic works as intended: booking by Application A immediately removes that slot from Application B's view of the same window (verified — checks B/C/D), and `capacity_per_slot > 1` lets multiple different Applications book the same slot until it is exhausted (check E).

**Concurrency hardening (task §9):** `InterviewAppointment` gained `slot_ordinal` (0-indexed, `< capacity_per_slot`) plus a **partial unique index** `ux_interview_appointment_slot_ordinal_confirmed` on `(scheduling_window_id, slot_start_at, slot_ordinal)`, scoped to `status = 'CONFIRMED'` rows only (mirrors the exact `sqlite_where`/`postgresql_where` pattern `RestaurantLocation`'s own primary-location constraint already uses in this codebase). `book_slot` still picks the first free ordinal in Python, but the `session.flush()` that inserts the new row is now wrapped in a `try/except IntegrityError` — if two requests raced past the same "free ordinal" check, the database itself accepts only one INSERT and the loser gets a clean `ValueError` ("This slot is no longer available"), never a silently-doubled booking. This was verified directly (bypassing the service layer's own Python check entirely) with two raw `InterviewAppointment` inserts sharing the same `(window, slot_start_at, ordinal=0)`: the first succeeds, the second raises `sqlite3.IntegrityError: UNIQUE constraint failed`; marking the first row `RESCHEDULED` immediately frees ordinal 0 for reuse, since the partial index only ever covers `CONFIRMED` rows. This is the minimum clean DB-level guard for the existing check-then-insert architecture — not a broader concurrency-control redesign (task's own "do not over-engineer").

---

## 4. UI changes

- **Selection Session page (`session_detail.html`)** — new "Interview Scheduling Windows" section: lists every window offered under the Session (stage, date, time, slot length, capacity, active/inactive) and a form to offer a new one (`POST /sessions/<id>/scheduling-windows/new`, wired to `session_scheduling_window_create` in `app.py`). This is now the primary place a Selezionatore manages scheduling windows.
- **Candidate Dossier (`dossier.html`)** — the existing per-Application window form is relabeled "Application-specific scheduling override (exceptional...)" with an explanatory note pointing to the Session page, plus a new link ("Manage shared Interview Scheduling Windows on this Application's Selection Session") when the Application belongs to one. The Dossier's communication/appointment display itself (current appointment, reschedule status, scheduling link state) is unchanged.
- No change to the candidate-facing `/schedule/<token>` page itself — it already read through `scheduling_service.list_available_slots`, which now transparently returns the shared Session pool.

---

## 5. Tests / results

**A. Permanent regression suite** (`selection_validation.py::_assert_5d_micro_fix_session_scheduling`, 14 checks covering the task's own A-M letter items — "N: full regression suite passing" is the outcome of the run itself, not a separate check), registered in `run_validation()`. Fresh SQLite DB, migrations applied through revision `e8b2d5f1a9c3`. **Full suite result: 522/522 checks passed** (508 pre-existing including Task 5D's own 43 + 14 new) — confirming M (existing Task 5D communication/override behavior unchanged) and N (no regression anywhere else).

**B. Direct database-level concurrency probe** (one-off script, not committed) — bypassed `book_slot` entirely and inserted two raw `InterviewAppointment` rows sharing `(window, slot_start_at, ordinal=0, CONFIRMED)`: the database itself rejected the second (`IntegrityError`), and freed the ordinal the moment the first row's status changed away from `CONFIRMED`. **2/2 passed.**

**C. Flask HTTP-level smoke test** (throwaway DB, real `test_client()`, one-off): created a Selection Session, uploaded and linked two Applications to it, created a scheduling window through the real `/sessions/<id>/scheduling-windows/new` route, confirmed the Session page displays it, confirmed both Applications see the identical slot pool via the service layer, booked the slot for Application A through the real `/schedule/<token>/book` page, confirmed Application B's pool no longer offers that slot, and confirmed the Dossier page still renders. **10/10 passed.**

**D. Full-navigation regression smoke** (unchanged from Task 5D, re-run): all 17 existing + new nav pages still render 200. **17/17 passed.**

---

## 6. Remaining relevant limitations

- The DB-level guard (partial unique index) protects the CONFIRMED-row invariant exactly; it does not add row-level locking around the "compute free ordinal" read itself — under genuine concurrency the loser of a race gets a clean, correct rejection (proven in test B) rather than a silent double-booking, which is what task §9 asked for ("minimum clean database-level protection... do not over-engineer"), not a guarantee that the *first* requester always wins a photo-finish (an inherently harder problem this task did not ask to solve).
- A window may in principle carry both `session_id` and `application_id` set at once (an override explicitly scoped inside one Session, for extra bookkeeping clarity); `_window_applies_to_application` treats `application_id` as authoritative whenever it is present, so this remains unambiguous, but the create-window UI forms only ever populate one or the other.
- Existing Task 5D Application-scoped windows created before this fix continue to work unchanged (still valid override rows with `application_id` set) — no data migration/backfill was needed or performed.
