# How Works Standard

**Code:** UI_HOW_WORKS_001
**Status:** standing, mandatory. Product Owner instruction, 2026-11-02.
**Applies to:** every operational page of every RF-One Domain and Module, in every RF-One app (RF-One Web, Selection, Tips, Training, Invoice Intake and any future app on the RF-One login), and every release of them.
**Authority:** this is the **one normative text** for How Works. `CLAUDE.md`, `AGENTS.md`, `UI Rules.md` §6 and the [Release Checklist](../Infrastructure/deploy/RELEASE_CHECKLIST.md) refer to it and do not repeat it.

> MIEAF: every function explains how it works, in the same release in which it is published.

---

## 1. Every operational page has a "How Works" link

Every operational page shows a visible **How Works** link. It opens the Help section **for that page**, inside the Help of its Domain or Module. It never opens the top of the manual.

Example: Selection → Applications → **How Works** opens *How Selection works*, section *Applications* (`/selection/how-it-works#applications`).

- **Position.** At the right end of the Domain's navigation tabs, above their divider line, in the same position on every page of the Domain (the placement of the earlier Domain-guide rule, 2026-10-27, is kept).
- **Label.** `How Works`. A tooltip may name the page ("How Applications works").
- **Target.** `<guide address>#<section id>`. The guide has one section per page or tab, with that `id`. The section opened is visibly marked (`:target` style) and is not hidden under the top edge.
- **Marker.** The link carries `data-how-works="<section id>"`. The automatic check (§5) relies on it.
- **One link, one implementation.** The link is rendered once, in the Domain's layout template, from the page's own section code. Pages do not each write their own copy (UI Rules §3).
- **The guide** uses the RF-One shell and breadcrumb, is written in English like the rest of the interface, and explains the actual workflow in the order the person meets it.

## 2. The Help describes the released behaviour

The Help section of a page:

- describes the behaviour **actually implemented**, in the version **actually published**;
- explains to the person **how to use** the function: what to do, what happens, what is kept, what can be undone;
- **does not describe planned features** that are not yet available. A current limitation that affects use may be stated as a fact ("Selection does not import Indeed applications").

This replaces, for planned features, the earlier wording "distinguishes implemented capabilities from planned or unavailable ones".

## 3. Code and Help are one release unit

Every time a function changes, its Help is updated **in the same development and the same release**. A functional change without the Help update is **not complete** and must not be released.

| Change | Kind | Help update required |
|---|---|---|
| New page, tab, action, field, filter, status or message the person sees or uses | Functional | Yes: the section of that page |
| Changed behaviour, rule, order, default, permission or outcome of an existing function | Functional | Yes |
| Removed function | Functional | Yes: remove it from the Help |
| Refactoring with identical behaviour, performance, logging, tests, deploy scripts, dependency updates, security fixes with no visible effect | Technical | No |
| Wording, layout or style changes that do not change what the person can do | Technical | No (update the Help if it quotes the wording) |

A change is **technical only** when it is declared so in its commit message, on a line of its own, with the reason:

```
How-Works: technical - <why nothing the person can do has changed>
```

The declaration is part of the history and is reviewed like any other line of the commit. Declaring a functional change as technical is a release error.

## 4. Operational pages and the registry

An **operational page** is a page a person of the business opens on the RF-One login to do their work. Not operational, and therefore without a How Works link: sign-in and password pages, layout templates, the guides themselves, public pages for people outside the business (e.g. Selection's candidate pages on RMAED.it), e-mail bodies, and fragments included in a page (partials whose name starts with `_`, modal contents, macros).

Every page template of every app is classified in [`how_works_registry.json`](how_works_registry.json), in exactly one list:

| List | Meaning |
|---|---|
| `pages` | Operational page with its How Works target: `"<template>": "<guide template>#<section id>"` |
| `not_operational` | Not an operational page, with the reason |
| `help_missing` | Operational page that existed before this standard and still has no page-specific Help. **This list can only shrink.** A new page can never be added to it. |

A template that extends nothing and has no `<html>` is a fragment and is not classified.

**Public candidate pages** (Selection's application page, online interview, interview-time choice and their notices, on RMAED.it) are excluded from the How Works link by Product Owner decision (2026-11-02). They keep the contextual instructions a candidate needs to complete them, on the page itself; a change to what a candidate must do updates those instructions in the same release.

**Legacy pages** (`help_missing`, 121 at 2026-11-02) are kept in the registry by Product Owner decision. A legacy page that a release does not change never blocks that release: it is listed as a warning only. A release is blocked by a new operational page without How Works, and by a functional change to an existing page (legacy included) without its Help update.

## 5. Automatic check

[`check_how_works.py`](check_how_works.py) (Python standard library and Git only) runs the checks:

| Check | Error when |
|---|---|
| Coverage | a page template is in none of the registry lists (a new page without How Works), or a registry entry points to a template that no longer exists |
| Link | a page in `pages` has no `data-how-works` link in its template or in the layouts it extends |
| Target | the guide template does not exist, the target has no section id, or the guide has no element with that `id` |
| Release correspondence (`--since <rev>`) | a commit in the range changes functional files of an app (templates, application code, static assets; not tests or documents) and is not declared `How-Works: technical`, but the Help of the changed pages (or, for code, any Help of that app) is not changed in the same range; or a page added in the range was put in `help_missing` |

```text
python "03 Software/Shared UI/check_how_works.py"                         # working tree, every app
python "03 Software/Shared UI/check_how_works.py" --app Selection --rev <commit> --since <released commit>
python "03 Software/Shared UI/check_how_works.py" --report                # also list pages still without Help
```

Exit code 0 = no error; 1 = release error. Unchanged `help_missing` pages are listed as warnings, never errors. A page added in the release and classified `not_operational` is listed as a warning, so the reviewer confirms it really is not an operational page.

**Where it runs.**

- **Selection:** `release_selection.py` runs it on the commit being released, against the commit currently live (from the live image tag), before anything on AWS is changed. An error refuses the release.
- **Other services** (RF-One Web, Tips, workers): their releases follow the [Release Checklist](../Infrastructure/deploy/RELEASE_CHECKLIST.md), which requires the same command with `--since` the commit currently live, until their release scripts call it themselves.
- `test_check_how_works.py` tests the check itself; Selection's `test_how_works_http.py` verifies on the running application that each of the five tabs renders its link and that the target section exists.

The registry and the guide are released in the same commit as the code, so the Help a person reads is always the Help of the version they are using.

## 6. Applying the standard to an existing page

1. Write the page's section in its Domain guide (one section per page or tab, `id` = the page's code).
2. Make the Domain layout render the How Works link from the page's section code, with `data-how-works`.
3. Move the page from `help_missing` to `pages` in the registry.
4. Run the check; release code, guide and registry together.
