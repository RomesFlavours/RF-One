# REPORT — Registry and Training AWS release

Date: November 13, 2026. Explicit Product Owner authorization covers required AWS
changes, backups and tests, and deletion of all existing trial students.
The user separately confirmed that “all” includes the two historical students,
and authorized test mail to pm@rmaed.it. They confirmed the initial test arrived
in the inbox.

## 1. Released outcome

RF-One Web and Training deployment operations both completed SUCCEEDED and both
services are RUNNING. Official entry: https://rfone.romesflavours.com.
Registry: /admin/roles?tab=people. Trainer: /training/manage/students.
Student sign-in: /training/access. New students activate through their personal
emailed link, supply the initial credentials and choose a different password.
Recovery: /training/account/recover.

The release adds explicit CandidatePerson/person-account/Training links and STUDENT
qualification, without creating employees or changing other module permissions.
Existing Registry navigation, company-based access rules, role normalization,
read-only authorization and the previously released Visual Menu are preserved.
The overlay is based on the exact deployed image for each service; do not replace
it with a blanket copy of the older local application.

## 2. Data and schema

Live preflight found k9g120261112, not the older t9a revision in the November 12
plan. Registry tables were absent. The explicit additive migration r9a120261113
therefore descends from k9g120261112. It creates person_account_links,
person_employee_links, person_qualifications, training_person_links and
person_company_statuses. It does not replay Kitchen migrations or stamp the
unrelated local branch.

After a record-level encrypted S3 backup and the RDS recovery backup, the
authorized cleanup removed Training students 6 (Tatiana) and 7 (the girl),
their two needs, 56 assignments and one RF-One/Training link. Shared RF-One
accounts, central person/employee identities and unrelated permissions were
preserved. This is production cleanup; the local working database was not
synchronized or rewritten.

The final read-only audit finds zero students, no acceptance fixture accounts
remaining, the expected Registry tables and unchanged protected facts across all
30 protected tables. The employee_clover_links whole-row
fingerprint changed during the release window. A second private restore, this time
from the encrypted snapshot, established that only last_seen_at and last_run_id
were refreshed by existing ingestion runs: identities, links, states and source
snapshots are unchanged. Those legitimate tracking updates were retained, and the
final check compares all remaining fields against the restored baseline.
PostgreSQL sequence gaps from
tests are expected and are not reset.

## 3. Verification

Local functional onboarding/activation/recovery tests and nine Registry status
tests passed. Both actual release artifacts passed their scoped How Works check:
Training 20 pages, zero errors; Registry one changed page, zero errors. Registry's
63 inherited pages remain explicit legacy coverage limitations; this is not a
claim that global repository coverage is complete.

Actual entry-point tests on disposable SQLite databases passed locally and
inside each Docker build. Edge browser checks covered the trainer's dialog,
contextual help and ordinary student sign-in/mobile home (390px with no horizontal
overflow). Screenshots were inspected. The local Italian source was preserved.

Public HTTPS acceptance checks:
- Public HTTPS trainer login and management pages
- Actual Registry/STUDENT creation and activation email accepted for pm@rmaed.it
- Shared public login blocks initial credentials until activation
- Public activation -> personal password -> MyRF -> Training; other modules denied
- Existing published course assigned and opened over public HTTPS
- Real recovery email accepted and password reset/public sign-in passed

The acceptance trainer and student were created solely for testing and removed
with their links, qualifications, assignments, codes and identities. Secrets,
initial passwords, recovery codes and activation tokens were kept in process
memory, not written to the evidence report. SMTP was exercised from the AWS
network; the initial delivery test was confirmed in the recipient's inbox.

An additional test submitted New student through the actual public HTTPS form,
and the deployed App Runner service returned Invitation sent after real SMTP
delivery. That additional trainer/student fixture was also removed.

## 4. Backup, restore and rollback

RDS snapshot rfone-dev-pre-registry-training-20261113 and its encrypted copy
rfone-dev-pre-registry-training-20261113-encrypted are available. The encrypted
copy uses the AWS-managed RDS key. A private temporary restore of the snapshot
was checked against the original inventory (24 protected tables matched), then
used to rehearse the additive DDL and exact student deletion. The temporary
instance was deleted and its absence verified.

Record-level backup: s3://rfone-tips-deploy-418674484214/registry-training/releases/20261113/apply-student-record-backup.json
(server-side AES256 encryption). The backup contains recovery data and is not
included in the local report or shared source artifact.

Application rollback restores each saved pre-release SourceConfiguration,
including prior image and environment/secret references. Retain additive Registry
tables and new student data; do not run a destructive downgrade. Restoring removed
trial students, if ever requested, requires the private record backup or restoring
the recovery snapshot to another instance and selectively recovering those records;
never replace the live database blindly.

## 5. Traceability and limitations

- web: source `bf9ee0c805318a42b81875f9aae3a85e3e5133ca`, image `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-training-web-bf9ee0c80531`, digest `sha256:a870a383890078f0e2009839ef69f131b00c11d6b157cac8ab9b3c98666cbe6a`.
  Rollback image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-navigation-20261112t164512z` at `sha256:fb932cb91a6df290f456bf7e09488f299b5f45197be590f093e46ab1461836c8`.
- training: source `7a247b9a2a6fc13148a2d0c7e6fb136727d60182`, image `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-training-training-7a247b9a2a6f`, digest `sha256:6f228bf45a50b32bec1cc94c032296e90d12b39f603a4c50087853f902f25812`.
  Rollback image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:visual-menu-76747f071ac3` at `sha256:801870e54a3940bd840cebcc2567a685301b6f6b9ea1781edc71f066af9fa389`.

Evidence: output/registry-training-release-20261113, including deployment status,
source manifests, immutable source archives, help-check logs, restore verification,
production cleanup and final integrity results. The canonical migration is
03 Software/RF-One Data Store/migrations/versions/r9a120261113_registry_training_aws_release.py.

The automatic approval review rejected removal of local disposable test folders
under %TEMP%. Those isolated test files remain; this did not block production
student cleanup. Existing non-Training student-independent Registry people and
shared accounts were intentionally preserved.

Temporary cleanup completed: both private restore instances were deleted and their absence verified; 14 temporary ECS task definitions were deregistered, the release task role was removed, and the shared test execution role SMTP permission was restored. Production SMTP permissions remain in place.
