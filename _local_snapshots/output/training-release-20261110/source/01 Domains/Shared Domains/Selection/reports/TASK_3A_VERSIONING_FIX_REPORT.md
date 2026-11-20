# TASK 3A-FIX — Requirement Versioning + Immutable Snapshot Support: Implementation Report

## 1. What I implemented

An immutable, point-in-time snapshot mechanism for Requirement Sets, layered on top of Task 3A's existing live/editable model without changing it. Live `RequirementSet`/`Requirement` rows remain fully editable exactly as before; a new `create_requirement_set_snapshot()` operation captures the current state (set metadata + every Requirement, active or not) by value into two new immutable tables, keyed by `(requirement_set_id, version)` so a snapshot is always addressable as "this set, as of version N" and re-requesting one for an unchanged version returns the existing row rather than duplicating it.

## 2. Main files changed

- Extended: `rfone_data_store/models.py` (+2 tables: `RequirementSetSnapshot`, `RequirementSnapshotItem`; updated `RequirementSet`'s docstring to describe the new relationship between `version` and a snapshot)
- Extended: `rfone_data_store/selection/requirements_service.py` (+7 functions: create/get/get-by-version/get-latest/list/serialize)
- New: migration `c2b6e8a4f1d7_add_requirement_set_snapshot.py`
- Extended: `03 Software/Selection/app.py` (+2 routes), `templates/requirement_set_detail.html` (+Snapshots card), new `templates/requirement_set_snapshot_detail.html` (read-only view)
- Extended: `rfone_data_store/selection_validation.py` (+16 checks, `_assert_requirement_set_snapshot`)

## 3. Snapshot persistence model

`RequirementSetSnapshot`: `requirement_set_id`, `version` (unique together), copies of `restaurant_id`, `source_template_id`, `name`, `description`, `location_label`, `target_role`, `was_active`, plus its own immutable `created_at`. `RequirementSnapshotItem`: one row per Requirement captured, copying `name`, `description`, `category`, `criticality`, `trainability`, `assessment_stages`, all four evidence/guidance fields, `display_order`, and `was_active`. `source_requirement_id` on the item is deliberately a plain integer, **not** a foreign key — a snapshot must stay entirely valid even if the live Requirement it was copied from is later changed or removed.

## 4. Requirement Set version semantics

Unchanged from Task 3A: `version` starts at 1 and is incremented exactly once per structural edit — creating a Requirement Set, adding a Requirement, updating a Requirement Set or a Requirement (only when fields are actually passed), and deactivating/reactivating a Requirement (which routes through `update_requirement`). Read operations (`get_requirement_set`, `list_requirement_sets`, `get_snapshot`, `list_snapshots`, etc.) never touch it — verified explicitly (checks 3A-FIX-I/J). This was already correct in Task 3A; this fix's contribution is anchoring a *version* to an *immutable snapshot* so it now means something durable, not just a counter.

## 5. Snapshot creation/retrieval behavior

`create_requirement_set_snapshot(session, requirement_set_id)` reads the live set and its Requirements, and either returns the existing snapshot for the current version (if one was already captured) or creates a new one. Retrieval: `get_snapshot(snapshot_id)`, `get_snapshot_by_version(requirement_set_id, version)`, `get_latest_snapshot(requirement_set_id)`, `list_snapshots(requirement_set_id)`. `serialize_requirement_set_snapshot(snapshot)` returns a deterministic plain dict (fixed field order, requirements explicitly sorted by `display_order` rather than relying on relationship-load order) suitable for auditing, testing, or a future Fit Assessment to persist alongside its own record.

## 6. Immutability guarantees

No update or delete operation exists anywhere in `requirements_service.py` for `RequirementSetSnapshot`/`RequirementSnapshotItem` — only create and read. Verified directly: editing the live set's metadata, editing a live Requirement, adding a new Requirement, and deactivating a Requirement after a snapshot was taken all leave that snapshot's content completely unchanged (checks 3A-FIX-E through H).

## 7. UI changes

On the Requirement Set detail page: current version is already shown; a new "Snapshots" card lists every snapshot (version, requirement count, creation date) with a "Create snapshot of current state" button and a link to a read-only detail view per snapshot. The new `requirement_set_snapshot_detail.html` page displays the captured set and its requirements with no edit forms at all — intentionally, since snapshot content must never be editable.

## 8. Targeted tests performed and results

- `python test_selection_engine.py` (`selection_validation.py`, incl. new `_assert_requirement_set_snapshot`): **76/76 checks passed** (61 pre-existing Task 2A/2B/3A checks + 15 new checks 3A-FIX-A through 3A-FIX-O, covering snapshot creation, metadata/requirement/order fidelity, immutability against every kind of live edit, version-increment consistency, read-operations-don't-bump-version, retrieval by version, deterministic serialization, template non-interference, template cloning, and existing Requirement CRUD).
- `python test_batch_upload.py`: **19/19 checks passed** — confirms the résumé/candidate pipeline is unaffected.
- Manual end-to-end smoke test through the real Flask app (`test_client`): created a set, added a requirement, created a snapshot, confirmed re-clicking "create snapshot" without an edit reuses the same row, edited the live set/requirement and added another requirement, confirmed the snapshot was untouched, viewed the snapshot's read-only page.
- Full Alembic migration chain verified to apply cleanly through the new head revision on a fresh database.

## 9. Known limitations directly relevant to versioning

- Snapshot creation is explicit, not automatic — nothing currently calls `create_requirement_set_snapshot()` on every version bump; a future Fit Assessment (or a user action) is expected to call it when a snapshot is actually needed, to avoid accumulating a snapshot row for every minor edit.
- `serialize_requirement_set_snapshot()` returns a Python dict, not a stored JSON blob — nothing currently persists the serialized form; it is provided as a ready-to-use deterministic representation for whatever later stage needs to store or compare it.
- Templates and `RequirementTemplateItem` rows are unaffected by this fix and remain unversioned/unsnapshotted, per the task's explicit instruction that this applies to restaurant Requirement Sets, not the template architecture.
