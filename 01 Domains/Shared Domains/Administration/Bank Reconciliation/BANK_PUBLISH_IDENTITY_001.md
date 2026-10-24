# Bank publication identity

## 1. Problem
A discovered format could be published, then reopened from its original discovery card as an unrelated new conversation. Repeated publication created a separate rule while the earlier definition remained unchanged. Old conversation history also obscured the current published definition.

## 2. Changes
Discovery conversations retain their scan and format identity. Both final Save actions update the discovery entry with the exact published rule ID, version, text and spec. Reopening a published discovery reads the current rule version. Both existing-rule save paths retain the selected rule ID and publish the preview definition. The modal separately shows the current published definition; discovery results refresh after saving.

## 3. Verification
Regression checks exercise FUTURE and ALL with changed text/spec, verify version increments and reopen both from rule and discovery after a second publication. Guarded rollback and frozen draft checks remain. No production rule is applied during deployment. Existing duplicate historical rules are preserved.

## 4. Traceability
See deployment output report, code backups and SQLite backup.
