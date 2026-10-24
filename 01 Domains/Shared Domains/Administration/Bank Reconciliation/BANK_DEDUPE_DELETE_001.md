# Bank duplicate formats and modal deletion

## 1. Request
Prevent repeated AI extraction formats and provide Delete inside the rule modal.

## 2. Implementation
Canonical extraction policy keys ignore titles, explanation wording, case, list ordering and omitted defaults. They preserve meaningful delimiters, exclusions, suffix policy and approved numeric names. Discovery deduplicates proposals, links equivalent known rules, and filters duplicates in cached results while retaining original proposal indices. New publication rejects an identical existing extraction policy.
Delete in the modal uses existing rule deletion for published rules and discards unpublished drafts or discovery proposals. Discard hides equivalent duplicate proposals in that scan. Deletion preserves transaction records and rollback history. No existing production rule is automatically deleted.

## 3. Validation
Targeted tests cover equivalent specifications, real differing variants, discovery deduplication, duplicate publication rejection, draft/proposal discard, deleted rule exclusion, both publication actions and guarded rollback. Python and template parsing and JavaScript syntax checked.

## 4. Traceability
Deployment output includes source backups, database backup, verification and report.
