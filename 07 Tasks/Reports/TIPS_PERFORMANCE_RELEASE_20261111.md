# Tips performance release — 2026-11-11

## 1. Scope
Deploy the locally verified Tips optimizations and historical-evidence reporting support. Preserve the currently deployed Registry authorization and Training routing. No database copy, data import, schema migration, role change or rule activation is part of this release.

## 2. Cause and changes
Order eligibility repeatedly queried roles and shifts. Calculation now reads request-local assignments and shifts once, and reuses grouped settlement and money facts. Host audit batches orders, payments, role names and employees, and indexes sibling allocations. No cache survives a calculation request. Imported-data detail is paginated at 100 records per table while summaries retain the full selected period.

## 3. Preserved behavior
Both order-time and daily, hours-weighted rules remain supported. Full-day context, effective roles, incomplete-shift blocking, source retention and deterministic cents remain unchanged. Historical reporting preserves original bank observations and explicit owner acceptance annotations. Source payment references in audit have deterministic identifier order.

## 4. Evidence
On the same canonical local data, core calculation plus employee review: week 29,462 to 13 queries; year 145,288 to 67. Allocation and employee-review fingerprints match before/after for the week and year. Legacy engine, stateless and host-audit suites pass 40, 31 and 33 checks; flexible engine passes 18 tests and historical evidence 11 tests. How Works check passes. English is the release default; the local launcher retains Italian. These measurements are local benchmarks, not AWS timings.

## 5. Release provenance
The previously running Tips artifact is `registry-access-tips-20261110t173829z`. Recover its exact application source before applying only the verified Tips delta, preserving newer access controls. The existing shared schema revision is `t9a120261110`; the release chain includes it and does not execute migrations.

## 6. Acceptance and recovery
Require a successful image build, successful App Runner operation, expected running image, healthy startup logs and unchanged authentication boundary. Roll back by restoring the previous image identifier from the saved service configuration; no database rollback is needed because this release changes no database data or schema.

## 7. Deployment result
Pending the explicit AWS release operation. Result and push reference will be recorded after verification.
