# Migration data — immutable, one snapshot per Alembic revision

Files here are **inputs to a specific Alembic revision, frozen at the moment
that revision was written**. They are named `<revision>_<what>.csv` and are
read only by the revision whose id they carry.

## The rule

**Once a file here is committed, it is never edited, never re-sorted and never
"kept in sync" with anything.** Correcting it would change what a historical
migration does, which is the one thing a migration must never do: a database
built from `base` years from now has to reach exactly the state the revision
chain describes, not the state today's canonical definition happens to
describe.

A wrong value in one of these files is corrected by a NEW revision that
migrates forward from it, exactly as a wrong value in already-shipped data is.

## Why these exist

`b8d3f1a72c64`, `c5f8b2e91a47` and `d7a4c9e2f318` originally read the live
canonical catalog:

    rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv

That file is the CURRENT canonical definition and is actively maintained — it
has already grown from 134 accounts to 136, and it will change again. Reading
it at migration time meant `b8d3f1a72c64` would have seeded 136 accounts on a
database created today and 134 on one created in September 2026, so the same
revision chain produced different histories. Each revision now carries its own
frozen copy instead.

## The two concerns, kept apart

| | Alembic history | Current canonical definition |
|---|---|---|
| lives in | `migrations/migration_data/` | `rfone_data_store/bank_reconciliation/canonical/` |
| answers | what the catalog WAS at revision X | what the catalog IS now |
| changes | never | whenever the Product Owner approves a change |
| read by | one revision each | `canonical_catalog.seed` / `validate` / the app |

The canonical CSV stays the source of truth for bootstrap, validation and every
future change. It is simply not what decides what a 2026 migration does.

## The files

| file | revision | content |
|---|---|---|
| `b8d3f1a72c64_rfone_restaurant_coa_v1.csv` | `b8d3f1a72c64` | the 134-account catalog as approved at commit `a6fa020`, with that revision's original `Node Type` vocabulary (`CONTRA_ASSET`, `CONTRA_REVENUE`, `POSTING_REVIEW_SENSITIVE`) |
| `c5f8b2e91a47_account_semantics.csv` | `c5f8b2e91a47` | the same 134 accounts with the four semantic columns as approved at commit `c3124cd` |

`d7a4c9e2f318` needs four rows only, so it carries them inline in the revision
file rather than adding a third snapshot.
