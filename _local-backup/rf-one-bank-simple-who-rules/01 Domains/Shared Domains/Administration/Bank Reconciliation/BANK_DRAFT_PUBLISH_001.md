# Bank draft and publication flow

## 1. User request
Save draft in the editor; Preview uses the saved draft if available, otherwise the published rule. Preview ends with Save, Save and apply to repository, Edit.

## 2. Behavior
Draft saving freezes the exact definition separately from subsequent unsaved conversation. Preview labels its source Draft or Current rule and displays the reviewed definition. Final Save publishes that exact version for future imports. Repository application requires its separate explicit action and retains guarded rollback. Edit returns to the conversation. Nested recognition profiles use the preview definition.

## 3. Verification
Six targeted regression tests cover draft selection, unsaved changes, fresh-session reopening, no historical writes on future publication, pending draft compilation, nested profiles and guarded rollback. Browser fixture checks the two sources and final controls using synthetic data.

## 4. Traceability
Deployment preserves source backups and an SQLite backup in the workspace output folder. No schema migration or production rule application is performed by deployment.
