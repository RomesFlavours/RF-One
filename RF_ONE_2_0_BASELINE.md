# RF-One 2.0 — Clean Baseline Manifest

**Baseline name:** RF-One 2.0
**Branch:** `release/rf-one-2.0`
**Core tag:** `core-2.0-freeze` → commit `71de3663dba2716ccbb6c1f93ffd458e20da8ead` ("RF-One Core 2.0 freeze")

This is a factual manifest of what this branch contains and how it was built — not itself canonical architecture (see `00 Core/Core Evolution.md`) and not a replacement for `PROJECT_STATE.md`.

---

## Composition

Built by cherry-picking, in this order, onto `core-2.0-freeze`:

| # | Commit (origin) | Subject |
|---|---|---|
| 1 | `d8a3fc7921963d45b9b9dec2cd302252804e4ff3` | RF-One 2.0 organizational responsibility and attention runtime |
| 2 | `177094d6b964b69a8916fecb3ef1c6323767744e` | RF-One organizational chart configuration |
| 3 | `f9ce9cbaafda4ccee830a89e8b9cacd288e49e99` | RF-One organizational runtime consistency fixes |
| 4 | `c5a33343b2895251f986a3e5e0a574905a80b2c8` | Reconstruct Selection/Pills documentation after working-tree loss |
| 5 | `8eb2c5a072f2a30f20460e4d5572805f6389e7e0` | RF-One Tips Core 2.0 process-first pilot |

Commits 1–4 were already linear (branch `review/attention-org-runtime`). Commit 5 (`review/tips-core2-pilot`) diverged independently from `core-2.0-freeze` and was cherry-picked last; the only conflict was a duplicate `.gitignore` comment (both branches independently added the same `Secrets/` ignore rule) — resolved by keeping one copy of the rule. `models.py` merged additively with no conflict.

**Plus, added directly to this baseline (previously untracked in the working copy, never committed on any branch):**

- `00 Core/ConceptualArchitecture/20_RF-One_Selection_Pills_Cognitive_Model.md` — **required**: already referenced by `00 Core/README.md` and `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md` **at the `core-2.0-freeze` commit itself** (i.e. Core 2.0, as frozen, already pointed to a file that had never been committed). Content verified (documentation only, no secrets); added as-is.
- `01 Domains/Cross Domain/Selection/SELECTION_PILL_ASSESSMENT_AND_TRAINING_READINESS_001.md` and `01 Domains/Cross Domain/TRAINING_SERVICE_001.md` — **required**: both are referenced by all six of the just-reconstructed Selection/Pills documents (commit 4). Without them, the baseline would ship canonical documents with broken cross-references. Content verified (documentation only, no secrets); added as-is.
- `03 Software/RF-One Data Store/migrations/versions/09ed62634a09_merge_rf_one_2_0_heads_organizational_.py` — **required**: an empty Alembic merge migration reconciling the two heads that combining commits 1–4 and 5 produces (`749a28964701` and `efe49dbc7321`, both descending from `f7174fa37e93`). No schema change; `upgrade()`/`downgrade()` are no-ops. Without it, `alembic upgrade head` is ambiguous.

---

## Capabilities included (IMPLEMENTED)

- **Organizational Responsibility + Attention Management** — Position/Scope/Occupant/Temporary Coverage/Backup Position/Organizational Fallback Policy, cross-Domain Attention Items with priority/routing/resolution history. Admin/config/test UI only (no end-user Attention Inbox). 20/20–49/49 relevant checks passing (see Test Results below).
- **Organizational Chart Admin Page** — position editor, AI-assisted review, coverage-check tooling.
- **Tips Core 2.0 process-first pilot** — Trigger/Readiness → Distribution Engine (unchanged, pre-existing, deterministic) → Payment Instruction → Mercury Sandbox Connector → Outcome Verification. Sandbox-only; no production Mercury endpoint or token in code (`MERCURY_SANDBOX_API_TOKEN` from environment only).
- **Selection / Pills / Training Service documentation** — Selection Guidability/Training Handoff, Pill Assessment & Training Readiness, Training Service boundary (internal RF-One service, not a Cross Domain), Operational Knowledge and Continuous Productivity Development boundaries, Person Continuity — reconstructed after an accidental working-tree loss; see commit 4 and its own recovery notes for provenance/confidence per file.

## FUTURE / NOT IMPLEMENTED

- End-user Attention Inbox (only admin/config/test surfaces exist).
- Cognito / mobile identity integration (not required by this baseline; existing Identity & Access work remains frozen, unaffected).
- Guidability formal scoring, Training curriculum/quiz-to-1-5-scale conversion, AI scoring authorization — all explicitly left open by the Selection/Pills documents themselves.
- Physical reorganization of `Operational Knowledge` / `Continuous Productivity Development` folders to more directly reflect the Training Service functional boundary (deliberately deferred by `TRAINING_SERVICE_001.md` itself).
- **FUTURE / CONCEPTUAL EXTENSION — Human Operational State and Adaptive Cognito Interaction.** Documented, post-baseline, at `00 Core/ConceptualArchitecture/15_Human_Operational_State_and_Adaptive_Cognito_Interaction.md` (status: APPROVED — Post-Baseline Conceptual Extension, ratified by the Product Owner; still not part of the Approved 00–14 canonical set and not retroactively part of `core-2.0-freeze` — see `00 Core/Core Evolution.md`). No software, database, wearable, sensor, or diagnostic algorithm exists for this in this baseline or any other branch; documentation only.
- **FUTURE / CONCEPTUAL EXTENSION — Ambient Operational Context and In-Flow Cognito Assistance.** Documented, post-baseline, at `00 Core/ConceptualArchitecture/16_Ambient_Operational_Context_and_In-Flow_Cognito_Assistance.md` (status: APPROVED — Post-Baseline Conceptual Extension, ratified by the Product Owner; still not part of the Approved 00–14 canonical set and not part of `core-2.0-freeze` — see `00 Core/Core Evolution.md`). Recognizes the Restaurant Domain's existing Service Copilot module as this concept's first Domain-level consumer instance — a documentation-only recognition, not a change to Service Copilot's own approved content or functional behavior. No microphone capture, speech-to-text, transcription, audio streaming, earbud protocol, or surveillance capability exists for this in this baseline or any other branch; documentation only.
- **FUTURE / CONCEPTUAL EXTENSION — Visual/Video Context as Ambient Evidence.** Documented, post-baseline, at `00 Core/ConceptualArchitecture/17_Visual_Video_Context_as_Ambient_Evidence.md` (status: PROPOSED — Post-Baseline Conceptual Extension, a sub-extension of document 16, not yet ratified; not part of the Approved 00–14 canonical set and not part of `core-2.0-freeze` — see `00 Core/Core Evolution.md`). Documents authorized images/video as one source category of Ambient Operational Context (scene-level Ambient Evidence only, never automatic Fact, never a judgment about a person). No computer vision model, video ingestion, camera stream, image storage, object detection, face recognition, biometric identification, or emotion recognition exists for this in this baseline or any other branch; documentation only.

## Known non-blocking open items

- `01 Domains/Domain Architecture.md` contains two pre-existing dangling links to `07 Tasks/TASK_DOMAINS_001...` / `TASK_DOMAINS_002...`, already present at `core-2.0-freeze`. Out of scope here (Domain Architecture is not modified by this baseline); flagged for a future documentation task.
- `07 Tasks/Reports/` accumulates task reports linearly; no reorganization performed as part of this baseline.

---

## How to rebuild the database from this branch

```
cd "03 Software/RF-One Data Store"
alembic upgrade head
```

Verified against a fresh SQLite database with no manual intervention (single head after the merge migration above).
