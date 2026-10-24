# Bank explicit rule update target

## 1. Problem
Unlinked discovered variants were treated as new rules even when their base extraction format already existed. Refining the suffix policy could bypass the exact duplicate guard.

## 2. Resolution
Discovery opening resolves the existing extraction format independently of suffix refinements. One candidate is linked automatically. Multiple candidates require an explicit selection of the rule to update in the modal, preserving the draft. Publication blocks creation of another rule for an existing family, including older unlinked conversations. Both final actions publish a new historical version under the selected rule ID. No automatic merging or deletion of existing production rules.

## 3. Validation
Tests count rule records before and after refinement and verify version increment on the same ID. Ambiguous candidates, explicit target selection, FUTURE and ALL saves, and duplicate protection are exercised.

## 4. Traceability
Deployment output preserves original source and database backups with verification report.
