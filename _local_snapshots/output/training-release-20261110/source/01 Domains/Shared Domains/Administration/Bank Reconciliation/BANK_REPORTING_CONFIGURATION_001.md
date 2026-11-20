# Economic Reporting Configuration

**Task:** BANK_REPORTING_CONFIGURATION_001
**Status:** Implemented — real configuration applied to the golden database.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Migration:** `f7c4a21e98b3`
**Configuration script:** `03 Software/RF-One Data Store/configure_reporting_structure.py`
**Builds on:** `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.md`, `BANK_INVOICE_EVIDENCE_COLLABORATION_001.md`

---

## What is now configured

| | |
|---|---|
| ReportingGroup | **`ReportingGroup`** — one, ACTIVE |
| LEGAL reporting entities | **3** — Angeli E Demoni, LLC · RF Gelati, LLC · RF Mount Dora, LLC |
| VIRTUAL reporting entities | **0** |
| Destination (ship-to) mappings | **2** — `Winter Park` → Angeli E Demoni · `Mount Dora` → RF Mount Dora |

Each reporting entity is bound to its `LegalEntity` **by legal name, not by
id**, and all three consolidate into the one group. No `LegalEntity` was
created, renamed or modified.

`ReportingGroup` remains deliberately **not** a `Corporate`: `00 Core/
Corporate.md` defines Corporate as the highest organizational Entity with
governance and strategy responsibilities, and no Corporate table is
persisted in this schema. This is the narrower consolidation perimeter
only.

---

## Restaurant ownership is untouched

`Restaurant.legal_entity_id` is still NULL, deliberately. The reporting
entity configuration is sufficient for Bank economic reporting, and which
`LegalEntity` owns the Restaurant operational unit remains a separate
decision with Payroll and Compensation consequences.

Nothing in this task reads or writes that relationship.

---

## Destination evidence: text → reporting entity

The Invoice collaboration recognized an economic owner only when a
document's ship-to text **equalled a reporting entity's name**. Real
suppliers write a trading name, a store label or a street address, never
"Angeli E Demoni, LLC", so that was too fragile to survive ingestion.

`ReportingEntityDestinationAlias` replaces it with a generic mapping:

```text
SOURCE DESTINATION TEXT  ->  REPORTING ENTITY
```

It is **evidence mapping, not accounting classification**. It never chooses
an account, never decides a WHY, and never answers what the document did
not establish.

### Scope is the safety mechanism

| Scope | Claims |
|---|---|
| `SUPPLIER` | Only what THAT supplier's paperwork means |
| `GLOBAL` | The text means the same thing everywhere |

> "ROME'S FLAVOURS" from Supplier A does not prove the same meaning for
> every external source.

Resolution always prefers the **narrowest** matching scope: a supplier
mapping beats a global one, because the more specific statement is the
better-evidenced one. Two partial unique indexes keep one meaning per key
per scope, so a contradiction is impossible rather than merely
discouraged.

### Four distinct outcomes

| Outcome | Meaning |
|---|---|
| `RESOLVED` | One entity, established |
| `NEEDS_OPERATOR` | The same text means different entities for different suppliers, and this context cannot settle it |
| `UNKNOWN` | No mapping exists. Not ambiguity — there is simply nothing on file |
| `NO_EVIDENCE` | The document carries no destination text at all |

`UNKNOWN` and `NEEDS_OPERATOR` are kept apart on purpose: one is a gap to
record, the other is a question to ask.

### What it refuses to do

* **No fuzzy matching.** Two strings match after normalization or they do
  not. "Probably the same place" is how an expense silently lands on the
  wrong LLC's P&L.
* **No inference** from the payer, the supplier's identity, a historical
  majority, or the item category.
* **No mapping without stated evidence** — `evidence` is NOT NULL, because
  a mapping without it is an opinion about who bore a cost.

Retiring a mapping deactivates it and appends the reason; nothing is
deleted.

---

## The ship-to evidence actually found

**Every one of the 17 purchase documents has `destination_location = NULL`,
and `customer_account_reference = NULL`.** A full scan of all 243 tables
found the strings "Winter Park" and "Mount Dora" in exactly one place:
`legal_entities.legal_name = 'RF Mount Dora, LLC'`.

So **no mapping could be created from document evidence.** None was
invented to fill that gap.

The two mappings that exist were derived by the configuration script from
RF-One's own existing configuration, and each records the exact evidence:

| Location | Evidence | Conclusion |
|---|---|---|
| **Mount Dora** | `LegalEntity 'RF Mount Dora, LLC'` is itself named after it; `PaymentInstrument 'RFMD Checking'` belongs to it | RF Mount Dora, LLC |
| **Winter Park** | `PaymentInstrument 'WP-Checking'` and `'RFWP- Checking'` both belong to Angeli E Demoni, LLC | Angeli E Demoni, LLC |

The script does not hold a fixed list — it searches for the evidence and
refuses to write a mapping it cannot support. A location whose evidence
pointed at two Legal Entities would produce no mapping at all.

> **Please confirm the Winter Park mapping.** The two are not equally
> strong. Mount Dora is established by the Legal Entity's own legal name.
> Winter Park rests on reading the abbreviation **WP** in two bank-account
> labels as "Winter Park" — consistent, uncontradicted anywhere in the
> database, and consistent with the relationship the task anticipated, but
> it is an inference about an abbreviation rather than a literal statement.
> The row that would settle it authoritatively,
> `Restaurant.legal_entity_id`, is deliberately out of scope here. The
> mapping is recorded with `confirmation_source = SYSTEM_EVIDENCE` and its
> full reasoning, so it can be reviewed or deactivated in one call.

### Left deliberately unmapped

* **RF Gelati, LLC** — no physical ship-to is invented for it (§9). It
  receives allocations from explicit document evidence or an operator
  decision. "RF Corporate" is a bank-account label, not a delivery
  address.
* **"Rome's Flavours - WP"** — a trading name. A global mapping would claim
  it means the same entity on every source's paperwork, which no evidence
  supports, and it is the task's own example of text that needs supplier
  scope. Map it per supplier when a real document uses it.
* **The bare abbreviations "WP" / "MD"** — two letters are far too weak to
  be a global destination key.

---

## WHO ↔ Supplier linking, ready for ingestion

No real `BankOccurrence` exists yet, and **none was seeded** to create
links. What was prepared and tested is the behaviour that runs when a real
WHO first appears during Bank ingestion:

```text
Real Bank WHO appears
      ↓  search canonical Supplier name and SupplierAlias, exact after normalization
one strong unique match   ->  PROPOSED (and linked when asked to)
several candidates        ->  NEEDS_OPERATOR
name too short to identify->  NEEDS_OPERATOR
no match                  ->  NO_MATCH — the WHO stays valid and unlinked
already linked            ->  ALREADY_LINKED, reused
```

* **Exact-after-normalization only.** There is no fuzzy tier. "Probably the
  same vendor" is how a payment ends up attached to another company's
  invoices.
* **Amount is never consulted.** Two parties being owed the same figure
  says nothing about who they are.
* **No Supplier is ever created, renamed or merged** by discovery, so an
  unrecognized counterparty can never become a duplicate supplier row.
* **A minimum name length applies** before automatic linking. This is not
  cosmetic: the real supplier catalog contains OCR artefacts — one supplier
  is literally named `I` — and an exact match against one of those would be
  a coincidence, not an identification. An operator may still confirm such
  a link explicitly.
* **An operator-confirmed link is recorded as `HUMAN`** and is reused by
  every later transaction for that counterparty.

---

## P&L, unchanged

Reporting still reads `BankTransactionAllocation` and nothing else.
Verified on disposable fixtures: an allocation for each entity appears in
that entity's P&L; the consolidated `ReportingGroup` P&L contains all three
exactly once; and cross-entity payer effects remain Balance Sheet
positions (`1610` / `2710`) that never enter any P&L.

---

## What this task deliberately did not do

No AWS access, no deploy, no Bank/Historic Data or Bank/Download import,
no Zelle OCR, no real `BankOccurrence`, no fake Supplier, no VIRTUAL
reporting entity, no change to `LegalEntity`, `PaymentInstrument`,
settlements, `Restaurant.legal_entity_id`, `Supplier`, `SupplierAlias`,
`PurchaseDocument` or `PurchaseLine`, no
`reconciliation_control_start`, no learned WHY rules, no QBO/CSV export
change, and nothing touched in Tips, Payroll or Compensation.

Row-by-row diff against the pre-change backup confirms all of the above
tables are byte-identical.

---

## Where the code lives

| Concern | File |
|---|---|
| Model | `rfone_data_store/models.py` (`ReportingEntityDestinationAlias`) |
| Mapping CRUD and resolution | `rfone_data_store/bank_reconciliation/destination_evidence.py` |
| WHO → Supplier discovery | `rfone_data_store/bank_reconciliation/invoice_evidence.py` |
| Owner resolution from a document | `invoice_evidence.resolve_owner_from_document_evidence` |
| Configuration (idempotent, dry-run by default) | `configure_reporting_structure.py` |
| Migration | `migrations/versions/f7c4a21e98b3_add_destination_evidence_mapping.py` |
| Tests | `test_bank_reporting_configuration.py` |
