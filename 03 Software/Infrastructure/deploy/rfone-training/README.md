# Training AWS release

Authorized by the Product Owner on 2026-11-10: publish the completed Training
workspace in English and then push its scoped source. The Italian local workspace
is retained. The release uses an isolated Training App Runner image and official
CloudFront routing, sharing the existing RF-One cookie secret, session version
checks and TRAINING grants. No automatic local sign-in or permission bootstrap is
included. The existing web, Kitchen, Selection and Tips images are not replaced.

Database publication is additive and explicit before service deployment: student
metadata, submission replay protection, withdrawn catalog records, immutable
course versions/files and assignment-version references. The existing Visual Menu
course is initialized by stable slug, and individual-dish entries are withdrawn
without deleting content or historical assignments. No local working database,
student account, account grant or local uploaded file is synchronized to AWS.

Uploaded course materials remain in the shared managed PostgreSQL database and
retain per-assignment authorization. Visual Menu reads the existing Kitchen
tables and serves existing private S3 media through authenticated endpoints.

Release evidence is recorded under `output/training-release-20261110` outside the
committed source. A manual RDS snapshot and the prior CloudFront configuration
are recorded before mutations. Rollback restores prior routing/images and keeps
additive Training data; do not drop course files or historical versions.
