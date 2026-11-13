# CV Selection SP

**Status:** local prototype for Product Owner review (authorized 1 November 2026). Not merged, not deployed.
**SP** = Shelbi + Pino: one CV engine consolidating Selection's two CV analyses.

## Scope

Position → Upload CVs → Analyze → Ranking. The scope ends at the ranking: interviews, messages, appointments and
decisions stay in Selection and are not touched.

## What it does

| Step | Behavior |
|---|---|
| Position | Server or Line Cook. The role's profile (Shelbi, `Selection/workspace/position_profiles.py`) becomes the draft requirement list: one requirement per profile dimension, with criticality (weight ≥ 25 must-have, 10–15 preferred, else optional) and weight. The manager can change criticality and weight or add requirements, then **approves** them (versioned). |
| Upload | Many PDF (also scanned), DOCX or TXT files at once. Exact duplicates are skipped (Pino's content hash); same email or phone is reported as a possible duplicate. |
| Analyze | **One AI reading per CV** (AWS Bedrock, Selection's AI client), 3 in parallel, retrying when Bedrock throttles. |
| Ranking | Ordered list with group, relevant experience, demonstrated competences, red flags, points to verify and the reason for each position; ▲▼ to change the order; detail page and original CV. |

## Rules enforced by code (not by the AI)

- **Quotes** must be found word for word in the CV, otherwise discarded; a level without a verifiable quote is
  "not documented" (Pino's `evaluate_candidate` rule).
- **Skills list = claim:** evidence found only in a skills section is level 1 at most and a competence stays
  "claimed" (Shelbi's rule, enforced in code).
- **Dates** must be in the CV. When the AI gives none, the code reads them on the job's line. Durations, gaps and
  stability are computed (Pino's date normalizer, Shelbi's stability thresholds); year-only dates are a range,
  never an invented month; a job is current only when the CV says so.
- **Flags:** a flag stating a duration or gap written by the AI is dropped; a flag that only says something is
  not in the CV, or has no quote, becomes a point to verify; residence, commute and protected characteristics
  are never asked for and are dropped if they appear.
- **Missing ≠ negative:** "not documented" and "cannot be judged from a CV" stay separate from documented
  evidence against a requirement.
- Every correction is listed in the candidate's **verification log**; every analysis stores the prompt,
  profile and requirement versions and the model.

## Ranking

A motivated **preselection priority, not a validated prediction**; no number is shown as a probability, nobody
is excluded.

1. Manager's manual order, when set.
2. Group from the approved must-haves: **A** every must-have shown · **B** partly shown or to verify ·
   **C** a must-have not documented (to verify) · **D** documented evidence against a must-have.
3. Within a group: documented evidence weighted by the approved weights, as a share of what the CV can show.

Each candidate shows why they are ahead of the next one.

## Reuse (unchanged code)

| From | Used for |
|---|---|
| Pino — `RF-One Data Store/.../selection/parsing` | `text_extraction`, `dedup.compute_content_hash`, `flexible_dates.normalize_date_pair`, `ai_client` |
| Pino — `Selection/workspace/ai_adapter` | contact redaction, quote normalization, the "never use" list, the JSON retry note |
| Shelbi — `Selection/workspace` | `position_profiles` (Server, Line Cook), stability thresholds, `cv_reading._transcribe_transport` (scanned PDFs) |

Neither original engine is modified.

## Files

| File | Role |
|---|---|
| `app.py` | Flask routes and background analysis |
| `sp_profiles.py` | Profiles as approved requirements |
| `sp_analysis.py` | The single AI reading and its verification |
| `sp_timeline.py` | Verified dates, durations, gaps, stability |
| `sp_ranking.py` | Groups, order, reasons, manual order |
| `sp_store.py` | JSON storage per position (no new database) |
| `test_sp.py` | 34 checks, fake AI, temporary folder |

## Run and test

```
python app.py --port 5110        # http://127.0.0.1:5110/
python test_sp.py                # fake AI, no network
```

Data: `%LOCALAPPDATA%\RF-One\CV Selection SP` (outside OneDrive and Git). AI settings are read from Selection's
`%LOCALAPPDATA%\RF-One\Selection\ai.json`; AWS profile `rfone-dev-login` (needs a valid `aws login`).

## Known limits

- Levels are AI judgements within the code's rules; weights are Shelbi's draft values, not yet calibrated on real
  outcomes.
- Single local user, no RF-One login; English interface like Selection.
- Prototype storage: JSON files, not the RF-One database.
