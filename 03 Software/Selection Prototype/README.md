# Selection AI — local prototype (first release)

A local, simplified Selection organized by **open positions**. One position page holds the five functions:
**1 Position** (requirements, headcount, English job ad, standard interview questions, approval) ·
**2 Applications** (public page with résumé + short English interview, resumable; manual multi-upload) ·
**3 Evaluation** (three proposal groups with verifiable evidence; side-by-side comparison) ·
**4 Interviews** (phone or in person; direct booking or a link offering times; internal calendar) ·
**5 Decisions** (hired / not selected / on hold; English messages approved by the manager; history; manual close).

It does **not** modify `03 Software/Selection/` and is never deployed.

## What it reuses

| Need | Existing component reused |
|---|---|
| CV text extraction, parsing, normalization, duplicate document check | `selection/import_pipeline.py`, `parsing/*` |
| Person resolution, same-person and name-match suggestions | `application_service.py`, `identity_service.py` |
| Requirements, versioned approval (snapshots), templates | `requirements_service.py`, `restaurant_templates.seed_sample_templates` |
| Evidence per requirement from the CV | `fit_assessment_service.py`, `resume_evidence_matcher.py` |
| Indicators, flags, interview questions | `analysis.analyze_candidate` |
| Standard interview questions | `phone_interview_service` question definitions (`seed_romes_flavours_phone_interview_questions`) |
| Accounts, login, session revocation, Domain rule, CSRF | `rfone_account_service.py`, `rfone_web_session.py` (Domain `SELECTION`) |
| Local time display | `display_format.local_datetime` |
| AI | `parsing/ai_client.generate_json`, only through `ai_adapter.py` |

Prototype-only tables (`selproto_*`) are created with `create_all` in the prototype's own database; they are not part
of the Alembic chain. The proposal group is computed by one transparent rule from requirement statuses (no new
scoring engine); nobody is excluded automatically; missing information is never read as a negative.

## Data

`%LOCALAPPDATA%\RF-One\SelectionPrototype\` (outside OneDrive and Git): `selection_prototype.db`, `documents\`
(original CVs), `secret.key`. Override with `RFONE_SELECTION_PROTOTYPE_DATA`. `RFONE_DATABASE_URL` is forced to this
file for the process; no other database is written.

## AI permissions

| Start | Effect |
|---|---|
| `python app.py` | No AI. Rule-based CV reading and existing engines; standard English message templates. |
| `python app.py --ai` | AI drafts the position (requirements, headcount, English ad) and candidate messages. No candidate data is sent: messages use placeholders filled locally. |
| `python app.py --ai-cv` | Explicit authorization only: AI also reads CVs and answers (follow-up interview questions, evaluation with quotes verified verbatim). |

Selection's import chain tries AI parsing first whenever a provider is configured (the repo-root `.env` configures
AWS Bedrock). `ai_adapter.install_guard` replaces, in this process only, the function the CV parser calls, so without
`--ai-cv` no CV is sent anywhere. `ai_adapter._transport` is the single seam for RF-One's future central AI service;
`organization_adapter.py` (read-only, `RFONE_SELECTION_PROTOTYPE_ORG_DB`) plus the owner-written company profile are
the company facts the AI may use — missing facts are reported, never invented.

## Not automated (by design for this release)

Sending email/SMS (approved messages are copied), Indeed integration (the public page carries schema.org
`JobPosting` data and can be used as an "Apply on company site" link), external calendars, links to Training,
Management or Organization after hiring. The public pages bind to 127.0.0.1: Internet exposure needs separate
authorization.

## Run and test

`Avvia Selection Prototipo.cmd` (starts with `--ai`), or `python app.py [--port 5095] [--ai] [--ai-cv]`, then
http://127.0.0.1:5095/. The first visit creates the owner account. Smoke test of the whole path (synthetic data,
throwaway folder, no AI provider reachable, fake AI for the AI branch): `python test_prototype_smoke.py`.
