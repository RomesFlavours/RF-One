# Manual reconciliation: WHO + WHY, and the Rule

**Task:** BANK_MANUAL_WHO_WHY_001 (Product Owner correction to the Review workflow)
**Status:** Implemented on `feature/bank-simple-who-rules` — service, routes, popup, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration.
**Builds on:** BANK_TWO_STAGE_REVIEW_001 (To Reconcile / Reconciled), BANK_SIMPLE_WHO_RULE_001 (the Rule).

---

## Two row actions, two meanings

| Action | Meaning | Writes |
|---|---|---|
| **Select WHO** | Reconcile THIS transaction by hand: its WHO **and** its WHY | one HUMAN decision for the transaction (`manual_reconciliation.reconcile_who_why`) |
| **Rule** | Teach recognition: description text → WHO | a WHO-only recognition rule, applied to every matching transaction, now and on future imports (`who_rules.apply_who_rule`) |

A Rule never chooses a WHY. The possible WHY ticked in the Rule modal are WHO → WHY associations only.
Manual reconciliation never creates a Rule and never learns a description.

## "Select WHO / WHY" popup

> **Since BANK_WHY_NAVIGATION_GROUPS_001** the popup has three columns — WHO | WHY GROUP | WHY — and
> **any active WHY** can be chosen for any WHO (the WHO's own WHY are only marked; Confirm adds the missing
> association). A new WHY needs a group. See `BANK_WHY_NAVIGATION_GROUPS_001.md`; the description below is
> the original two-step popup.

One popup (`_bank_who_why_modal.html`, `static/js/bank-who-why.js`), used on To Reconcile and on Reconciled:

1. compact transaction description;
2. **WHO**: search and a scrollable list of every ACTIVE WHO, alphabetical; an empty search shows the
   full list; aliases are searchable, selection is always the canonical WHO;
3. **WHY** (after a WHO is chosen): the WHY currently available for that WHO, and **+ Create New WHY**.
   A WHY is never selected for the operator, not even when the WHO has only one;
4. **Confirm** (enabled only with one WHO and one WHY) and **Cancel**.

Removed from the popup: WHAT choice, For Whom, *Learn this description*, the Rule shortcut, Standard
controls and the WHO → WHY → WHAT explanations.

Loading is on demand (no WHO × WHY matrix in the page): the WHO list once per page
(`GET /bank/manual-reconciliation/whos`), the WHY of the chosen WHO
(`GET /bank/manual-reconciliation/whos/<id>/whys`), and the WHY groups, P&L WHAT and existing WHY names
when Create New WHY is first pressed (`GET /bank/whys/create-options`).

## Create New WHY (BANK_CREATE_NEW_WHY_SHARED_001, 2026-10-05)

**One flow for both reconciliation modals** — Select WHO / WHY and the WHO Rule modal — so the operator
never leaves reconciliation because a WHY is missing. One dialog (`_bank_why_create_dialog.html` +
`bank-why-create.js`, included once per page after the modals), one route (`POST /bank/whys/create`),
one service (`manual_reconciliation.create_why_for_who`). The dialog opens **on top of** the modal that
launched it and closes back to it — no navigation, no reload; Cancel / Escape change nothing.

| Field | Rule |
|---|---|
| WHY Name | required; spaces trimmed; an active WHY with the same name (case and spacing ignored) is **reused**, never duplicated — "Existing WHY found — reused." (group and WHAT are then not asked) |
| WHY Group | required for a new WHY; `BankReasonGroup`, alphabetical; the group selected in the modal is preselected |
| WHAT / accounting destination | required for a new WHY; searchable; a **P&L WHAT**, exactly as Bank Configuration requires (`configuration.create_why`, decision D11 — a Balance Sheet destination is refused) |

Save, in ONE database transaction (committed whole or rolled back whole — no WHY without group or WHAT,
no half association): the WHY is created by `configuration.create_why` (or the existing one reused) and,
when the modal has a WHO, added to that WHO (`why_catalog.associate`, only if missing).

* **Select WHO / WHY:** the WHY comes back **selected**, in its group, marked *used with this WHO*;
  Confirm then records it for the transaction as before (`reconcile_who_why`). Confirm still accepts a
  WHY name (`new_why_*`) and creates/reuses it through the same `_create_or_reuse_why`.
* **WHO Rule:** the WHY appears in its group, in alphabetical place (the group is added if it had no
  WHY to show), **ticked as a Possible WHY**; the WHO, the Rule sentence and the other ticks are kept.
  It stays a WHO association only: Apply never gives a WHY to a transaction. For a WHO still to be
  created by Apply, the WHY is created now and associated by Apply.

## Confirm

`POST /bank/transactions/<id>/who-why` → `reconcile_who_why` → `row_reconciliation.record_who`: the HUMAN
decision of the Reconciliation rows. WHAT is derived from the WHY. A row that changes loses its
acceptance (Needs review until confirmed again). The transaction leaves To Reconcile and appears in
Reconciled; For Whom and the status stay truthfully visible there.

## Reconciled

In Review > Reconciled each row shows Account/Card, Date, Description, Amount, **WHO**, **WHY**,
**WHAT**, For whom and Status. WHY (and WHO) are edited from the row with the same popup, WHO and WHY
preselected; changing the WHO refreshes the WHY list, and a WHY that is not the new WHO's is refused.
A Rule-resolved row with no WHY says *WHY needed* and stays in Reconciled.

The month page `/bank/reconciliation` keeps its approved compact row (BANK_RECONCILIATION_001: WHAT not
on the compact row) and its own WHO modal.

## The TABLE TOP LINEN finding

The rule chain (BankRecognitionRule → recognition / CanonicalWhoResolver → current decision →
`review_queues`) was verified correct on a production-shaped copy: one Rule "description contains
TABLE TOP LINEN → WHO TABLE TOP LINEN" gives the WHO to all 43 matching transactions across every
month, and to future imports, without a WHY. On the review server no Rule had been saved: Apply never
reached the server. The Rule sentence field carried the HTML `required` attribute, so an empty sentence
was blocked by the browser's own bubble instead of the modal's message. The attribute is removed (the
modal's *Write the rule.* message shows), and choosing a WHO proposes an editable sentence built from
its name.
