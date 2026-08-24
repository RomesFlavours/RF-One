# TASK_CLOVER_001 — Build Read-Only Clover Data Exporter

## Objective

Build the first working RF-One Clover integration as a **read-only data discovery/export tool**.

The immediate goal is:

> Connect securely to the Rome's Flavours Clover merchant account, retrieve all merchant data exposed by the authorized Clover REST API permissions, preserve the raw responses locally, and produce an inventory of what Clover actually stores and exposes.

This is the first implementation step toward:

```text
Clover API
→ raw data export
→ data discovery
→ tip calculation
→ later web function
```

Do **not** implement tip calculation yet.

Do **not** build a web UI yet.

Do **not** write anything to Clover.

---

# Security requirements

The repository root already contains a local:

```text
.env
```

with:

```text
CLOVER_MERCHANT_ID=...
CLOVER_API_TOKEN=...
```

The `.env` file is ignored by Git.

Requirements:

- Never print the API token.
- Never include the API token in logs.
- Never include the API token in reports.
- Never copy the token into source code.
- Never commit `.env`.
- Never send Clover data to an external service.
- Use only HTTP `GET` requests.
- Do not call POST, PUT, PATCH or DELETE.
- Treat downloaded customer/employee/payment data as potentially sensitive.
- Raw Clover exports must remain local and must be ignored by Git.

Before doing anything else, verify that `.env` is ignored by Git without revealing its contents.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Inspect the existing repository structure, especially:

```text
03 Software/
01 Domains/Restaurant/
01 Domains/Personnel Management/Performance/
```

3. Read:

```text
01 Domains/Domain Architecture.md
01 Domains/Personnel Management/Performance/README.md
07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md
```

4. Inspect the existing software/tooling conventions under `03 Software/`.

5. Run:

```bash
git status
```

6. Verify `.env` is ignored.

Do not display `.env`.

---

# Architectural placement

This task is an implementation/integration task.

The Clover connector belongs under:

```text
03 Software/
```

not under the conceptual Restaurant Domain.

Create a contained module using the repository's existing software conventions.

If no stronger existing convention exists, use:

```text
03 Software/Clover Data Explorer/
```

Do not create implementation code inside:

```text
01 Domains/Restaurant/
```

Restaurant may later own the business semantics for tip calculation, but Clover access itself is Runtime/Software integration.

---

# Current Clover context

This is a North American production Clover merchant account.

Use the production Clover REST API base URL:

```text
https://api.clover.com
```

Authentication is by Bearer token.

The merchant identifier must come from:

```text
CLOVER_MERCHANT_ID
```

The token must come from:

```text
CLOVER_API_TOKEN
```

Do not hard-code either value.

---

# Phase 1 — Connection test

Implement the smallest safe read-only request first.

Call the merchant endpoint using the configured merchant ID and token.

The tool should report only:

- connection success/failure;
- HTTP status;
- merchant ID;
- merchant name if returned;
- response timestamp.

Do not print the token.

If authentication fails, stop cleanly and explain the status/error without exposing credentials.

---

# Phase 2 — Endpoint discovery/export

Create an exporter that attempts to retrieve all useful data exposed under the currently granted read permissions:

- Customers
- Employees
- Inventory
- Merchant
- Orders
- Payments

At minimum investigate and export, where authorized and available:

## Merchant

```text
merchant
```

## Employees

```text
employees
shifts
```

Preserve shift fields exposed by Clover, including cash-tip-related information if present.

## Customers

```text
customers
```

Do not request unnecessary sensitive expansions merely because they exist.

## Inventory

Investigate and export available collections such as:

```text
items
categories
modifier groups
modifiers
item stocks
discounts
tax rates
tags
order types
```

Only use officially available GET endpoints and only when the current token authorizes access.

## Orders

Export orders as a first-class collection.

Do not rely solely on nested `expand` fields for large related collections.

Investigate separately retrievable related data such as:

```text
line items
modifications
discounts
payments
```

when necessary to preserve complete data.

## Payments

Export payments as a first-class collection.

Preserve all returned raw payment fields.

Pay particular attention to fields relevant to later tip analysis, including where returned:

```text
amount
tipAmount
taxAmount
createdTime
modifiedTime
employee
order
tender
refunds
voided/result state
```

Do not calculate tips in this task.

---

# Pagination

Clover collection endpoints may paginate results.

The exporter must support complete pagination.

Use the API's supported `limit` / `offset` semantics.

Do not assume the default first page is the complete dataset.

Where supported, use a large legal page size (for example up to the documented maximum) and continue until the complete collection is retrieved.

Important:

Nested expanded collections can be truncated independently.

Therefore:

> Do not assume an expanded nested collection is complete merely because the parent response is complete.

When completeness matters, retrieve the related collection through its own endpoint.

---

# Time range

The user ultimately wants to understand the full historical dataset available from Clover.

For this first exporter:

- attempt to retrieve the complete accessible history;
- do not artificially impose a recent-date limit;
- if an endpoint requires filtering or Clover imposes practical limits, document the limitation;
- do not invent missing history.

The exporter must make it possible later to add incremental/date-range exports.

---

# Raw-data preservation

Create a local output area such as:

```text
03 Software/Clover Data Explorer/data/raw/
```

or an equivalent path consistent with repository conventions.

This directory must be added to `.gitignore`.

Save raw API responses without normalizing away fields.

Suggested structure:

```text
data/raw/
└── YYYY-MM-DDTHHMMSS/
    ├── manifest.json
    ├── merchant.json
    ├── employees.json
    ├── shifts.json
    ├── customers.json
    ├── items.json
    ├── categories.json
    ├── payments.json
    ├── orders.json
    └── ...
```

Exact filenames may vary based on actual discovered endpoints.

Do not create empty fake files for unsupported endpoints.

---

# Manifest

Every export run should create a non-secret manifest containing:

- export start time;
- export completion time;
- Clover environment/base URL;
- merchant ID;
- endpoint/collection name;
- HTTP success/failure;
- number of retrieved records where meaningful;
- number of pages;
- output filename;
- any API limitation/error;
- no token or secret value.

This manifest will help us understand what Clover actually exposes.

---

# Data-discovery report

After the first successful export, generate a human-readable Markdown report describing what was actually found.

Create:

```text
03 Software/Clover Data Explorer/CLOVER_DATA_DISCOVERY.md
```

or equivalent path if repository conventions require a different module name.

For every successful collection, report:

- endpoint/category;
- record count;
- major top-level fields observed;
- discovered relationships/IDs;
- earliest timestamp found where meaningful;
- latest timestamp found where meaningful;
- whether pagination was required;
- whether nested data appears incomplete;
- fields potentially relevant to tips;
- unexpected fields/data not normally visible in the Clover dashboard.

Do not dump customer names, emails, phone numbers, payment identifiers or other PII into the Markdown report.

The report is schema/discovery oriented, not a raw-data copy.

---

# Unknown endpoint handling

Do not fabricate endpoint names.

If an expected collection is not available:

1. record the attempted documented endpoint;
2. record HTTP status/error;
3. continue with other read-only collections unless authentication itself failed.

The tool must tolerate partial API coverage.

---

# Error handling

Handle at minimum:

- missing environment variables;
- invalid/expired token;
- permission denied;
- 404 unsupported endpoint;
- API throttling/rate limit;
- network failure;
- malformed/unexpected JSON;
- pagination failure.

Never retry write operations because no write operation is allowed.

Use conservative retry/backoff only for safe GET requests if appropriate.

---

# Implementation style

Prefer a simple implementation that can later be reused by a web function.

If the repository has no existing preferred language/framework, Python is acceptable.

Keep separation between:

```text
configuration
Clover API client
pagination
export orchestration
raw persistence
discovery/reporting
```

Do not overengineer.

Do not introduce a database yet.

JSON raw files are sufficient for this discovery phase.

---

# No transformation yet

This task explicitly does **not**:

- calculate employee tips;
- allocate pooled tips;
- reproduce the user's spreadsheet;
- calculate employee Performance;
- normalize Clover into RF-One ontology;
- create KPI calculations;
- build a dashboard;
- build a web API;
- build authentication for end users.

Those are later tasks.

The purpose of TASK_CLOVER_001 is to understand **what Clover actually gives us**.

---

# Git hygiene

Update `.gitignore` so raw Clover data cannot be committed.

Ignore the exact local export path.

Do not ignore the source code or discovery Markdown report.

Before finishing:

- verify `.env` is ignored;
- verify raw export JSON files are ignored;
- verify source code remains trackable;
- do not stage;
- do not commit.

---

# Validation

A successful task must demonstrate:

1. The Clover API can be reached using the local credentials.
2. No credential is printed or written to tracked files.
3. Only GET requests are used.
4. Merchant metadata is readable.
5. At least the core authorized collections are attempted.
6. Pagination is implemented.
7. Raw results are saved locally.
8. Raw results are Git-ignored.
9. A manifest is produced.
10. A schema/data-discovery report is produced without PII.
11. Payments are inspected for tip-related fields but tips are not calculated.
12. Employee shifts are inspected for fields relevant to hours/cash tips where available.
13. No Product/UI is built.
14. No Restaurant conceptual model is modified.
15. Nothing is staged.
16. Nothing is committed.

---

# Required task report

Create:

```text
07 Tasks/Reports/TASK_CLOVER_001_REPORT.md
```

with exactly these sections:

## A. Summary

## B. Implementation location

## C. Files created

## D. Files modified

## E. Authentication and security

Confirm that secrets were not exposed.

Do not include the token.

## F. Clover connection result

## G. Collections/endpoints attempted

For each collection state success/failure and record count.

## H. Historical coverage

Earliest/latest data found where meaningful.

## I. Tip-related data discovered

List fields/relationships that may later support tip calculation.

Do not calculate tips.

## J. Unexpected or useful Clover data

Describe useful fields/relationships not anticipated before export.

## K. Pagination/completeness

Explain how completeness was handled and any known limitations.

## L. Raw export structure

## M. Data discovery report

State the exact path of the generated discovery document.

## N. Open questions / Clover limitations

## O. Git/security scope confirmation

Confirm:

- `.env` ignored;
- raw exports ignored;
- no secret committed;
- no write API call;
- no staging;
- no commit.

---

# Restrictions

Do not:

- expose or print `CLOVER_API_TOKEN`;
- remove `.env` from `.gitignore`;
- commit raw merchant data;
- make POST requests;
- make PUT requests;
- make PATCH requests;
- make DELETE requests;
- change Clover data;
- calculate tips yet;
- modify Core;
- modify Personnel Management conceptual files;
- modify Restaurant conceptual files;
- build a web UI;
- build a database;
- stage;
- commit.

---

# Final response

After completing the task, return only:

1. a short completion summary;
2. whether the live Clover connection succeeded;
3. the exact report path:

```text
07 Tasks/Reports/TASK_CLOVER_001_REPORT.md
```

Then stop.
