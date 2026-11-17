# Email Control interface refresh

Deployed successfully on 17 November 2026 at 16:37:25 America/New_York.

## Result

- Compact summary: total messages, in progress, accepted by Aruba, needs attention.
- Searchable message register with subject, recipient, Domain and readable status labels.
- One-click attention/in-progress filters, Domain/status filters, inclusive local-day date filters and 25-message pagination.
- Detail page with message content, chronological activity, clear permitted actions and collapsed technical information.
- Search/filter context retained when returning from a message.
- RF-One olive palette, existing typography, shared breadcrumbs, responsive layout and visible keyboard focus.

SMTP acceptance remains distinct from confirmed recipient delivery. Uncertain
messages still cannot be resubmitted. Authorization, CSRF and the central
queue's state transitions remain enforced.

## Release evidence

| Reference | Value |
| --- | --- |
| Branch | `codex/rfone-email-service-aws` |
| Image source commit | `577705cb03db83b24409aa05d9ecd53a880ff38c` |
| Image | `rfone-web:email-ui-577705cb03db` |
| Digest | `sha256:0193f695dc9fc3d22ca662e797b2825704954bde8095e6ecc83db214946fa18f` |
| CodeBuild | `rfone-web-build:b44f5ff9-7255-43c3-82d4-74593e721fcd` — SUCCEEDED |
| App Runner update | `62ce1bb621b44e44adc959789611ff90` — SUCCEEDED |
| Service | `rfone-web` — RUNNING |

The release overlays only the Email Control routes, templates and scoped CSS
on the previously running image, plus a small registration change to reuse
RF-One's existing Location timezone resolver. Other application source files
were preserved. No database migration or SMTP worker deployment was performed.

## Validation

All 23 dedicated tests passed locally and again inside the built Linux image.
Additional coverage checks subject search, attention filters, inclusive local
dates, escaped message content and safe return navigation. Browser checks
covered the desktop register, attention filter, message detail, preserved
list context and mobile layout without horizontal document overflow.
Browser preview records were fictional and used a disposable local database.

After deployment:

- `/login`: 200.
- `/training`: unchanged 302 to Training sign-in.
- `/selection/`: unchanged 302 to RF-One login.
- `/administration/email`: 401 without authentication.
- `/static/css/email-control.css?v=1`: 200, serving the new stylesheet.
- Existing ECS email worker: ACTIVE, running 1 / desired 1, task definition `rfone-email-service:1` unchanged.

No production request was enqueued and no real test message was sent.
Live authenticated page rendering was not exercised through a production
user session; administrative rendering and actions were checked in isolation.

## Access and rollback

Open <https://rfone.romesflavours.com/administration/email> with an active
RF-One administrator session.

The UI release tool is `deploy_ui.py`, with explicit `build`, `status`,
`deploy` and `rollback` actions. Its secret-free state is retained as
`rfone-email-ui-release-state.json` in the operating system temporary directory.
Rollback restores the saved Web source configuration and prior image
`rfone-web:email-7291a4ac8419`. It does not scale, restart or modify the worker
and does not change the database or queue.
