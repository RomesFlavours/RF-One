# Registry local acceptance runtime

Install `launch_local.py` beside the existing private `verification.json` and
`local-session.key`, outside the immutable AWS source/dump. The state file supplies
`local_database`, `development_source` (the reviewed `03 Software` directory) and
`web_port`. Never commit the private state, database dump or signing key.

The launcher verifies the dedicated loopback PostgreSQL target and strips cloud
configuration, blocks outbound sockets and AWS clients, disables Clover job
launching, then serves the actual RF1 shell, standalone Tips, Selection and Kitchen
on one loopback port. It does not change user grants or disable the application
policy. Schema migrations are explicit, not run on import.

A local-only User selector changes the existing account session without a login.
It defaults to owner once, then preserves the explicit signed selection across
authorization denial/logout. Inactive users and revoked session versions never
fall back to owner. Company switching uses Registry's validated shared context.
The selector and local authentication shortcut live only in this wrapper, never
in the production applications. HTML is no-store. No environment banner is added.

Operational Training requests through Tips require the shared Training grant and
explicit identity, then use the canonical RF1 Training entry. The public dish guide
is unchanged. Internet-dependent functionality remains disabled in this runtime.

Run `python launch_local.py --check` for the local page smoke check. Normal startup
serves the configured loopback port. Keep the original private dump and previous
launcher as the recovery point. AWS publication requires separate authorization
after Product Owner local acceptance.

## Administrator restriction (2026-11-10)

Switch user is rendered only for a currently valid RF1 platform administrator
or owner. Both GET /local/users and POST /local/access-user validate that same
permission server-side before listing accounts or changing identity. Domain
administrator roles do not confer this capability. After selecting a nonadmin
account, the control disappears and that account cannot use either endpoint.
The restriction is checked afresh, including inactive/revoked sessions.
