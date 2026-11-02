# RF-One Release Checklist

**Mandatory for every release of every RF-One service** (`rfone-web`, `rfone-selection`, `rfone-tips`, the Clover workers and any later service). A release that misses an item is not done.

This checklist collects obligations already in force and points to their own documents; it does not redefine them. Only item 3 is new (UI_HOW_WORKS_001, 2026-11-02).

| # | Item | Where it is defined | Automatic |
|---|---|---|---|
| 1 | Release only committed code that is pushed to origin, through the service's own release procedure, never from an uncommitted folder | `rfone-selection/release_selection.py` (SELECTION_DEPLOY_GUARD_001); each service's folder in this directory | Selection: yes |
| 2 | The tests of the changed modules pass on that commit | the module's `test_*.py` | no |
| 3 | **How Works:** every changed page has its How Works link and its Help section updated in the same release; a new page is registered with its Help; a technical-only commit is declared `How-Works: technical - <reason>` | [`How Works Standard.md`](../../Shared%20UI/How%20Works%20Standard.md) | Selection: yes (in `release_selection.py`); other services: run the command below |
| 4 | Migrations and AWS data changes only with their own explicit approval | `CLAUDE.md` (Local Database Policy), the release's task | no |
| 5 | A release record with the commit, the image, the backups and how to restore | e.g. `rfone-selection/DEPLOYMENT-*.md`, `07 Tasks/Reports/` | Selection: partly (release JSON) |
| 6 | The final REPORT | `CLAUDE.md` (RF-One Report Standard) | no |

## Item 3: the How Works command

Run it from the repository root on the commit being released, against the commit currently live:

```text
python "03 Software/Shared UI/check_how_works.py" --app "<App>" --rev <commit to release> --since <commit live now>
```

`<App>` is the registry name: `Selection`, `RF-One Web`, `Tips`, `Training`, `InvoiceIntake`. Exit code 1 is a release error: do not release. Fix it by updating the Help with the code (or, for a change that is really technical only, by declaring it in the commit message), never by editing the registry to hide a page.
