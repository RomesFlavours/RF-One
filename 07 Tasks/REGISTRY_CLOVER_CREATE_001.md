# REGISTRY_CLOVER_CREATE_001 — «Crea in Clover» from the Registry card

Status: implemented locally on `feature/registry-multisite` (2026-11-22), awaiting Codex review. Not pushed, not deployed.
Source: Product Owner instructions given in chat on 2026-11-22 (recorded here because other agents cannot see the chat).

## Approved behaviour (latest Product Owner instruction, 2026-11-22, supersedes the earlier correspondence-table version)

1. On the Registry card, next to each assigned site without a POS ID: **Crea in Clover**. It uses the selected
   site and the person's **Registry role at that site**; the Clover merchant is resolved on the server.
2. No correspondence table is required and RF-One performs **no check on the Clover role level**. The Clover API
   needs a role ID: RF-One reads the merchant's role catalogue and uses only the role with the **same name** as the
   Registry role. If that ID is not uniquely identifiable (none, or more than one), the card shows the error and
   nothing is sent; no other role is chosen.
3. Permissions stay with Clover: RF-One sends no system level and never creates or changes roles or permissions.
4. The employee ID returned by Clover is saved as the POS ID of that site on the same card. The manual POS ID entry
   stays for employees already in Clover. No Clover → Registry import of personal data.
5. Duplicates: a site with a POS ID shows it; double click and concurrent requests send at most one creation.
   After an uncertain answer, recovery uses the RF-One custom ID (`RF1-<person id>`). Elapsed time, an empty
   search or a manual closing never re-enable «Crea in Clover» (Product Owner, same day): the open request ends
   only when the employee is found in Clover (or when a POS ID is typed manually). A definite refusal by Clover
   (nothing created) allows a new attempt.
6. Sandbox verification of creation and role: **not executed** until sandbox credentials are provided.

## Implementation notes (technical choices within the approved behaviour)

- "Same name" = identical text ignoring surrounding spaces and letter case.
- Writing is off unless `RFONE_CLOVER_EMPLOYEE_CREATE=sandbox|production`; sandbox uses
  `CLOVER_SANDBOX_API_TOKEN__<MERCHANT_ID>`, production the merchant's own token. Required Clover token
  permissions: employees read and write. Enabling production is a separate Product Owner authorization.
- Attempts are append-only events on the card (`employee_directory_events`, actions `CLOVER_CREATE_*`); no schema change.

Code: `rfone_data_store/clover_employee_create.py`, `technical/connectors/clover/employee_writer.py`,
`RF-One Web/employee_directory_routes.py`, card template and help. Tests: `RF-One Web/tests/test_registry_clover_create_http.py`,
`tests/test_clover_employee_writer.py`.
