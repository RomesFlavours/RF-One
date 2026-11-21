# Retirement of `source_role_mappings` for Tips (TIPS_REGISTRY_ROLES_001)

Product Owner decision, 2026-11-21: Registry is the only official source of the Clover role ->
RF-One role correspondence. Tips (`tips/clover_role_history.py`) reads it from
`registry_role_mappings` (source `CLOVER`, per Restaurant, temporal), managed in
Anagrafica > Reparti e ruoli.

- `source_role_mappings` is no longer read by Tips. It is **inactive, not deleted**: on AWS it had
  0 rows on 2026-11-21, which is why every Clover-observed role was "uncertain" and Winter Park Tips
  calculations were blocked.
- The only remaining code that writes it is the manual Restaurant Profile bootstrap
  (`profile/bootstrap.py`), never run on AWS; its rows would have no effect on Tips.
- Temporal rule: the first Registry version of a Clover role applies since always (the table was
  introduced after the roles existed); each later version applies from its own `valid_from`.
- A Clover role without an RF-One role in Registry is "to be defined": the calculation is blocked and
  the role is named in the reason. Nothing is guessed.
- Distribution rules, percentages, hours, history, finalized runs, entitlements and payments are
  unchanged. Deleting the table needs a separate decision and migration.

## Product Owner decisions, 2026-11-21 (TIPS_REGISTRY_ROLES_002)

- Retroactive first version: allowed unless a confirmed (MANUAL) Registry assignment valid at that
  instant shows another role; then the role is uncertain and the reason says so.
- Before a person's first Clover observation: the Registry assignment documented and valid at that
  date (never one that starts later: today's role is never projected into the past). None, or two
  different ones, is an explicit exception in the blocked reason.
- Verified on AWS data (read-only): for closed periods the result with Registry history equals the
  result with assignments only; finalized runs and entitlements are never recomputed or changed.
