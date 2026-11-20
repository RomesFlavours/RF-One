# REPORT — Local session handoff, November 14, 2026

## 1. Resume the actual local development source

Read `CLAUDE.md` first. The main OneDrive checkout contains today's uncommitted MyRF/Home, Registry and local module integration. Do not discard or reset those changes. Its local entry point is `03 Software/RF-One Web/visual_menu_local.py`, URL `http://127.0.0.1:5097/`. The existing operator is `rfone`; retain its actual permissions, automatic loopback login and Italian UI.

The database used by this entry point on the source PC is `127.0.0.1:55436/rfone_aws_copy`. Its observed schema revisions are `k9f120261112` and `t9d120261113`. The old `%LOCALAPPDATA%/RF-One/local-runtime.json` points at a different, older Registry-only launcher on 5094/55571; it does not describe today's main-checkout Home. Do not silently switch databases or merge them.

The November 14 contextual help instruction supersedes the earlier tab-bar placement: page/modal help must be right-aligned immediately below the title/content divider. Do not reapply the older layout blindly.

## 2. OneDrive continuation

The private checkpoint is `output/local-continuity/current/`, excluded from Git. It contains a consistent PostgreSQL dump of 328 tables, portable PostgreSQL binaries, pinned Python dependency wheels, 52 local photo assets, source checkpoint and SHA-256 manifest. The source database was not changed to create it.

Before leaving the source PC, close local apps and run `Prepara cambio PC.cmd`. It refreshes the recovery copy and verifies that the source database stopped. Wait until OneDrive is fully synchronized. On the second Windows x64 PC, make the full project available offline, ensure Python 3.12 x64 is installed, and run `Riprendi lavoro locale.cmd`. It creates a per-PC Python environment from the included wheels and restores only into a new project-relative local database. It never overwrites existing local data, runs migrations or creates/grants accounts.

One active PC at a time is mandatory. The synchronized handoff marker is not a reliable distributed lock. Do not open on the second PC until the first PC is closed and synchronization has completed. Future portable sessions must use the same prepare/close procedure before switching again.

An independent restore test checks every table count and the schema revisions. This does not certify execution on the second PC or completion of OneDrive synchronization; those must be verified there.

## 3. State of the work in this chat

Registry layout was deployed on November 13, from application commit `f499c63f0e63...`, branch `codex/registry-layout-20261113`; release report commit `06a1153`. Final image digest was `sha256:70f8e543d2c3468f6c497d45139ac9153bb576877ee4d0e4be2f5b663e233871`. This is historical provenance, not a fresh assertion about today's live image. See the existing release report and evidence in `output/registry-layout-release-20261113/`.

AI cost audit covered October 14 through November 13, 2026, AWS billing dates UTC: USD 33.467919895 gross usage, USD 6.21643561 credits, USD 27.251484285 net. Gross model amounts: Haiku 4.5 USD 30.949126075; Sonnet 4.5 USD 2.0786766; Opus 4.6 USD 0.426426; GPT-OSS 120B USD 0.0136887; Nova Lite USD 0.00000252. November amounts were provisional. No reliable module-level attribution exists in the inspected billing/logging setup. Direct OpenAI cost access returned 403 with available credentials; direct Anthropic administrative billing access was not available. Do not report unknown direct-API spending as zero.

SMS discussion was informational only. No SMS service, sender, registration, spend limit or production integration was activated or tested. Any later implementation needs its own concrete task. Sending is distinct from AI inference. Bedrock also uses APIs; changing transport alone does not establish better quality or speed.

## 4. Per-PC dependencies and limits

AWS SSO, API administrative access, Codex login and SMTP configuration are not transferable credentials and were not copied. Each PC needs its own authorized configuration for cloud AI or mail. The PostgreSQL dump retains 150 remote S3 references (149 résumé references and one Development Journal document); these were not downloaded or rewritten. Training course file bytes are stored in the database. Local photos are included and relocated only in the restored database.

RFBank is separate. Its existing source and recovery material under `RFBank/` remain preserved on OneDrive, but its launcher still references a private per-PC runtime absent from the inspected source PC. No older Bank recovery file was promoted to the active database. The portable MyRF launcher does not certify or replace that separate Bank installation.

## 5. Traceability

- `03 Software/Infrastructure/Local Continuity/README.md` and `continuity.py`.
- Root launchers `Prepara cambio PC.cmd` and `Riprendi lavoro locale.cmd`.
- Private recovery manifest, schema revisions, source status and verification: `output/local-continuity/current/`.
- Uncommitted local Registry changes from the old source worktree outside OneDrive were separately preserved in `output/local-continuity/external-registry-local.zip` (7 source files, base commit recorded inside). This is recovery material, not the current main-checkout launcher or a database replacement.
- No push, deploy, production write, schema migration or account/grant change was performed for this continuity preparation.
