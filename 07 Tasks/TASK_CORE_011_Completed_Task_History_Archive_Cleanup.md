# TASK_CORE_011 — Completed Task History Archive Cleanup

## Objective

Clean the active task workspace after completion of TASK_CORE_001 through TASK_CORE_010.

Completed task specifications and their completed reports should no longer remain mixed with active work under `07 Tasks/`.

Archive them instead of deleting them so RF-One preserves:

- decision history;
- implementation/audit trail;
- provenance;
- past architectural reasoning;
- the ability to understand why canonical documentation changed.

This is a **repository-governance / file-organization task**.

Do not redesign RF-One concepts.

Do not delete completed task history.

Do not modify software behavior.

Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Read:
   - `07 Tasks/README.md`
   - `90 Archive/README.md`
   - `PROJECT_STATE.md`

3. Inspect the complete contents of:
   - `07 Tasks/`
   - `07 Tasks/Reports/`
   - `07 Tasks/Backlog/`

4. Confirm which `TASK_CORE_001` through `TASK_CORE_010` specification files actually exist.

5. Confirm which corresponding report files actually exist.

6. Search the repository for references or Markdown links to:
   - `07 Tasks/TASK_CORE_`
   - `07 Tasks/Reports/TASK_CORE_`
   - exact completed task/report filenames.

7. Run `git status` before making changes.

Preserve all unstaged/untracked work produced by TASK_CORE_006 through TASK_CORE_010.

---

# Approved archive structure

Create:

```text
90 Archive/Task History/
├── README.md
├── Tasks/
└── Reports/
```

The archive is historical and non-authoritative.

Canonical truth remains in:

- `00 Core/`
- `01 Domains/`
- `09 Strategy/`
- other canonical layer documentation.

Task history explains how RF-One arrived there; it must not override canonical documentation.

---

# Files to archive

Archive all **completed** task specifications from:

```text
TASK_CORE_001
through
TASK_CORE_010
```

that actually exist in `07 Tasks/`.

Move them to:

```text
90 Archive/Task History/Tasks/
```

preserving filenames exactly.

Archive all completed corresponding reports that actually exist under:

```text
07 Tasks/Reports/
```

Move them to:

```text
90 Archive/Task History/Reports/
```

preserving filenames exactly.

Do not invent missing reports.

Do not create placeholder files for reports that never existed.

---

# Current task exception

Do **not** archive:

```text
07 Tasks/TASK_CORE_011_Completed_Task_History_Archive_Cleanup.md
```

This is the active task.

Its report must also remain active at:

```text
07 Tasks/Reports/TASK_CORE_011_REPORT.md
```

because TASK_CORE_011 is not historical until the Product Owner has reviewed and committed it.

---

# Backlog treatment

Do not archive or delete:

```text
07 Tasks/Backlog/
```

The backlog remains active planning/governance material unless a future task explicitly retires individual backlog items.

In particular, preserve:

```text
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md
```

in its current canonical active location.

---

# Reference handling

Moving task history must not leave broken links.

For every repository reference to a moved Task or Report:

## If it is a Markdown link

Update the path to the new archive location.

Example:

```text
07 Tasks/Reports/TASK_CORE_009_REPORT.md
```

becomes:

```text
90 Archive/Task History/Reports/TASK_CORE_009_REPORT.md
```

## If it is plain historical prose

A path update is appropriate if the prose explicitly identifies the old path.

Do not rewrite conceptual content merely to remove task-number references.

## If a canonical document depends on a Task/Report as authority

Do not silently preserve a bad authority relationship.

Canonical documents should be authoritative for concepts; archived Task/Report files are provenance only.

If you find a canonical document whose meaning depends on an archived report rather than canonical content:

- do not redesign it silently;
- record the issue in the final report;
- only make a minimal wording/path correction if the intended canonical source is obvious and already exists.

---

# `07 Tasks/README.md`

Update it to clearly explain the active task workspace.

It should state that `07 Tasks/` contains:

- currently active task specifications;
- active reports awaiting review/commit;
- active backlog/planning material.

It should also state that completed historical task specifications/reports are archived under:

```text
90 Archive/Task History/
```

Keep it concise.

---

# `90 Archive/Task History/README.md`

Create a short README explaining:

1. this directory contains completed RF-One task specifications and reports;
2. these files are historical/provenance material;
3. they are non-authoritative;
4. canonical meaning resides in the current Core/Domain/Strategy/etc. documentation;
5. historical "Approved" wording inside an archived Task/Report does not supersede newer canonical documentation;
6. archived files should normally remain unchanged except for explicit archival/governance maintenance.

---

# `90 Archive/README.md`

Update minimally to list:

```text
Task History/
```

as a historical/non-authoritative archive area.

Do not rewrite the whole Archive policy.

---

# `PROJECT_STATE.md`

Modify only if necessary.

If it contains direct path references to completed Task/Report files, update them.

Do not add a long task-history section.

The project state should describe the current RF-One state, not become an index of historical tasks.

---

# No deletion rule

Do not permanently delete any completed TASK_CORE_001–010 specification or report.

Use Git-aware moves/renames where possible so history remains traceable.

The objective is:

```text
active workspace cleanup
```

not:

```text
history destruction
```

---

# Expected active `07 Tasks/` shape after cleanup

The exact contents depend on existing files, but conceptually it should resemble:

```text
07 Tasks/
├── README.md
├── Backlog/
│   └── ...
├── Reports/
│   └── TASK_CORE_011_REPORT.md
└── TASK_CORE_011_Completed_Task_History_Archive_Cleanup.md
```

Do not create empty placeholder task files.

If other genuinely active, non-completed tasks exist, leave them in place and explain them in the report.

---

# Expected archive shape

Conceptually:

```text
90 Archive/
├── README.md
├── Legacy Repository/
│   └── ...
└── Task History/
    ├── README.md
    ├── Tasks/
    │   ├── TASK_CORE_001_...
    │   ├── ...
    │   └── TASK_CORE_010_...
    └── Reports/
        ├── TASK_CORE_005_REPORT.md
        ├── ...
        └── TASK_CORE_010_REPORT.md
```

The report list above is illustrative.

Archive only reports that actually exist.

---

# Validation

After moving files:

1. Verify no completed `TASK_CORE_001`–`TASK_CORE_010` specification remains under the active `07 Tasks/` root.
2. Verify no completed corresponding report remains under active `07 Tasks/Reports/`.
3. Verify TASK_CORE_011 and its report remain active.
4. Verify `07 Tasks/Backlog/` is untouched except for path-reference corrections if absolutely necessary.
5. Verify no Task/Report was deleted.
6. Verify all moved filenames are unchanged.
7. Verify Markdown links to moved files resolve to the new archive location.
8. Search for stale old paths:
   - `07 Tasks/TASK_CORE_001`
   - through `07 Tasks/TASK_CORE_010`
   - `07 Tasks/Reports/TASK_CORE_`
9. Verify no Core concept definition changed.
10. Verify no Domain concept definition changed.
11. Verify no Strategy concept definition changed.
12. Verify no Software file changed.
13. Run `git status`.
14. Do not commit.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_CORE_011_REPORT.md
```

with exactly these sections.

## A. Summary

State what was archived and why.

## B. Task specifications archived

List every exact task filename moved and its destination.

## C. Reports archived

List every exact report filename moved and its destination.

Explicitly identify any TASK_CORE_001–010 report that did not exist and therefore was not invented.

## D. Active task workspace after cleanup

List what remains under:

```text
07 Tasks/
```

and explain why it remains active.

## E. Archive structure

Show the resulting:

```text
90 Archive/Task History/
```

structure.

## F. References updated

List every file whose Task/Report path reference was updated.

If no references required modification, state that explicitly.

## G. Authority / governance confirmation

Confirm that archived Tasks/Reports are historical and non-authoritative and that canonical documentation remains authoritative.

## H. Scope integrity

Confirm no conceptual redesign occurred.

## I. Git status / scope confirmation

Confirm:

- no Task/Report history was deleted;
- no Core conceptual file changed;
- no Domain conceptual file changed;
- no Strategy conceptual file changed except path-only correction if required;
- no Software file changed;
- no Git commit.

---

# Restrictions

Do not:

- delete completed task history;
- archive TASK_CORE_011;
- archive TASK_CORE_011_REPORT;
- move or remove `07 Tasks/Backlog/`;
- change Core concepts;
- change Domain concepts;
- change Strategy concepts;
- modify Product specifications;
- modify Software;
- modify the legacy repository contents under `90 Archive/Legacy Repository/`;
- make a Git commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_011_REPORT.md
```

Then stop.
