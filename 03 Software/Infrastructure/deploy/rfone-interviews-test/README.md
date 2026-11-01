# Interviews TEST release

Publish the common interview prototype inside the existing `rfone-web` service and official RF-One entry. Every interview page displays TEST. Existing RF-One login and EMPLOYEES Domain access are preserved for administrators; the assigned active account alone can conduct an interview. No local demo login, fixture, setup token or anonymous access is deployed. The configured RF-One AI provider is used, not simulated answers.

## Verified release baseline

The deployed S3 source was compared with `release/selection-complete-20261030` (`2d85435`). All 819 application files matched except `RF-One Web/templates/home.html`, whose already-live directory thumb marker is preserved. This release does not ship the dirty handoff checkout or its unrelated schema changes.

AWS already has the unified person directory (`Employee`, `EmployeeContextLink`, aliases and context resolution) at migration `d9e220261029`. Interviews reuse it through `interviews/directory_bridge.py`. The earlier local prototype's CandidatePerson master and person_account_links/person_employee_links are superseded for this deployment and are not shipped. No parallel people registry is created. The `/people` URLs are redirects to the existing directory. Directory authorization, source identity reconciliation and existing operational features remain owned by their current services.

The new additive migration `e0a120261101` creates only interview_sessions and three indexes. person_id references employees; requester and delivery login reference rfone_accounts. It changes no people, account, employment, financial or Selection records. A request needs one unambiguous active linked login; ambiguous identity chains cannot receive it. Removing or changing a person/login link revokes access to an assigned interview. Existing alias consolidation preserves interview identity via the declared Employee FK.

## Deployment sequence

1. Verify AWS account 418674484214, profile rfone-dev-login, region us-east-1.
2. Confirm running image and database revision. Create an RDS snapshot before migration.
3. Commit the isolated release, archive the Docker COPY directories with forward-slash paths, and include the existing Dockerfile/buildspec. Never include .env, credentials, local data, demo server or fixtures.
4. Upload to a versioned release S3 key. CodeBuild source/buildspec overrides build and push a unique ECR tag, leaving the existing source key and running image intact.
5. Run tools/apply_interviews_test.py once as a short-lived ECS task using the existing database secret, execution role and allowed network. It accepts only d9e220261029 or the already-applied new revision. No unrelated migrations run.
6. Update only rfone-web's image identifier, retaining all settings, roles, networking and secret references. Wait for successful deployment and verify public login redirects and existing pages.

The application never migrates on import. The feature's auth pages are not indexed and use no-store. TEST does not mean data is automatically synthetic: users must select suitable test content and AI output remains unvalidated. Voice uses the browser's speech service; raw audio is not stored by RF-One.

## Verification and rollback

Run tests/test_interviews.py and tests/test_image_layout_startup.py on the release tree; exercise existing directory tests for regressions. Deployment verification never creates real interviews or changes real person links. If application deployment fails, restore the recorded prior immutable image. The new table is additive and can remain while the previous image runs. Do not drop interview data automatically; a schema downgrade is an explicit operational decision.
