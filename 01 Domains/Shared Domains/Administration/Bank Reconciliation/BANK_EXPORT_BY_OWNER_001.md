# Monthly Export per Owning Entity, people included

**Task:** BANK_EXPORT_BY_OWNER_001
**Status:** Implemented on `feature/bank-simple-who-rules`. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration — the existing Source owner model is reused.

---

## What changed

The Monthly Accountant Export is generated **per Owning Entity** of the Sources: a Company
(an LLC — its LEGAL ReportingEntity when it has one) or a **person** (a PERSONAL ReportingEntity).
The owner is chosen next to year and month and is required before Check and Download; there is no
"all owners" export.

| Question | Answer |
|---|---|
| Which owners are offered? | The owners already present on payment Sources, each once (`export.owner_choices`). |
| Which movements are in a report? | The month's in-scope movements (the same scope as before) of that owner's Sources — each once. |
| How is a movement's owner read? | Exactly where ownership already lives (`OwnerIndex`): a bank account's own owner; a card's is the owner of the account it settles to **on the movement's date** (`card_configuration.accounting_account_for`). Never the WHO, never For Whom. |
| For Whom? | Unchanged and independent: a payment from Pino's personal account for MD is in **Pino's** report, with **MD as For Whom**. |
| A Source owned by a person | A valid owner: its own report, no LLC needed, never a blocker. The Source page no longer warns "Owned by a person". |
| A Source with no owner | Its movements are in no owner's report. They are listed on every owner's page as **Not attributed to any owner** (with *Fix this file* / *Open Source*), never assigned automatically, never dropped silently, and they block no owner. A file with no Source identified is listed the same way. |
| Blockers | Only the selected owner's: its movements (duplicates, Needs review, incomplete classification) and the parsing errors of its own Sources' files. Another owner's problems never block it. |
| No movement | "No transactions for this owner and month" — never READY, no file. |

Monthly statement expectations (`monthly_source`) were never part of the export's gate; nothing
there changed.

## The file

`RfBank_YYYY_MM_<Owner>.xlsx`. Sheet **Bank**: the accountant's 12 columns unchanged and first,
then **For Whom** (from the movement's allocation), **Owner** and **Owner Type** (Company / Person).
*Company* stays the LLC's legal name and is empty for a person — no fictitious LLC. Sheet **Report**:
owner, owner type, year, month, row count and totals per currency.

`export.export_content` produces the rows once; the Check page's *Rows in the file* and *Total
<currency>* figures and the downloaded file both read it, so they always agree. Nothing is
recalculated and no rule is applied: the decisions' snapshots are read as before.

## Open points

* A file whose Source was never identified, or a card without a settlement account, no longer
  blocks any report; it is listed as not attributed. If its movements belong to the selected owner,
  that report is incomplete until the Source is fixed — the page says so on every owner's page.
* A Source whose currency is not set is totalled under *(currency not set)*.
