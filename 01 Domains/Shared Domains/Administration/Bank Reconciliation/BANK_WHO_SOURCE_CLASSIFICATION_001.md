# WHO + Source classification — 2026-10-26

Approved by the Product Owner: one canonical WHO identity, and one classification row per exact WHO +
financial Source (account/card). The database enforces uniqueness of occurrence_id/payment_instrument_id.
Each pair has zero or one WHY. WHAT is read from that WHY; WHOM is the Source owner at the movement date.
A missing pair/WHY stays open. Never fall back to a WHO-only default, another Source, a historical
association or a WHO-only Recognition Profile. Matched transfers/card payments retain their dedicated
path. Confirmed human WHO/WHY decisions stay stored and protected; display WHAT/WHOM are derived.

Configuration lists WHO, Source, WHOM, WHY and WHAT. WHO catalog management is separate and never creates
a duplicate identity for another Source. Exact-pair edits change the engine signature; the explicit
Recalculate WHY / WHAT action refreshes proposals. New recognized WHO/Source combinations are added as
unclassified pairs automatically; no old global WHY is copied to them. A merge refuses two different
WHYs for the same Source, and combines nonconflicting pairs without duplication.

WHO activity labels are removed: catalog/link tables, profile activity/label columns, editing controls,
search, recognition worker, automatic creation, hints, AI inputs and cached result fields. Historical
migration files and offline backups remain as recovery/audit history. Migration f4b120261026 preserves
CSV imports, movements, operational explanations/allocations and WHO catalog identities. The migration
is destructive for labels; recovery of removed label data requires the pre-migration backup.

Existing WHO-global defaults remain historical configuration only and are not projected to Sources.
The previously requested full decision reset is still paused; this change does not perform that reset.
