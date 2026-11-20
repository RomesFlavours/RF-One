# Local MyRFOne alignment

The local Home follows the verified AWS navigation: company context, authorized
modules (including Organization, Projects and Selection Old), Administration with
Registry, Settings and Development Journal under Services. The official local
launcher selects Italian and signs in as the existing active `rfone` operator on
loopback, keeping the account's real grants. It must not create accounts, grant
access, run migrations, refresh data or connect local navigation to production.

Restore only the missing published navigation dependencies from the verified
Registry layout source (image base `sha256:70f8e543d2c3468f6c497d45139ac9153bb576877ee4d0e4be2f5b663e233871`).
Keep local Kitchen, Training and Bank implementations. Reuse the existing
canonical PostgreSQL connection and session key. Company switching changes only
the browser session and resolves permissions again on each request.

Acceptance: Home and its contextual modal are Italian, the expected authorized
entries and company selector are present, anonymous local visits sign in
automatically, company changes require CSRF and reject inaccessible companies,
and no database content/schema or AWS resources change during verification.
Home help must describe the available navigation and any real local limitation.
