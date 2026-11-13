# Registry person editor status contract

Approved local task, 2026-11-12. Applies to the actual Registry on loopback port
5094, using the existing Employee directory and linked RF-One accounts.

Company relationships are a concurrent set: CANDIDATE, EXTERNAL, EMPLOYEE.
They describe company relationship, independently of company memberships, job
roles, permissions and account access. Unspecified historical facts are retained
as unspecified. Existing identity records are reused; no name-based merges.
The additive rfone_person_company_statuses relation references the existing
Employee identity or an unlinked external account, never a new person register.
Account status uses the existing RFOneAccount.status ACTIVE/INACTIVE. Changing
company relationships does not grant permissions, assign roles or provision
Training. Employees require no separate STUDENT qualification for eligibility.

Both controls are saved atomically with the existing profile service. Existing
callers omitting the new arguments retain current behavior. Status changes revoke
existing account sessions. Owner/current-operator accounts remain protected from
accidental self-disable. The local UI is Italian, with a compact modal, sticky
close and save controls, contextual help, draft retention and row return.
No AWS operations or production writes are authorized by this task.


## Verified local application

Migration s1a120261112 was applied only to the loopback Registry database,
rfone_employee_directory, from f3b120261110. Historical data digests matched
before/after. Source backup and pre-migration digests are in
C:/Users/servi/AppData/Local/RF-One/Backups/registry-person-modal-20261112.

Service validation: 21 isolated tests, including the 15 existing role/company
checks and 6 status persistence/validation/compatibility checks, passed.
The actual 5094 Edge E2E (`RF-One Web/test_registry_modal_5094.py`) creates a
unique synthetic identity, saves both statuses, verifies PostgreSQL values,
checks error rollback and draft retention, then repeats editing at 390px width.
It verifies Help/Cancel/X/Escape behavior and focus returning to the saved row.
Synthetic identity, account, qualification and audit rows are removed in finally;
original person/account/membership/role/grant digests must match the baseline.
The latest proof and screenshots are in the backup directory above. The local
service remains running on 5094. No AWS or production operation was performed.
