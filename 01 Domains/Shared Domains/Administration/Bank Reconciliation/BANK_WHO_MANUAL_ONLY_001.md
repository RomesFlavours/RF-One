# WHO Classification UX and Manual Only WHO

**Task:** BANK_WHO_MANUAL_ONLY_001 (Product Owner decision, 2026-10-05)
**Status:** Implemented on `feature/bank-simple-who-rules`. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** migration `b7f1c3e5a9d2` — `bank_occurrences.manual_only` (boolean, default false; no data change).

---

## Manual Only

A person may mark a WHO **Manual Only**: it is reconciled by hand when it occurs (e.g. a restaurant visited
occasionally) and takes no part in **individual WHO Rule automation**.

| | Manual Only WHO |
|---|---|
| WHO Rule button | replaced by a "Manual Only" badge |
| WHO Rule Apply (`who_rules.apply_who_rule`) | refused, also when the WHO is reached by name from the Review combo |
| WHO Rule fragment merge | a Manual Only WHO is never merged as a fragment |
| Classification Learning, WHO-Rule candidates | never a target; a stored WHO suggestion for it cannot be approved |
| Classification Learning, structural and WHY candidates | unchanged: its transactions remain evidence |
| General Rules | unchanged: they may still extract a name that is this WHO |
| Manual WHO / WHY reconciliation | unchanged |

Marking a WHO that has an active WHO Rule is refused until the person explicitly chooses **"Disable existing WHO
Rule and mark Manual Only"** (or Cancel). The rule then becomes INACTIVE — kept for history, never deleted — and
transactions already recognised stay as they are. Removing Manual Only only clears the flag; disabled rules are
not re-enabled. One service: `who_rules.set_manual_only`; one route: `POST /bank/who-rules/manual-only`.

## WHO Classification list

Active WHO are listed in three groups, alphabetical (case-insensitive) inside each, with a heading and count:

1. **Needs Rule** — no active WHO Rule, not Manual Only;
2. **Has Rule** — at least one ACTIVE description WHO recognition rule (General Rules, WHY Rules, inactive rules
   and suggestions do not count);
3. **Manual Only**.

The group is computed in the query that orders and pages the list (no per-WHO query). Search covers all groups
and keeps the headings. The merged-WHO view is not grouped.

Columns: WHO · Type · Transactions · **Last transaction** · Recognised when · actions.

**Last transaction** shows the WHO's most recent bank transaction, so a person sees what the WHO really is before
choosing a Rule or Manual Only: the bank's original description (`description_original`, never a WHO label; two
lines at most, the whole text on hover), then date · account · amount. Latest = greatest `posting_date`, then
greatest transaction id. A WHO holds a transaction through its recognition or its current decision — the same
family the Transactions count reads — and a canonical WHO also answers for the merged WHO it absorbed (an
INACTIVE WHO whose name it holds as a `MERGED_WHO_NAME` alias). A WHO without transactions shows "—". All rows of
a page are answered by one window-function query (`who_rules.latest_transactions`), never one query per WHO.

## Page and modal

* Classification uses the Bank frame (`wrap-wide`), like every other Bank page.
* `#who-classification` is the stable anchor of WHO Classification. Apply in the Rule modal, Manual Only, search
  and paging return there with the same query; Apply reloads the page so its result is shown and the scroll
  position is kept.
* The Rule modal is a wide two-column panel (about 88vw, max 1500px): WHO, Rule sentence and Apply information on
  the left; Possible WHY on the right, grouped by the WHY navigation groups (`BankReasonGroup`, alphabetical, like
  every Bank UI; WHY alphabetical inside each), collapsible, one search across all groups, selected WHY counted per group. Possible WHY remain WHO
  associations only: Apply never chooses a WHY for a transaction.
