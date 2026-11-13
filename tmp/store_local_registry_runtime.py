from pathlib import Path
base=Path('tmp/git-anagrafica-release')
p=Path('tmp/launch_registry_local.py');s=p.read_text(encoding='utf-8');s=s.replace("source=Path(r'C:/Users/servi/.codex/worktrees/edee/RF One/tmp/git-anagrafica-release/03 Software')","source=Path(state.get('development_source',str(ROOT/'source')))")
p.write_text(s,encoding='utf-8',newline='\n')
target=base/'03 Software/Infrastructure/Registry Local';target.mkdir(parents=True,exist_ok=True)
(target/'launch_local.py').write_text(s,encoding='utf-8',newline='\n')
(target/'README.md').write_text('''# Registry local acceptance runtime

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
''',encoding='utf-8',newline='\n')
