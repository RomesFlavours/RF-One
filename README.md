# Selection: isolated Render free trial

Synthetic data only. AWS, production credentials, existing accounts and CVs are excluded.
The snapshot contains the integrated RF-One login and Selection; it is not the historical
Selection Prototype. It is deliberately published on a separate branch, never main.

Build a new source snapshot with `python build_snapshot.py <new-directory>`.
The SHA256 manifest identifies the exact working-tree source and trial adaptations.
The historical overlong PostgreSQL constraint is shortened only in the snapshot.

Apply the root render.yaml from branch `codex/render-selection-free-trial` in workspace
RF One. Both resources explicitly use Free. The database already created with the same
name must be reused. Do not create a second database or upgrade a plan.

Login: `render-trial`. The initial password is the generated RFONE_TRIAL_ADMIN_PASSWORD
in the Render service Environment panel; it is never committed or logged. Changing that
variable later does not reset the existing account's password.

The WSGI launcher requires a separate trial DB, disables provider calls, SMTP and the
Aruba bridge, mounts Selection at /selection, enables HTTPS cookies and noindex headers,
and marks every HTML page as a synthetic trial. A single preloaded worker runs schema
initialization once per start; four request threads allow a small concurrency test.
This bootstrap pattern is trial-only, not the intended production migration process.

## Test and evidence

Run `python test_trial_wsgi.py` within the packaged snapshot for a disposable SQLite
integration check. This is not proof of PostgreSQL or Render compatibility.
The existing Selection workspace suite passes locally with isolated AI and mock email.

On Render verify build/start, /trial-health, real login, all five workspace tabs,
synthetic CV upload/read, denial of anonymous internal access, concurrent requests,
data survival across redeploy and loss of temporary CV files after a new instance.
Record failures as well as response times, and separate cold-start from warm requests.
Database export/restore remains pending until tooling and a second isolated restore
target are available. Free Postgres has no managed backup and expires after 30 days.

No live AI, SMTP, IMAP or AWS comparison has been executed by preparing these files.
IMAP needs a connector test; it is not known to require a paid Render instance.
Document deletion semantics also require a separate check (LocalDocumentStore.discard
currently retains files); deleting a database row is not proof of physical erasure.

## Costs and future migration

Free trial infrastructure: $0 within included bandwidth and build limits.
Paid SMTP connectivity and persistent documents: Starter app $7/month + 1 GB disk
$0.25/month. Paid PostgreSQL starts at $6/month; baseline combined $13.25/month.
For 2 GB application RAM use $25/month instead: $31.25/month baseline.
Add database storage charges if applicable, taxes and any usage exceeding allowances.
OpenAI usage is separate and requires an explicit budget and provider adaptation.
Existing Aruba mailbox fees are unchanged; no new mailbox is provisioned.
Source prices: https://render.com/pricing ; limits: https://render.com/docs/free .
Confirm the actual quoted total before activating any paid resource.

The paid DB includes managed recovery, with a 3-day PITR window on Hobby. Persistent
disks have daily snapshots retained for 7 days; independent DB/file backups still need
a consistent recovery procedure. Restoring PITR creates another DB and can add compute
cost while both exist. A disk limits the app to one instance and interrupts redeploys.

Future migration is conditional on successful tests. First inventory the few live AWS
services and schema revisions; establish one authoritative database, automated migrations,
backup/restore checks and compatible application releases. Prefer initial copy plus
verified delta transfer and a short controlled cutover over bidirectional DB writes.
A temporary shared DB across providers needs explicit network access, TLS, compatible
schema, measured latency and a rollback boundary; none is enabled in this trial.
