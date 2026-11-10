# Registry authorization service release

These overlays align the effective Registry policy in RF1 Web and the current
published Tips, Selection, Training and Kitchen services. Each patch applies to
the exact source ZIP recorded in manifest.json, not to a guessed repository head.
Every original and resulting file is SHA-256 checked. Service-owned business code,
Selection workspace/bridge and Training courses/first-access behavior are retained.
The source trees include the already-applied shared chain through t9a120261110;
this release does not migrate the production database.

Reproduce each context with Python (no AWS access or migrations):

    python apply_overlay.py web downloaded-web-baseline.zip output-web

Use tips, selection, training or kitchen with its corresponding baseline archive.
Before building Selection, stamp RELEASE_COMMIT with the release commit; keep the
project's existing workspace and candidate-bridge build guard unchanged. All image
tags must be new and immutable. Update each App Runner service only if its image
still matches manifest.previous_image. Preserve runtime configuration/secrets,
record operation IDs and image digests, and retain previous images for rollback.

Tests use disposable SQLite databases and the actual published business sources.
They cover role grant/revoke, existing sessions, company separation and Training
trainer downgrade; Selection also checks that the current workspace remains.
Public candidate pages and the public dish guide remain public by design.

The private local launcher and Switch user are deliberately excluded. No local
cookie, signing key, database dump, local-only authentication or simulated-user
selection belongs in a production image. This release never generates production
login cookies or changes the production login/session mechanism.

Current shared schema definitions recovered into the repository include the
already-deployed additive Training course/profile tables. This is source-history
alignment, not a new migration execution. The original unpublished lifecycle work
in the parent employee-directory worktree remains separate.
