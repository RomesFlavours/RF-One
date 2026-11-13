# Registry navigation release - November 12, 2026

AWS deploy and Git push completed. Commit: 34c321148c6d7624f686a6398aab5479cf17a136. Branch: codex/registry-navigation-20261112.

## Behavior

- Permissions Save returns to the validated canonical person in Registry; its editor reopens automatically.
- Back to person and Registry breadcrumbs preserve the same person across account editing, direct permissions, Training identity linking and password reset.
- The legacy Accounts list entry redirects to Registry instead of rendering the old list.
- Validation errors retain the person context; permission selections remain visible after errors. Password errors stay at the reset section and never reflect secrets.
- Resetting one's own password retains session invalidation and explicitly preserves the person destination through required reauthentication.
- Separate authorization/reset windows preserve unsaved changes in the original person editor.

## Checks

8 local navigation tests passed, including headless browser confirmation that Save and Back reopen the correct person, including the administrator's own identity. The production image repeated HTTP cases with the browser-only case intentionally skipped. 192 Registry workflow/permission checks and 10 performance/attribution tests passed. Existing Clover-confirmation and release-policy tests passed inside the image. JavaScript syntax and template parsing passed.

The final App Runner operation succeeded and the service is RUNNING. Runtime configuration, secret references, instance and network configuration were compared and preserved. Public JavaScript and unauthenticated login boundaries were verified. No authenticated production permission, identity-link or password POST was submitted. No schema migration, data import or other service deployment was performed.

Immutable source artifacts, build/deployment IDs, baseline configuration and rollback image identifiers are recorded privately under tmp/registry-navigation-release. The Git branch contains the reviewed navigation transformer and tests applied to a pinned production image, preserving unrelated published source differences.
