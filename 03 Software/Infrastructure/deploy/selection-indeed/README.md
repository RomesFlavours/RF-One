# AWS Indeed browser worker

This is an additional service, not a replacement Selection deployment. It has
no database/S3 access. Selection retains its existing RDS and private S3 store.
No AWS resources are created by these files.

## Runtime

Build the Dockerfile from the RF One repository root and run **one replica** on
Linux EC2 with an encrypted EBS volume mounted at `/data` (root-owned, mode 0700).
Use an ALB HTTPS listener, its ACM certificate, and a dedicated hostname/root
path for the worker. Route WebSocket upgrades to the same container; set the
ALB idle timeout to at least 120 seconds. Only target port 8080 may be reached
from the ALB security group. Never expose VNC 5900 or X11 6000. Chromium runs as
uid 10001; provide at least 2 vCPU / 2 GiB RAM and 1 GiB shared memory.
Run the container with `--restart=unless-stopped`, plus tmpfs mounts on `/tmp`
and `/home/browser` (uid/gid 10001 for the latter). These hold temporary downloads
and browser runtime files and must be emptied on container restart. The only
durable writable mount is the encrypted `/data` ledger. A Gunicorn worker exit
terminates the whole container so an orphaned browser is never inherited.
The HTTP/Playwright service runs as container root; only the headed Chromium is
dropped to uid 10001 by the fixed launcher. It receives a minimal environment
without the API key and cannot read root's process environment or `/data`.
Do not override the image user, mount the Docker socket, grant host privileges,
or expose CDP/debugging ports. Restrict outbound access to Indeed, its
sign-in/assets dependencies and Selection HTTPS.
Do not attempt to evade Indeed verification or access controls.

Inject secrets with SSM/Secrets Manager at runtime; do not bake them into images
or put them in source control. Use one cryptographically random key of at least
32 characters, shared only by Selection and this worker.

Worker environment:

| Variable | Value |
|---|---|
| `RFONE_INDEED_KEY` | Shared secret |
| `RFONE_INDEED_PUBLIC_URL` | `https://<worker-host>` (root, no trailing path) |
| `RFONE_INDEED_SELECTION_URL` | `https://rfone.romesflavours.com/selection` |
| `RFONE_INDEED_STATE` | `/data/indeed.sqlite` (default) |

Selection environment:

| Variable | Value |
|---|---|
| `RFONE_INDEED_KEY` | Same secret |
| `RFONE_INDEED_WORKER_URL` | Same URL as worker public URL |

Deploy the changed Selection files (including `indeed_protocol.py`, workspace
routes/receiver and templates) using the normal Selection release process.
No schema migration is required. Configure the callback on Selection's official
hostname so the machine POST does not redirect. Worker and Selection fail on
redirect rather than forwarding credentials. Worker calls can last up to 120
seconds per CV; configure gateway/request timeouts accordingly.

The worker's API requires a bearer key. Browser links are short-lived tickets,
issued only after RF-One checks edit access to the job's position. A secure,
HttpOnly, SameSite=Lax cookie gates every viewer asset and WebSocket (Lax allows
the top-level redirect from a Selection hostname on another site); the socket
also checks Origin and revocation continuously. Tickets never grant worker API
access. Do not log query strings at ALB/proxy level: `/open` contains a short-lived
viewer capability. Browser access is revoked when downloads start. Closing a
tab does not stop a job; use Selection's Stop control.

One active browser is supported. Do not run multiple Gunicorn workers, use
`--preload`, scale replicas or attach the SQLite volume to multiple instances.
The ledger retains job metadata and per-candidate checkpoints, never CV contents,
passwords or SMS codes. Browser cookies exist only in an ephemeral context.
After a restart/30-minute session deadline, the operator signs in again and
resumes. Stop takes effect between operations (a download or import may finish).
No-resume results are explicit; unknown page layouts pause/fail rather than
silently report success. Indeed UI changes may require selector updates.

## Acceptance before enabling production use

1. Install the worker requirements in a test environment (plus `websocket-client`
   for the transport test), then run `python -m unittest test_indeed_import.py
   test_indeed_browser.py test_indeed_viewer.py` in Selection. Install Playwright
   Chromium, or set `RFONE_TEST_BROWSER_EXECUTABLE` to an existing browser for
   the offline browser tests. Then run the existing
   `python test_selection_workspace_http.py` and How Works check.
   The repository currently has multiple Alembic heads. The new HTTP tests use
   a disposable schema built from model metadata; the production migration
   history is untouched. Reconcile the existing migration heads in the normal
   release process before deploying from a checkout that still has this issue.
2. Build/run the Linux container and check `/health`, unauthenticated API 401,
   viewer 403, valid viewer ticket and WebSocket, expiry and revocation.
3. From a synthetic/test position in the deployed app, verify login/SMS manually
   and a short real Indeed import. Confirm original files in private S3 and
   PositionCandidate links only to the requesting position. Verify pagination,
   restart/resume and revoked manager access. Real candidate imports require the
   Product Owner's authorization for that test.
4. Keep the feature disabled until this live check passes. Rollback: remove the
   two Selection env vars and stop the worker; existing imported CVs stay valid.

Implementation references: [Playwright downloads](https://playwright.dev/python/docs/downloads),
[headed Linux execution](https://playwright.dev/python/docs/ci),
[noVNC embedding](https://novnc.com/noVNC/docs/EMBEDDING.html).

AWS references: [ALB WebSocket listeners](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html),
[ALB idle timeout](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html).
