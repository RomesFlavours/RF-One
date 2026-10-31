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
| From the CV: work history, positive evidence, hard requirements, cut-offs, risk flags and unknowns kept separate | Done |
| Recruiter priority High / Medium / Low over the proposed order | Done |
| AI Interview Requested, with confirmation, one email through the existing RMAED.it outbox, no duplicates | Done |
| AI interview on the candidate's link, then AI Interview Completed with the transcript | Done |
| Success and Failure case registry, matching patterns, rule approval UI, outcome feedback (phases 3 to 5) | Not started |

## 2. Files

| File | Change |
|---|---|
| `03 Software/Selection/workspace/position_profiles.py` | New. Server and Line Cook profiles: dimensions and draft weights, environment tables, flags, commute and hours bands, Mount Dora drive table. |
| `03 Software/Selection/workspace/profile_screening.py` | New. AI reading of the résumé, then code: quote check, stability from dates, score, commute, interview steps. |
| `03 Software/Selection/workspace/ai_interview.py` | New. Tables `selection_workspace_ai_interviews` and `selection_workspace_priorities`, invitation, conversation, public page. |
| `03 Software/Selection/templates/careers/ai_interview.html` | New. Candidate's interview page. |
| `03 Software/Selection/test_position_profiles_http.py` | New. 34 checks, synthetic data, fake AI, no email. |
| `workspace/engine.py` | `analyze` also runs the profile screening when the role has a profile; any failure there is logged and never loses the existing analysis. `current_proposals` gates it like the AI evaluation. |
| `workspace/routes.py` | Ranked list, priority route, AI Interview Requested route, template context. |
| `workspace/schema.py`, `workspace/__init__.py` | Provision the two new tables; register the public interview page. |
| `templates/workspace/position.html`, `candidate.html` | CV ranking table; From the CV panel; AI interview section with transcript. |
| `03 Software/Selection/README.md` | New section. |

Not changed: existing tables, the shared Alembic revision, the existing rule-based and AI evaluation, duplicate and
repeat-application handling, the apply link, the mail transport, the Aruba bridge, any other RF-One service.
Roles without a profile (for example Bartender) behave exactly as before.

## 3. How it works (facts)

- **The AI only reads.** It returns the work history, an evidence level 0–4 per dimension with quotes, flags,
  unknowns, stated hours and availability, and the home town. A reply that is not valid JSON is asked once more.
- **Code decides.** Quotes not found word for word in the résumé are dropped and their level becomes "not shown".
  Stability (short-job runs, job changes in 24 and 36 months, longest relevant tenure) is computed from the dates.
  The score is the weighted sum. Commute points: +5 (up to 20 min), 0 (up to 30), −5 (up to 44), −15 (45+).
- **Commute.** Minutes come from a table of nearby towns for Mount Dora; the AI's estimate is used only for towns not
  listed. Because no route is verified, 45+ minutes shows as "possible business cut-off, to confirm" and the CV fit
  label is not changed by it. The interview asks about the drive when it is unknown or over 30 minutes.
- **Order on the Evaluation tab:** priority (High, Medium, not set, Low), then score plus commute points. Hired and
  not-selected candidates leave the list.
- **AI Interview Requested:** offered only when the position is open, has a profile and the AI setting, the CV has
  been screened, the candidate is not hired or not selected, and there is a valid email. One confirmation, then one
  row in the existing outbox (source key `ai-interview:<id>`). A second or double click sends nothing.
- **The interview:** the link is the access, like the existing time-choice link. Nothing reaches the AI until the
  candidate presses Start, so mail link scanners start nothing. Steps: availability and hours, the commute when
  needed, up to 3 questions from the résumé (no near-duplicates), then the position's own questions (for Line Cook,
  the recipe/Legacy question). The server picks the next step and closes as soon as every step is answered, with at
  most 2 extra answers. Only the candidate's own words are kept as quotes. After the position closes or a final
  decision, the link says the interview is no longer open. The candidate can ask for a person by replying to the
  email (it comes from the same sender as the existing Selection emails).

## 4. Decisions taken in this build (interpretations)

| Topic | Choice | Why |
|---|---|---|
| Commute in the ranking | Points in the order; 45+ minutes is a point to confirm, not a cut-off | The owner wants locals ranked higher; the specification applies the 45-minute cut-off only after the drive is verified. |
| Drive times | Mount Dora town table first, AI estimate second | The AI put Leesburg at 45 minutes (about 25 in reality). |
| Where the person lives | Removed from the "never use" list for the screening and the interview only | Needed for the commute rule; the existing evaluation still excludes it. A test fails if that wording changes. |
| Priority not set | Between Medium and Low | New candidates should not sink below the ones marked Low. |
| Weights and thresholds | Exactly the draft values in the documents, labelled "Proposed, not yet approved" | Calibrate before approval (section 6). |
| Hard requirements | Shown as "none set in this profile yet" | The documents do not define any for these two profiles. |
| Interview length | At most 8 steps, plus 2 extra answers | A first run with 9 steps and 4 extras took 13 answers and repeated a question. |
| Interview text | Standard English invitation; the confirmation is the approval | One action, as the brief asks. |

## 5. Tests and success criteria

| Criterion | Outcome |
|---|---|
| Same engine, Server and Line Cook give different assessments | Pass (profile per role; Bartender keeps the existing screening only) |
| A flag can be traced to the résumé line or the dates | Pass (quotes shown; stability flags say "computed from the dates") |
| Unknown is never zero or a negative | Pass (stability unknown, hours unknown listed separately) |
| An odd or broken AI reply never breaks the existing analysis | Pass |
| One recruiter action, one email, no duplicates (also on a double click) | Pass |
| No invitation when it cannot work (no profile, AI off, not screened, closed, final decision) | Pass |
| Opening the link calls no AI; the interview closes on the answer that covers the last step | Pass |
| Interview completes and the transcript is visible | Pass |
| Existing Selection tests still pass | Pass: workspace HTTP (89), outcome workflow (13), Aruba bridge (9), acting identity (12) |
| Real AI check on fictional résumés and a fictional interview (Bedrock, Haiku 4.5) | Pass (section 7) |

## 6. Open points for the owner

1. **Success and Failure cases.** These need real employees' pre-hire CVs, outcomes and documented reasons, which is
   personal data, and with a few people per role they prove little. Proposal: start with a 30 and 90 day outcome note
   per hire and build the registry from that.
2. **Weights are hypotheses.** Proposal: Giovanna ranks 10 past CVs blind and we compare with the AI order before
   approving.
3. **Drive times.** The town table in `position_profiles.DRIVE_MINUTES` holds typical minutes to Mount Dora (Leesburg
   25, Eustis 12, Orlando 45, The Villages 38 and others). Someone at the restaurant should confirm them, above all the
   towns near 45 minutes.
4. **Commute and fairness.** Ranking by where people live can affect some groups more than others. Worth a quick check
   with whoever advises on hiring rules before it is used on real candidates.
5. **Mandatory Line Cook stations** for Mount Dora (section 15 of the Line Cook model) are still to be set.
6. **Response time.** The profile screening adds one AI call (11 to 16 seconds) per CV, in the same places as the
   existing AI evaluation, including when a candidate submits an application and when many CVs are re-analyzed.
7. **Deploy.** The two new tables are provisioned by `workspace/schema.py` (snapshot first, as for the outbox).
   The positions need "AI résumé and answer evaluation" on.

## 7. Real AI check

AWS Bedrock, Claude Haiku 4.5, temperature 0, Mount Dora position. Made-up résumés only, no real candidate data.

**CV screening** (11 to 16 seconds per résumé):

| Résumé | CV fit | Score | Commute | Notes |
|---|---|---|---|---|
| Marco (Line Cook) | Strong | 79 | Leesburg, 25 min | Sauté and pasta "owned"; grill and pizza only "claimed" in the skills list |
| Carla (Server) | Strong | 61 | Orlando, 45 min (to confirm) | 44 months at one restaurant; −15 for the drive puts her ranking at 46 |
| Tyler (Server) | Limited | 15 | Winter Park, 40 min | 4 jobs in a row under 6 months (computed from dates); not available Saturdays |
| Dana (Server) | Limited | 4 | Sanford, 35 min | No restaurant experience, no dates: stability shown as unknown, confidence Low |

**AI interview** (a second AI played Marco from his résumé): 7 steps, 7 answers, about 33 seconds of AI time in
total. Every step was answered, the interview closed on the last answer, and the commute was not asked (25 minutes).
On the recipe question Marco said he would raise ideas with the head chef after service.

Problems found and fixed during review:

| Problem (observed) | Fix |
|---|---|
| One reply was not valid JSON, so the résumé got no result | One retry with a note asking for valid JSON |
| The AI put Leesburg at 45 minutes, so Marco became a cut-off | Mount Dora town table, used before the AI estimate |
| "Jobs without usable dates" counted every job | Counting bug fixed; test added |
| An estimated 45+ minute drive was labelled a business cut-off | Now a point to confirm; points still apply |
| The interview repeated a question and needed up to 13 answers | At most 3 résumé questions, no near-duplicates; 2 extra answers |
| The interview needed one more message after the last step | Closes on the answer that covers the last step |
| The 20-minute limit counted from when the link was first opened (a mail scanner could trigger it) | Limit removed; the AI starts only on Start |
| The invitation could be sent with AI off, after a final decision or on a closed position | Refused, and the button is not shown |
| A double click could show an error page | Handled: "already requested", one email |
| An odd AI reply could stop the existing analysis from being saved | Screening failures are logged; the existing analysis is always saved |

Interpretation: the order matched what a manager would expect, the flags trace to the dates or to quotes, and no
quote had to be dropped. Four résumés and one interview prove the flow works, not that the weights are right
(section 6).

## 8. References

- Branch `shelbi/selection-position-profiles`; base `release/selection-complete-20261030` (`2d85435`).
- Test: `python test_position_profiles_http.py`.
- Specifications: RF1_Selection_Position_Specific_Standards_for_Shelbi.md, RF1_Server_CV_Preselection_Model_v1_EN.md,
  RF1_Line_Cook_CV_Preselection_Model_v1_EN.md, RF1_Selection_System_Changes_for_Shelbi_v2_EN.md (31 October 2026).
