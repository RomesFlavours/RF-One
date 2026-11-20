# REPORT — Registry layout AWS release

Date: November 13, 2026.

## 1. Published outcome

Registry at https://rfone.romesflavours.com/admin/roles?tab=companies now uses the Training visual standard: underlined tabs, help beside navigation, matching spacing, table cards and sticky modal headers. Every existing profile modal has anchored contextual help. Closing Help with Escape retains the underlying editing window and its unsaved draft.

The release is a narrow overlay over the exact image previously deployed on AWS. It preserves that version's Registry functionality, account grants, authentication, Training onboarding and other application modules. Newer local identity/status/reconciliation functionality is outside this layout release.

## 2. Acceptance criteria and observed results

| Criterion | Result |
|---|---|
| Exact production baseline | Prior image digest verified before preparing the overlay |
| Source frozen and pushed | Application source commit `f499c63f0e63cc961d4e42e9784f6c376674d531` on `codex/registry-layout-20261113` |
| English shared interface | Four real entry-point pages, contextual help and principal modals passed |
| Existing operations preserved | Isolated SQLite tests passed area/role saves, duplicate validation, CSRF and anonymous/ordinary-user denial |
| Immutable image tests | The same entry-point checks passed inside the AWS CodeBuild Docker build |
| Contextual help consistency | Scoped How Works check passed with zero errors; 63 inherited pages remain unchanged legacy coverage warnings |
| App Runner operation | `76cc13f5471843e88ae7daec66b99be8` completed SUCCEEDED; service RUNNING |
| Public HTTPS acceptance | All four authenticated Registry tabs returned 200; anonymous access still redirects to login |
| Browser acceptance | Microsoft Edge, 1440px and 390px: no page overflow, no JavaScript errors, page/modal help and preserved drafts, including Escape |
| Public asset integrity | Served CSS SHA-256 matches the tested, committed source |
| Existing service settings | Secrets, permissions, health checks, network and scaling configuration preserved; only image identifier and source revision changed |
| Data and schema | No migrations, data synchronization, account creation, grants or production data writes performed |
| Local Italian copy | Source and local automatic access preserved; running local copy confirmed Italian |

## 3. Source and image provenance

- Application commit: `f499c63f0e63cc961d4e42e9784f6c376674d531`.
- Source branch: https://github.com/RomesFlavours/RF-One/tree/codex/registry-layout-20261113.
- Source archive: `s3://rfone-tips-deploy-418674484214/registry-layout/releases/20261113/f499c63f0e63cc961d4e42e9784f6c376674d531.zip` (AES256).
- Source archive SHA-256: `b9039a4c1404851e5e08c66cb86bfea17698ea6a55cf35a8d27090beac098777`.
- CodeBuild: `rfone-web-build:ada89b3f-5813-4249-a49a-20f3cb645103` — SUCCEEDED.
- Image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-layout-f499c63f0e63`.
- Image digest: `sha256:70f8e543d2c3468f6c497d45139ac9153bb576877ee4d0e4be2f5b663e233871`.
- Four runtime overlay files: Registry template, Registry help, Registry CSS and Registry keyboard guard. Test/build/manifest files accompany them. No application authorization or data-store code was replaced.

## 4. Rollback

Restore the RF-One Web SourceConfiguration saved in `output/registry-layout-release-20261113/service-before.json`, including its prior release revision and existing environment/secret references. The prior image is `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-training-web-bf9ee0c80531` at digest `sha256:a870a383890078f0e2009839ef69f131b00c11d6b157cac8ab9b3c98666cbe6a`.

No database restore or schema downgrade is needed for this presentation-only release.

## 5. Remaining local limitation and evidence

Automatic approval review rejected the combined local-server restart/browser-verification command with `blocked by policy`. It was not retried or bypassed. The running local process therefore has not loaded the final keyboard guard; its Italian source files are updated on disk. This does not affect the successful AWS deployment or the public browser acceptance.

Private local evidence: `output/registry-layout-release-20261113/` contains the baseline and final service configurations, immutable source metadata, build/test logs, operation results, public acceptance JSON and desktop/mobile screenshots. Session secrets and authentication cookies were used only in memory and were not written to reports or committed source.
