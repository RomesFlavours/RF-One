# REPORT: SELECTION_POSITION_PROFILES_001

Position-specific CV screening, recruiter priority and the AI interview invitation.
Branch `shelbi/selection-position-profiles`, from `release/selection-complete-20261030`. For review: nothing is
deployed, merged or sent.

## 1. What was asked

From "Position-Specific Standards", the Server and Line Cook "AI CV Preselection Model v1.0" and "System Changes v2"
(31 October 2026): the first part of the flow, up to sending the email.

| Step | Status |
|---|---|
| One engine, a profile per position (Server, Line Cook) | Done |
| Ranking that keeps positive evidence, cut-offs, risk flags and unknowns separate | Done |
| Recruiter priority High / Medium / Low over the proposed order | Done |
| AI Interview Requested, with confirmation, one email through the existing RMAED.it outbox, no duplicates | Done |
| AI interview on the candidate's link, then AI Interview Completed with the transcript | Done |
| Success and Failure case registry, rule approval UI, outcome feedback (phases 3 to 5) | Not started |

## 2. Files

| File | Change |
|---|---|
| `03 Software/Selection/workspace/position_profiles.py` | New. Server and Line Cook profiles: dimensions and draft weights, environment tables, flags, commute and hours bands. |
| `03 Software/Selection/workspace/profile_screening.py` | New. AI reading of the résumé, then code: quote check, stability from dates, score, commute, cut-offs, interview steps. |
| `03 Software/Selection/workspace/ai_interview.py` | New. Tables `selection_workspace_ai_interviews` and `selection_workspace_priorities`, invitation, conversation, public page. |
| `03 Software/Selection/templates/careers/ai_interview.html` | New. Candidate's interview page. |
| `03 Software/Selection/test_position_profiles_http.py` | New. 30 checks, synthetic data, fake AI, no email. |
| `workspace/engine.py` | `analyze` also runs the profile screening when the role has a profile; `current_proposals` gates it like the AI evaluation. |
| `workspace/routes.py` | Ranked list, priority route, AI Interview Requested route, template context. |
| `workspace/schema.py`, `workspace/__init__.py` | Provision the two new tables; register the public interview page. |
| `templates/workspace/position.html`, `candidate.html` | CV ranking table; From the CV panel; AI interview section with transcript. |
| `03 Software/Selection/README.md` | New section. |

Not changed: existing tables, the shared Alembic revision, the existing rule-based and AI evaluation, the apply
link, the mail transport, the Aruba bridge, any other RF-One service.

## 3. How it works (facts)

- The AI only reads. It returns the work history, an evidence level 0–4 per dimension with quotes, flags, unknowns,
  stated hours and availability, home town and a rough drive time. If the reply is not valid JSON, it is asked once
  more with a short note (temperature 0 would otherwise repeat the same reply).
- Code decides: quotes not found word for word in the résumé are dropped and their level becomes "not shown";
  stability (short-job runs, changes in 36 months, longest relevant tenure) is computed from the dates; the score is
  the weighted sum; commute adds +5 (0–20 min), 0 (21–30), −5 (31–44), −15 and a visible business cut-off (45+).
  The minutes come from a table of nearby towns for Mount Dora; the AI's estimate is used only for towns not listed.
- Order on the Evaluation tab: priority (High, Medium, not set, Low), cut-offs last within each priority, then score.
- AI Interview Requested: confirmation, then one row in the existing outbox with source key `ai-interview:<id>`.
  A second click finds the interview and sends nothing. No valid email: nothing is created.
- The interview: availability and hours first, commute when unknown, the résumé's questions, the position's own
  questions. The server picks the next step and closes after every step is covered, 4 extra answers, or 20 minutes.
  Only the candidate's own words are kept as quotes. The candidate can ask for a person by replying to the email.

## 4. Decisions taken in this build (interpretations)

| Topic | Choice | Why |
|---|---|---|
| Commute in the ranking | Points and a cut-off flag, from a town table for Mount Dora, then the AI's estimate | The owner wants locals ranked higher. The AI put Leesburg at 45 minutes, so known towns use the table. Labelled approximate; nobody is excluded. |
| Where the person lives | Removed from the "never use" list for the screening and the interview only | Needed for the commute rule; the existing evaluation prompt still excludes it. |
| Priority not set | Between Medium and Low | New candidates should not sink below the ones marked Low. |
| Weights and thresholds | Exactly the draft values in the documents, labelled "Proposed, not yet approved" | Calibrate against real outcomes before approval. |
| Interview text | Standard English invitation; the confirmation is the approval | One action, as the brief asks. |

## 5. Tests and success criteria

| Criterion | Outcome |
|---|---|
| Same engine, Server and Line Cook give different assessments | Pass (unit + profile per role; Bartender keeps the existing screening only) |
| A flag can be traced to the résumé line or the dates | Pass (quotes shown; stability flags say "computed from the dates") |
| Unknown is never zero or a negative | Pass (stability unknown, hours unknown listed separately) |
| One recruiter action, one email, no duplicates | Pass |
| Interview completes and the transcript is visible | Pass |
| Existing Selection tests still pass | Pass: workspace HTTP, outcome workflow, Aruba bridge, acting identity |
| Real AI check on fictional résumés (Bedrock, Haiku 4.5) | Pass after three fixes (section 7) |

## 6. Open points for the owner

1. **Success and Failure cases.** These need real employees' pre-hire CVs, outcomes and documented reasons, which is
   personal data, and with a few people per role they prove little. Proposal: start with a 30 and 90 day outcome note
   per hire and build the registry from that.
2. **Weights are hypotheses.** Proposal: Giovanna ranks 10 past CVs blind and we compare with the AI order before
   approving.
3. **Drive times.** The town table in `position_profiles.DRIVE_MINUTES` holds typical minutes to Mount Dora (Leesburg
   25, Eustis 12, Orlando 45, The Villages 38 and others). Someone at the restaurant should confirm them, above all the
   towns near 45 minutes, where the cut-off falls.
4. **Mandatory Line Cook stations** for Mount Dora (section 15 of the Line Cook model) are still to be set.
5. **Deploy.** The two new tables are provisioned by `workspace/schema.py` (snapshot first, as for the outbox).
   The positions need "AI résumé and answer evaluation" on to use the profile.

## 7. Real AI check

AWS Bedrock, Claude Haiku 4.5, temperature 0. Three made-up Server résumés and one made-up Line Cook résumé, Mount
Dora position. No real candidate data. 11 to 16 seconds per résumé.

| Résumé | Fit | Score | Commute | Notes |
|---|---|---|---|---|
| Carla (Server) | Cut-off | 61 | Orlando, 45 min | Strong résumé, 44 months at one restaurant; the cut-off is the drive only |
| Dana (Server) | Limited | 4 | Sanford, 35 min | No restaurant experience, no dates: stability shown as unknown, confidence Low |
| Tyler (Server) | Limited | 15 | Winter Park, 40 min | 4 jobs in a row under 6 months (computed from dates); not available Saturdays |
| Marco (Line Cook) | Strong | 79 | Leesburg, 25 min | Sauté and pasta "owned"; grill and pizza only "claimed" in the skills list |

Problems found and fixed during the run:

| Problem (observed) | Fix |
|---|---|
| One reply was not valid JSON (a quote mark inside a string), so the résumé got no result | One retry with a note asking for valid JSON |
| The AI put Leesburg at 45 minutes (about 25 in reality), so Marco became a cut-off | Town table for Mount Dora, used before the AI estimate |
| "Jobs without usable dates" counted every job, dated or not | Counting bug fixed; test added |

Interpretation: the order matched what a manager would expect (Marco and Carla well ahead of Dana and Tyler), the
flags trace to the dates or to quotes, and no quote had to be dropped. Four résumés prove the pipeline works, not
that the weights are right (see section 6).

## 8. References

- Branch `shelbi/selection-position-profiles`; base `release/selection-complete-20261030` (`2d85435`).
- Test: `python test_position_profiles_http.py`.
- Specifications: RF1_Selection_Position_Specific_Standards_for_Shelbi.md, RF1_Server_CV_Preselection_Model_v1_EN.md,
  RF1_Line_Cook_CV_Preselection_Model_v1_EN.md, RF1_Selection_System_Changes_for_Shelbi_v2_EN.md (31 October 2026).
