# Bank rule application contract

Approved by the Product Owner on 2026-10-19.

Two explicit application modes replace overlapping execution switches: FILL_MISSING preserves every populated WHO, WHY and For Whom; UPDATE_ASSIGNED replaces only the fields assigned by the selected rule, including manual and previous-rule values. Financial source data never changes. Split allocations and own-account WHO remain protected. Other active rules are disclosed as overlaps rather than silently blocking this explicitly selected application. Future imports keep their existing conflict protections.

A completed preview is mandatory and bound to the rule version, scope, mode and a fingerprint of current movement/decision/allocation/catalog state. Changes invalidate it. Apply is single use.

Every changed movement records complete before/after state. Rollback is transactionally serialized, append-only for decision history, idempotent per item, and restores only rows whose current state still equals the application after-state. Any later movement, decision or allocation edit causes a reported skip. Historical applications without snapshots cannot be rolled back. Created catalog entries remain available; source transactions are never deleted.
