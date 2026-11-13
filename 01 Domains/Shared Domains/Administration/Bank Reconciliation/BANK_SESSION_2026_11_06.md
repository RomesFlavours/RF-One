# Bank decisions and handoff for 6 November 2026

Read this note when the Product Owner asks to resume or recall today's Bank work. Working version: BANK-2026-11-04, port 5104. This records the conversation and received reports; it is not certification of the whole application.

The Product Owner closed today's rule discussion with: “OK basta così per le regole, mi stanno bene.” Record the current agreement and stop expanding the task. This is not permission to activate rules, rewrite data, or implement pending ideas automatically.

## 1. Agreed Bank workflow and layout

Tabs, left aligned: Pannello, Carica e riconcilia, Riconcilio, WHO, WHY, Configurazioni. Contextual How Works stays at the right. Monthly export belongs at the bottom of Pannello; Ripartizioni belongs in WHY; Conti e carte belongs in Configurazioni. Blue programming information panels were requested removed.

Section ovals are bookmarks; sections have a return-to-top arrow. Configuration sections start collapsed and load when opened. Local UI and help are Italian.

Riconcilio filters share one row: year, month, account, filter, search text, search. Open movements have one action, Completa, now in the first column. The system determines what is missing and presents the relevant operation in the same completion journey. Closed rows were explicitly left outside that layout change.

Completa is accessible from a movement and automatically at the end of the user-started reconciliation process when cases remain. It must not start reconciliation itself or require all exceptions to be solved before already-resolvable work proceeds. Current-movement confirmation, application to other movements and saving a future criterion are separate choices. Protected human decisions remain protected.

## 2. WHO to WHY configuration

One configuration per WHO, not one per card: one WHY, personal/company WHY, or conditional rule. Personal/company and the specific company come from account/card ownership at the movement date; unknown ownership is not automatically company ownership. Company exceptions take precedence over the configured behavior. WHOM normally follows ownership, with explicit exceptions; WHAT derives from WHY.

C reported conversion of 221 WHO: 115 grouped (19 single WHY, 96 personal/company), 99 without WHY, 7 requiring decisions. These are reported conversion counts, not a new live audit. The seven are ADP WAGE PAY, ABC, ALIBABA, ALIPAYUSINC, CHASE, PUBLIX and COMPANY CAR. Same-company differences may need contextual conditions rather than another card-specific row.

AI-assisted initialization from business-specific accounting templates and logical WHY remains deferred. First stabilize Bank's current workflow. Period P/L and print/PDF remain on the backlog; no implementation was verified here.

## 3. Pattern discovery comes before user explanation

The user should not have to discover recurring description formats or teach the AI their delimiters from scratch. Start from original descriptions, independently of existing WHO rules. Find stable structures and variable fields, count groups and sort largest first. Subfamilies are included in parent totals, never counted again in coverage.

Independent read-only analysis of 3,299 records found:

| Result | Groups | Records |
|---|---:|---:|
| Variable formats | 41 | 2,652 |
| Identical repeated descriptions | 85 | 514 |
| Residuals | One residual bucket, not a format | 133 |

Thus 126 recurring groups cover 3,166 records, but only 41 are variable-format families. Residual does not mean unrecognizable. Format coverage does not mean correct WHO recognition.

Major families: ACH 901, Zelle 681, online transfers 180, POS SIG 157, PURCHASE 115. ACH has 42 origin-company subfamilies, including PayPal with 81 records. Independent artifacts are in `C:/Users/servi/OneDrive/Documents/ChatGPT/RF1 Sviluppo/output/WHO-Formati/` (`analyse.py`, `analysis.json`, `index.html`). The final standalone HTML is a simple white listing with structures, examples and subfamily counts, without JavaScript dependency. Re-running analyse.py currently regenerates the earlier interactive template; preserve the final simple listing if regenerating.

C reports the new `/bank/who-training` page: Cerca pattern recalculates from live original descriptions, lists 126 recurring groups, and Definisci regola opens the existing editor with group context. Opening 16 pattern/subfamily buttons was reported tested. Code: `bank_who_patterns.py`, `who_patterns.js` and existing training/editor files.

## 4. AI rule proposal on opening the editor

Definisci regola must immediately analyze the selected pattern's structure, diverse examples and subfamilies, using the existing AI consent. It proposes the extraction itself and asks only about concrete ambiguity. Keep a complete original example at the top, show applicability/exclusions, proposed rule and description-to-extracted-WHO simulation. The person can correct in chat, simulate and explicitly save. No automatic creation/activation from discovery or analysis.

Approved concrete extraction:

- Ordinary ACH candidate: between `ORIG CO NAME:` and `ORIG ID:`.
- PayPal purchase/merchant-bearing variant: between `IND ID:` and `IND NAME:`; PAYPAL is the intermediary.
- When analyzing the whole ACH family, identify the PayPal exception and propose a generic rule excluding the relevant PayPal format plus a specific rule. Do not blindly assume every PayPal record contains a merchant there (section 6).
- Normalization: trim only leading/trailing spaces and uppercase. Preserve digits, special characters and internal spaces. Earlier wording about deleting numbers/special characters was incorrect.

C reports actual ChatGPT trials for PayPal and full ACH, plus save/activation on an isolated copy. `bank_who_pattern_analysis.py` was added. Correction through chat and Save-and-apply-to-existing were explicitly NOT tested. At that report, working rules #114 and #121 were still old and overlapping. Do not claim the live conflict has disappeared without checking.

Earlier command also requested user-controlled WHO rule priority and conflict detection before activation: simulate against existing rules; flag differing WHO outputs; let the user resolve placement before activating the new version; first applicable rule with a valid extraction wins, empty extraction falls through, human choices stay protected. Do not extend this to WHY rules. Completion of the priority interface/engine has not been verified. Explicit exclusion of PayPal from generic ACH addresses the concrete overlap without relying on a hidden priority.

## 5. Latest occurrence-window request supersedes earlier inline plans

The user rejected putting a large occurrence list inside Definisci regola. The latest request is a second independent, movable window that can be placed alongside the rule editor, opened from that editor. Both must remain usable so occurrences stay visible while the rule is developed. Earlier commands for an inline list or a window opened from the pattern name are superseded.

Keep the requested first 50 occurrences, most recent first, date/account/full original description and Show all. A subfamily shows only its own records. Preserve editor conversation, proposal and unsaved changes.

The assistant proposed resizable windows and simulation colors: green valid extraction (not human approval), yellow doubtful/conflicting, red applicable but failed/empty extraction, white not applicable. Results belong to the latest simulation; changing the draft makes them stale until resimulation. These color meanings are a proposal responding to the user's color request, not a verified implementation. No completion report or new consolidated implementation command for the separate window was received.

## 6. Cross-field simulation for uncertain WHO

The user proposed comparing ORIG CO NAME, CO ENTRY DESCR, IND ID and IND NAME using the whole description rather than trusting one field. A direct read-only check of all 81 ACH PayPal movements produced:

| Observed variant | Count | Proposed interpretation |
|---|---:|---|
| PAYPALSI77 / PURCHASE / textual IND ID | 45 | Merchant candidate from IND ID |
| PAYPALSI77 / INST XFER / textual IND ID | 29 | Merchant candidate from IND ID, despite transfer wording |
| PAYPALSD11 / TRANSFER / numeric IND ID | 5 | Numeric identifier is not a WHO name |
| PAYPALSD11 / TRANSFER / empty IND ID | 2 | No WHO available in IND ID |

All seven PAYPALSD11 records are incoming. IDs: 1663, 2235, 2725, 2727, 2729, 2748, 2752. The previous report's “seven numeric” is corrected to five numeric and two empty. “79 extracted” includes numeric identifiers and is not 79 valid WHO identifications.

For the 74 textual cases, examples include GOOGLE LUXY LIM, JETBLUEAIRW 081, LOWES.COM and SHEINUSSERV. For the seven incoming cases, the assistant proposed PAYPAL as the immediate counterparty candidate, while keeping economic origin/purpose unresolved. GIUSEPPE MIRAGLIA in IND NAME is not automatically selected just because it is a person's name. The description alone does not prove balance withdrawal, refund or ultimate sender. This was the assistant's reasoning over actual records, not a test or implementation of the in-app AI. No WHY, transaction or rule was changed.

The Product Owner accepted stopping the rule discussion here. Preserve the distinction between an accepted analysis direction, a proposal and an activated rule. Check/beneficiary disambiguation was explicitly deferred; a CHECK number alone does not supply its payee.

## 7. Remaining verification and tomorrow's recall

- Whole-Bank audit is incomplete. Computer Use stopped because it could not confidently determine Edge's URL; do not describe the application as independently verified end-to-end.
- C reports duplicate verdicts, transfer matching and WHOM inside Completa. Reported missing currencies on 13 of 14 instruments block real matching; no bulk currency assumptions were authorized.
- Remaining audit concerns: completion of relationship-between-owners cases, marking a record Done before rereading all outstanding issues, preservation of explicit exception WHOM on bulk application, and the untested visible WHOM path. These are pending checks, not all established defects.
- Pattern AI correction in chat and applying to existing movements are not verified. Separate occurrence-window/color implementation is not verified. WHO priority completion is not verified.
- On a future status request, include outstanding tasks with three descriptive lines each, using BANK_BACKLOG.md. Do not turn this handoff into authorization for additional work. Ask the user what to resume when no new task is given.

## References

- [Bank backlog](BANK_BACKLOG.md)
- [Earlier final WHO/WHY direction](BANK_WHO_WHY_FINAL_LOGIC_001.md) — some layout/status passages are older; this dated handoff records later conversation decisions without claiming all were implemented.
- User-pasted latest AI-analysis report: `C:/Users/servi/.codex/attachments/7d93cc46-55eb-441e-934e-0e78d42d9d1e/Testo incollato.txt`.
- Working code: `C:/Users/servi/OneDrive/AI-RF-ONE/BANK-2026-11-04/03 Software/RF-One Web/`.
- Working database: `%LOCALAPPDATA%/RF-One/BANK-2026-11-04/rfone.db`.
