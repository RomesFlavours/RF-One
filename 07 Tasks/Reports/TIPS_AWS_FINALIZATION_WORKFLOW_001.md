# TIPS_AWS_FINALIZATION_WORKFLOW_001 — Tips validation on AWS

Date: 2026-09-25. Baseline: `main` @ `c7d8a29`, Alembic head `e7b2c94d0f18`.
Final checkpoint: `main` = `origin/main` = `ad5fe0b` (after `0abc441`).

**Status: completed and deployed.** `rfone-web` and `rfone-tips` are
RUNNING. The finalization workflow is live on `rfone-web`. No run has been
finalized and no payment has been executed.

Source of the deploy facts below: the completed deployment report, as
supplied by the Product Owner on 2026-09-25. An earlier version of this file
read "Not deployed" and ended at the rollback; that version is superseded.

## 1. Original problem

`rfone-web` (`vhmsm9mgh8.us-east-1.awsapprunner.com`) and `rfone-tips`
(`mxgsc3nwha.us-east-1.awsapprunner.com`) are separate App Runner hostnames.
The RF-One login is RF-One Web's Flask signed-cookie session (cookie
`session`, host-only, path `/`, `Secure`, `HttpOnly`, `SameSite=Lax`). A
browser never sends it to the Tips hostname, so the Tips app sees every
request as anonymous and — correctly — refuses validation
(`Tips/rfone_identity.py`, §15). Result: CALCULATED runs could not become
FINAL on AWS, and only FINAL entitlements are payable.

Root cause class: **A — browser cookie scoping (two hostnames)**. Same
secret variable, same session keys, same account table: the code contract
is shared; the topology is not. A parent-domain cookie is not an option on
`awsapprunner.com` (it would expose the cookie to unrelated tenants).

## 2. Implemented finalization solution (`0abc441`)

The one human step (CALCULATED → FINAL) is offered on `rfone-web`, where the
person is signed in: `RF-One Web/tips_validation_routes.py`

| Route on `rfone-web` | Purpose | Server-side gates |
|---|---|---|
| `GET /tips/runs` | list of saved Calculation Runs | `require_domain_access("TIPS")` |
| `GET /tips/runs/<id>` | saved report (never recalculated) | `require_domain_access("TIPS")` |
| `POST /tips/runs/<id>/validate` | validation → FINAL | `require_domain_access("TIPS")` + `require_csrf()` |

The route calls the unchanged `calculation_run_service.validate_run`. The
Tips app's own validation route now applies the same TIPS-access and CSRF
gates. The Domain-access rule and the CSRF session key moved into
`rfone_data_store/rfone_web_session.py` so both apps read one definition.
The standalone Tips host remains separate and still does not receive the
RF-One Web session cookie.

Model note: the approved state model is `CALCULATED → FINAL`: validation by
a person IS finalization (§14). There is no separate persisted VALIDATED
state.

Tests: `RF-One Web/tests/test_tips_validation_http.py` (13 checks) and
`Tips/test_tips_validation_authorization_http.py` (5 checks).

## 3. Deploy incident

The first deploy of `0abc441` crash-looped `rfone-web` at runtime with
`ModuleNotFoundError: clover_explorer` (HTTP 502 from about 15:53 UTC until
the rollback completed). `tips_validation_routes.py` imports
`tips.calculation_run_service`, whose engine imports the Clover connector,
which needs `clover_explorer` from `03 Software/Clover Data Explorer/`. The
`rfone-web` image never copied that folder; local tests passed because every
sibling folder is on disk locally. No data changed.

## 4. Rollback

`rfone-web` was rolled back to its previous working image (same config and
layers as `sha256:d807cc9d…`).

## 5. Forward fix (`ad5fe0b`)

- The `rfone-web` Dockerfile and buildspec are now versioned under
  `03 Software/Infrastructure/deploy/rfone-web/`, so the image is built from
  committed files only.
- The Dockerfile copies `Clover Data Explorer` into the Web image.
- `RF-One Web/tests/test_image_layout_startup.py` imports the app inside the
  image layout rebuilt from the Dockerfile's COPY lines; it reproduces the
  crash without the fix.

## 6. Final deployed state

| Item | State |
|---|---|
| `0abc441`, `ad5fe0b` | pushed; `origin/main` = `ad5fe0b` |
| `rfone-web` | fixed image deployed successfully; **RUNNING**; no further application errors after 16:09:30 UTC in the observed window |
| `rfone-tips` | built and deployed successfully; **RUNNING** |
| Finalization UI on `rfone-web` | available (`/tips/runs`, `/tips/runs/<id>`, `POST /tips/runs/<id>/validate`) |

## 7. Runs 7 and 8

Both remain **CALCULATED**. They are the same calculation, done twice:

| Attribute | Run 7 = Run 8 |
|---|---|
| Business Dates | 2026-09-14 → 2026-09-20 (7 Business Dates) |
| Rule Version | same |
| Timezone / cutoff | same, 04:00 cutoff |
| Employee entitlements | 9, identical populations |
| Total | $5,953.28 |
| Voluntary | $5,782.28 |
| Gratuity | $171.00 |
| Balanced | yes |
| Finalization blockers (before either is finalized) | none |
| Referenced by a payment | never |

## 8. Overlap protection

Only one overlapping run may become FINAL. Once either run 7 or run 8 is
finalized, the other is blocked by the existing overlapping-FINAL protection
(`_blocking_final_run` in `rfone_data_store/tips/calculation_run_service.py`:
same Restaurant, overlapping Business Date range, identical ranges
included). Finalizing one of them is therefore safe; the choice of which one
is the Product Owner's.

## 9. Payment safety

- 0 payment cycles.
- 0 payment instructions.
- No entitlement assigned to a payment.
- No payment executed.

## 10. Current UI issue (next task — not fixed here)

On the standalone Tips host, the Saved Periods table at `/tips-runs` lists
runs 7 and 8, but its rows do not lead the person to the approved
finalization workflow on `rfone-web` `/tips/runs`. The transition from the
Tips Saved Periods UI to the Web validation UI is neither obvious nor
useful. Recorded as the next UI/workflow task.

## 11. Remaining architectural question

The wider question — one ingress (A), Tips mounted in RF-One Web (B) or a
custom domain (C) — stays open (see `03 Software/Infrastructure/README.md`).
It is **not** a blocker: the current manual finalization workflow on
`rfone-web` is already operational.
