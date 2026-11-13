# Registry / Training identity foundation - local result

The canonical person model is the existing CandidatePerson, with the existing person-account, person-employee and person-Training link contracts. A new administrator review page is available at http://127.0.0.1:5094/admin/registry/identity-reconciliation, linked from Registry.

## Existing local data audit

- 143 central person records, currently without confirmed operational links.
- 76 operational identity groups still unlinked to a central person.
- 0 groups with conflicting confirmed central-person links; 0 dangling explicit links.
- No suggested name/email matches in this particular snapshot. This does not establish that no real-world duplicates exist: human review is still required.
- Existing protected counts: 70 employees; 7 RF1 accounts; 3 Training identities; 2 RF1/Training bridges; 65 direct domain grants; 1 item grant; 2 Training needs; 56 assignments; 0 quiz attempts.

The additive schema setup preserved counts and SHA-256 fingerprints of the protected tables. No historical identity was automatically linked and no new central person was inserted into the existing database. Only disposable test databases received test confirmations.

## Delivered

Read-only graph audit and shared central-person lookup, Registry/Training reference fields, guarded atomic confirmations, stale-review checks, immutable confirmation events, explicit local migration, read-only loopback-only audit CLI, and an administrator/CSRF-protected review interface. No automatic merge, source deletion, credentials change or grant change.

11 service/migration tests, 10 HTTP/browser tests, 192 Registry checks and 10 performance/Clover regression tests passed. Sources and operational details: 03 Software/RF-One Web/PERSON_RECONCILIATION.md in the local development checkout. Private audit evidence: tmp/person-reconciliation.

This completes the local identity/reconciliation foundation, not the full Training correction program. The 76 groups await explicit human reconciliation. Training enrollment/access enablement, unified recipient selection, company boundaries, lifecycle and credential-management corrections remain separate steps. No AWS deployment or Git push was performed.
