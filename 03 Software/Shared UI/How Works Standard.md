# How Works Standard

**Code:** UI_HOW_WORKS_001
**Status:** standing, mandatory. Product Owner instruction, 2026-11-02.
**Applies to:** every operational page of every RF-One Domain and Module, in every RF-One app (RF-One Web, Selection, Tips, Training, Invoice Intake and any future app on the RF-One login), and every release of them.
**Authority:** this is the **one normative text** for How Works. `CLAUDE.md`, `AGENTS.md`, `UI Rules.md` §6 and the [Release Checklist](../Infrastructure/deploy/RELEASE_CHECKLIST.md) refer to it and do not repeat it.

> MIEAF: every function explains how it works, in the same release in which it is published.

---

## 1. Every page has a contextual help link that opens a modal

**Product Owner rule (UI_CONTEXTUAL_HELP_001, 2026-11-05), modelled on the "How Selection works" link.** Every RF-One page has a contextual help, reached through one consistent link that opens a **modal** on the page itself (it does not navigate away, so nothing on the page is lost).

| Page | Link label | What the modal explains |
|---|---|---|
| General RF-One Home | `How RF-One works` | RF-One and how to move around it |
| Home (entry page) of a Domain or Module | `How <Module> works` | purpose of the module, how it works, its operating flow, and what its home page shows |
| Every other page (lists, details, forms, settings, administration, services) | `How this page works` | that page only: what it is for, what the person can do, meaning of fields and buttons, consequences of the actions, next steps |

- **Page-specific, never generic.** The module explanation is never a substitute for a page's own explanation.
- **Real behaviour, plain English.** The help describes what is actually available (§2), in clear English for the user, without unnecessary technical detail. *Open decision:* how this English-text instruction combines with UI_DEVELOPMENT_LANGUAGE_001 (Italian local UI) — until the Product Owner decides, the help is English in local and shared use, while the page labels it quotes stay as the page shows them.
- **Permissions.** The help is rendered inside the page: whoever may open the page may read its help, and nobody else. A part of the help that describes a role-restricted button or section carries the same condition as that button or section.
- **Position.** Top right of the page's working area: at the right end of the app's navigation tabs where the layout has them (Selection, Tips — the "How Selection works" placement), otherwise in a right-aligned row directly above the page content. Same place on every page of an app.
- **Behaviour.** The link is a button (`aria-haspopup="dialog"`). The modal is a native `<dialog>`: it opens with focus on its close X, keeps keyboard focus inside, closes with Escape, the X at its top right (always visible while the help scrolls), the **Close** button or a click outside; focus returns to the link. It never submits, reloads or clears anything. Below 640 px it fills the screen.
- **Marker.** The link carries `data-how-works="<section>"`. The automatic check (§5) relies on it.
- **One component, one implementation.** `03 Software/Shared UI/help/_how_works.html` (link + modal, styles and script included). Each app keeps a byte-identical copy as `templates/_how_works.html`, like `rf-one.css`; the check (§5) fails when a copy differs. The layout of each app renders the link and the modal; a page only declares, at top level of its template:

  ```jinja
  {% set help_section = "<section>" %}   {# content: templates/help/<section>.html #}
  {% set help_title = "<Module>" %}      {# only on a Home: "How <Module> works" #}
  ```

- **Content.** `templates/help/<section>.html`, one fragment per page (or per tab, when one template renders tabs that are different pages for the person), wrapped in `<section id="help-<section>">`. Existing full guides (`*how_it_works*` pages) stay available, agree with the sections, and preferably include them so there is one source.

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
| `pages` | Operational page with its help target: `"<template>": "help/<section>.html#help-<section>"` (a list when one template renders several tabs). An older guide target `"<guide template>#<section id>"` is still read, but every page is moved to its own modal section. |
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
| Modal section | for a `help/<section>.html` target: the page does not declare `{% set help_section = "<section>" %}`, or the section has fewer than 300 visible characters |
| Component | an app's `templates/_how_works.html` differs from `Shared UI/help/_how_works.html` |
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

1. Read the page, its route and its permission conditions; write `templates/help/<section>.html` for that page.
2. Declare `help_section` (and `help_title` on a Home) at the top of the page template; remove any older per-page help link the layout now replaces.
3. Move the page from `help_missing` to `pages` in the registry, with target `help/<section>.html#help-<section>`.
4. Verify: the page renders the link and its own section (the app's `test_how_works_*` HTTP test), the modal opens and closes, the text matches the page. Run the check; release code, help and registry together.

**Every creation or change of a page includes checking, and where needed updating, its help. The work is not complete while the interface and its explanation do not match.**


## 1.1 Contextual help in every modal (Product Owner, 2026-11-03)

Every modal a person uses has a visible **?** help control. It opens the exact anchored guide section explaining **that modal**, inside the Domain/Module guide; never the guide top or an unrelated generic page section. The control may be compact, but has an accessible name explaining its purpose.

Opening or closing help preserves the modal, unsaved fields, draft rule, selection, list position and focus. Help must not submit, confirm or discard anything. Every page continues to have its page-specific How Works control. A modal is not a standalone page for the template registry, but it is **not exempt** from this contextual-help requirement.

Guide anchors are stable and specific to the modal/workflow. Explain the operations actually available, including simulation, confirmation and when data become effective. Update the help with the same functional change. Follow UI_DEVELOPMENT_LANGUAGE_001: Italian in the PO local interface (Come funziona / ?), English in the shared/release interface (How Works / ?). Preserve the Italian local copy when preparing publication.
