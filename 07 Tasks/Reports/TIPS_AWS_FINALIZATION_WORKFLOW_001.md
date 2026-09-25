# TIPS_AWS_FINALIZATION_WORKFLOW_001 — Tips validation on AWS

Date: 2026-09-25. Baseline: `main` @ `c7d8a29`, Alembic head `e7b2c94d0f18`.
Not deployed. No AWS run state changed. No payment executed.

## Problem

`rfone-web` (`vhmsm9mgh8.us-east-1.awsapprunner.com`) and `rfone-tips`
(`mxgsc3nwha.us-east-1.awsapprunner.com`) are separate App Runner hostnames.
The RF-One login is RF-One Web's Flask signed-cookie session (cookie
`session`, host-only, path `/`, `Secure`, `HttpOnly`, `SameSite=Lax`). A
browser never sends it to the Tips hostname, so the Tips app sees every
request as anonymous and — correctly — refuses validation
(`Tips/rfone_identity.py`, §15). Result: CALCULATED runs cannot become FINAL
on AWS, and only FINAL entitlements are payable.

Root cause class: **A — browser cookie scoping (two hostnames)**. Same
secret variable, same session keys, same account table: the code contract
is shared; the topology is not. A parent-domain cookie is not an option on
`awsapprunner.com` (it would expose the cookie to unrelated tenants).

## Solution

The one human step (CALCULATED → FINAL) is offered on `rfone-web`, where the
person is signed in: `RF-One Web/tips_validation_routes.py`
(`/tips/runs`, `/tips/runs/<id>`, `POST /tips/runs/<id>/validate`), behind
`require_domain_access("TIPS")` and `require_csrf()`, calling the unchanged
`calculation_run_service.validate_run`. The Tips app's own validation route
now applies the same TIPS-access and CSRF gates. The Domain-access rule and
the CSRF session key moved into `rfone_data_store/rfone_web_session.py` so
both apps read one definition.

The wider question — one ingress (A), Tips mounted in RF-One Web (B) or a
custom domain (C) — stays open (see `03 Software/Infrastructure/README.md`).

## Model note

The approved state model is `CALCULATED → FINAL`: validation by a person
IS finalization (§14). There is no separate persisted VALIDATED state.

## Tests

`RF-One Web/tests/test_tips_validation_http.py` (13 checks) and
`Tips/test_tips_validation_authorization_http.py` (5 checks).
