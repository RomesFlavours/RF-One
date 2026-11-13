# Kitchen AWS release

Explicit PO request, 2026-11-10: publish the completed Kitchen in English,
including visible data. Account-directory integration and assignment of access
rights are deferred to further PO instructions. Existing shared RF-One session
and KITCHEN/RECIPES/CONFIGURATION authorization remain enforced; no new accounts,
grants or automatic administrator access are created by the cloud entrypoint.

Kitchen is an isolated App Runner service built from a Kitchen-only source
snapshot. Other RF-One applications and their source bundles are not replaced.
The shared database is extended only for Kitchen tables; existing canonical
restaurants/suppliers are reused by explicit mapping, with no changes to account
or directory data. The domain content release is restricted to the Kitchen
content explicitly approved for publication, never a local database sync.
Original source evidence, identifiers and numeric facts remain unchanged by
English content translation. Proper restaurant/supplier names and established
culinary proper names are preserved.

Images are stored encrypted in a private S3 bucket and served through authorized
Kitchen/Visual Menu routes. Runtime uploads do not depend on App Runner's
ephemeral filesystem. Health checks are read-only. Database setup/content
publication is an explicit one-time deployment task, never application startup.

Release evidence, immutable source manifests, previous configuration and rollback
references are recorded under `output/kitchen-release`. Rollback changes only
the Kitchen image/routing; it does not downgrade or destroy shared data.

## Complete Kitchen release — 2026-11-12

The candidate includes Menu, one active menu per location, shared Menu Areas,
preparation elapsed time, whole-number presentation, recipes, configuration and
private plating media. It is based on the deployed Kitchen identity integration;
shared access/profile code is preserved verbatim. No local database content is
uploaded, and no accounts, grants, locations or suppliers are created.

AWS's verified head is `t9a120261110`. The explicit Kitchen-only release branch
`k9g120261112` adds the final schema directly, avoiding the unrelated Student
registry and superseded location-specific Menu Areas in the local development
chain. Historical `k9d120261112` now freezes its original pre-activation schema,
so `k9f120261112` adds `active` exactly once on that chain.

`upgrade_release.py --check` applies the actual PostgreSQL migration in a
transaction, checks preserved content and identity hashes, renders all four
pages with an already-authorized account and rolls back. The commit run is
allowed only after that check and an available RDS snapshot. App startup never
migrates. Evidence and the immutable source/image manifest are in
`output/kitchen-release-20261112`. Service rollback uses `previous_image` from
its `release.json`; the additive schema remains, preserving published data.
