# Registry Clover identity confirmation

Overlay on the currently running RF-One Web image pinned by SHA-256 digest.
Only Registry confirmation, its contextual help and the Tips finalization blocker
are changed. Published role-level and compensation updates remain inherited.
No migration, data import, automatic local login or grant update is included.

Validation: four isolated HTTP/attribution tests, shared Registry grant/revoke and
company isolation tests, unchanged standard How Works checker on the exact overlay.
Build repeats the HTTP/attribution and policy tests inside the resulting image.

Recovery: restore the previous ImageIdentifier recorded in the private release
state. Keep runtime settings and secrets unchanged. No data rollback is needed
because this release performs no migration or identity confirmation itself.
