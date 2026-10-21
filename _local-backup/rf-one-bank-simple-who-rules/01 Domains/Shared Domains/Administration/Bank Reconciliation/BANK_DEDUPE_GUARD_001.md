# 1. Duplicate update guard
Also prevent updating a distinct existing rule into an identical extraction policy. Existing unchanged duplicates are retained without automatic merging.

# 2. Validation
Publication tests use distinct formats for FUTURE and ALL, avoiding intentional cross-test duplicate creation.

# 3. Traceability
Extends BANK_DEDUPE_DELETE_001. Backups and verification are in deployment output.
