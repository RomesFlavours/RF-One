# Bank one proposal per description format

## 1. Reported failure
The live discovery scan 56 contained three Toast proposals. Two differed only by a space after TST*. The third changed the end delimiter. Exact policy deduplication had preserved them as separate cards, contrary to the requested workflow.

## 2. Resolution
Discovery groups by normalized description prefix and WHO-start delimiter, independently of suffix and end-delimiter interpretation. A format is displayed once. Equivalent whitespace policies are collapsed; distinct extraction policies are retained as variants inside that one discussion. Competing variants require human clarification before the draft can be previewed or published; they are not arbitrarily merged into an executable policy. The same grouping applies to cached results and newly generated results. Both publication paths continue to target the existing format's rule rather than creating copies. Publishing the agreed policy retires other cached cards in that group.

## 3. Validation
Regression tests reproduce the three Toast proposals, assert one card with two policy variants, reject preview before clarification, publish one rule and retain that identity. New-generation and cached discovery paths, draft discard and both save actions are checked. Read-only verification uses the actual cached scan to confirm a single Toast group.

## 4. Traceability
No production policy is created, applied or deleted during deployment. Source and database backups are retained with the verification report.
