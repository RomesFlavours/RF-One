# REGISTRY_CLOVER_CREATE_001 — «Crea in Clover» from the Registry card

Status: implemented locally on `feature/registry-multisite` (2026-11-22), awaiting Codex review. Not pushed, not deployed.
Source: Product Owner instructions given in chat on 2026-11-22 (recorded here because other agents cannot see the chat).

## Approved behaviour

1. On the Registry card, next to each assigned site without a POS ID: **Crea in Clover**. It uses the selected
   site and the person's current RF-One role at that site; the Clover merchant is resolved on the server.
2. The Clover role is the **explicit correspondence RF-One role → Clover role of that site**, reusing the existing
   configuration (`RegistryRoleMapping`, source `CLOVER`, current rows). Server → Server is fine where configured.
   No fallback by name.
3. Only an existing Clover role at the base **Employee** level. Missing, ambiguous, or higher-privilege role:
   show the reason and stop before writing. RF-One never creates or changes Clover roles or permissions
   (Product Owner: "ai ruoli è associata la sicurezza, non la toccare").
4. The ID returned by Clover is saved as the POS ID of the same card for that site. The manual POS ID entry stays
   for employees already in Clover. No Clover → Registry import of personal data.
5. Duplicates: a site with a POS ID shows it; double click, concurrent requests and uncertain answers never create
   a second employee. Recovery uses the RF-One custom ID (`RF1-<person id>`); while the first outcome is uncertain
   and the search finds nothing, no second insertion is sent.
6. Sandbox verification of creation and role: **not executed** until sandbox credentials are provided.

## Implementation notes (technical choices within the approved behaviour)

- Writing is off unless `RFONE_CLOVER_EMPLOYEE_CREATE=sandbox|production`; sandbox uses
  `CLOVER_SANDBOX_API_TOKEN__<MERCHANT_ID>`, production the merchant's own token. Required Clover permissions:
  EMPLOYEES_R and EMPLOYEES_W. Enabling production is a separate Product Owner authorization.
- Attempts are append-only events on the card (`employee_directory_events`, actions `CLOVER_CREATE_*`); no schema change.
- Closing an uncertain attempt («Nessun dipendente in Clover: chiudi la richiesta») is possible only after
  2 minutes, after a person has checked Clover, and only if the custom-ID search still finds nothing.
  This is the minimum step needed so that an uncertain attempt does not block the site forever.

Code: `rfone_data_store/clover_employee_create.py`, `technical/connectors/clover/employee_writer.py`,
`RF-One Web/employee_directory_routes.py`, card template and help. Tests: `RF-One Web/tests/test_registry_clover_create_http.py`,
`tests/test_clover_employee_writer.py`.
