# Restaurant Selection — Industry Extension

**Version:** 0.1
**Status:** Draft (initial canonical foundation)
**Module:** Restaurant Domain / Selection (Industry Extension of the Selection Domain's Resume Screening capability — `01 Domains/Shared Domains/Selection/`)
**Origin:** TASK_SELECTION_001

---

## Purpose

This document is the **Restaurant Industry Extension** of Selection's Resume Screening sub-area (`01 Domains/Shared Domains/Selection/ResumeScreening/`). It adds Restaurant-specific interpretation — a normalized role catalog, role classification, and the first real Client/Role Configuration (Rome's Flavours' Server role) — on top of the generic, industry-agnostic Resume Screening engine. Nothing here is assumed by Selection Core; Selection Core does not know Restaurant exists (`01 Domains/Shared Domains/Selection/ResumeScreening/README.md`, "Domain architecture"). Selection is a top-level, transversal Domain — this Restaurant Industry Extension depends on Selection Core, never the reverse; Selection Core has no knowledge of this folder's existence.

This document does not redefine any Restaurant Domain knowledge (food cost, kitchen process, service sequence, purchasing, menu, restaurant operations — canonical under `01 Domains/Business Domain/Restaurant/`) — it only adds the Selection-specific interpretation of Restaurant roles.

---

## Normalized role catalog

```text
FOH (Front of House)
  SERVER
  BARTENDER
  HOST
  BUSSER
  FOOD_RUNNER
  FOH_SUPERVISOR
  FOH_MANAGER

BOH (Back of House)
  PREP_COOK
  LINE_COOK
  PIZZA_COOK
  DISHWASHER
  SOUS_CHEF
  CHEF
  BOH_MANAGER

OTHER
  GENERAL_MANAGER
```

A Work History record's `original_job_title` is mapped to one of these codes (`ExperienceAndTrajectory.md`'s "normalized role") by simple, transparent keyword matching (see the Runtime implementation, `rfone_data_store/selection/industry/restaurant.py`) — never silently guessed when the title does not clearly match; an unmatched title is left unclassified (`OTHER`/unknown) rather than forced into the nearest code.

### FOH Team Leader titles (SELECTION_FOH_TEAM_LEADER_001)

Product Owner decisions of 2026-10-03. **FOH Team Leader is the existing `FOH_SUPERVISOR` role (rank 3)** — no new catalog code; it is shown as "FOH Supervisor / Team Leader".

- **Always `FOH_SUPERVISOR`** (the title names the front of house): FOH Team Leader, Front of House Team Leader, FOH Supervisor, Floor Supervisor, capo sala, caposala, responsabile di sala.
- **Generic coordination titles** — Team Leader, Team Lead, Shift Leader, Shift Lead, Floor Leader, and any other "Supervisor" (bare, Shift, Restaurant, Kitchen, Warehouse Supervisor…; Product Owner correction of 2026-10-03: a bare "Supervisor" is no longer FOH by itself) — are `FOH_SUPERVISOR` **only when the résumé ties the experience to the dining room**: the title itself says so (FOH, front of house, sala, or server/waiter/host/runner), or a duty describes coordinating servers, hosts, runners or table service. Working in a restaurant is not enough: it may be the kitchen. A title mentioning the kitchen, duties coordinating only non-dining-room staff (kitchen, warehouse, …), duties mentioning both dining-room and kitchen staff, or no context at all → the title is kept as written, no role is assigned, and a question asks which team and area it was (to be clarified).
- **Kitchen Supervisor** is not FOH and adds no FOH or supervisory months; no existing kitchen role matches its definition (`BOH_MANAGER` is a Kitchen Manager), so the title is kept and clarified.
- **Chef de rang** is a dining-room server: `SERVER`, never kitchen.
- **Unchanged for now:** Head Waiter, Maître, Captain, Lead Server.

A recognized title is the **declared** role. It does not by itself show the coordination duties actually performed; reading those duties is a separate, later step, and the candidate page says so.

---

## The target role belongs to the application (SELECTION_FOH_TEAM_LEADER_001)

The role a résumé is screened for is the **application's target role**, chosen by the operator at upload (single or batch, mandatory, no preselection; one choice for the whole batch) and saved on that application — the same person may apply for different roles. Supported today: `SERVER` (Server) and `FOH_SUPERVISOR` (FOH Team Leader). The résumé never sets it and nothing defaults to Server: an application with no target role, or an unsupported one, shows the role-independent analysis only and asks for the target role to be clarified. Existing applications keep the value they already have.

**Document vs application.** Uploading a résumé already imported (same document) for a target role it has no application for creates a new application for that role: the document (file, text) is reused and its extracted facts are copied without re-reading into the snapshot the new application is tied to (one application per snapshot). The earlier application — role, notes, stage, outcome — is untouched, and each application keeps its own. The same document for the same target role is reported as a duplicate and creates nothing. The person is resolved by the existing identity rules (identical email or phone); otherwise the new application gets name-match suggestions to verify, never an automatic merge.

## Rome's Flavours FOH Team Leader Role Configuration

```text
Target:             FOH_SUPERVISOR (shown as "FOH Team Leader")
Equivalent:         none (direct experience = roles read as FOH_SUPERVISOR)
Propedeutic:        SERVER (and its catalog equivalents WAITER, WAITRESS, DINING_SERVER), BARTENDER, HOST
Adjacent:           none
Transitions to investigate (neutral question, backed by the résumé text):
  BOH        -> FOH Team Leader
  MANAGEMENT -> FOH Team Leader
```

No weights, thresholds or scores (`ResumeScreening/RoleModel.md`).

---

## Rome's Flavours Server Role Configuration

The first concrete `RoleConfiguration` (`ResumeScreening/RoleModel.md`) — a Client + Role Configuration for Rome's Flavours' `SERVER` target role:

```text
Target:
  SERVER

Equivalent role names:
  WAITER
  WAITRESS
  DINING_SERVER

Propedeutic:
  BARTENDER
  FOOD_RUNNER
  BUSSER
  HOST

Adjacent:
  RETAIL_SALES
  HOTEL_GUEST_SERVICE
  CUSTOMER_SERVICE

Transitions to investigate:
  BOH -> SERVER
  MANAGEMENT -> SERVER
  NON_HOSPITALITY -> SERVER
```

A transition is raised only for a role this extension **positively** classifies into the category (`ResumeScreening/ExperienceAndTrajectory.md`, "A transition needs positive evidence"). For `NON_HOSPITALITY` no role is classified yet (`NON_HOSPITALITY_ROLES` is empty in `rfone_data_store/selection/industry/restaurant.py`), so that transition cannot appear on a real résumé until such roles are defined; a missing or unrecognized title is "to be clarified" instead. `HOTEL_GUEST_SERVICE` is hotel work, i.e. hospitality, and is never non-hospitality.

These transitions generate a `ROLE_TRANSITION` Flag (detail code `BOH_TO_FOH` for the BOH case — `ResumeScreening/FlagsAndIndicators.md`, "Initial types") with a suggested, motive-neutral interview question. They never cause automatic rejection (`ResumeScreening/ExperienceAndTrajectory.md`, "Do not infer motive").

---

## Role classification for Indicators

The Restaurant extension supplies the classification `ExperienceAndTrajectory.md`'s aggregate Indicators need but Selection Core cannot define itself:

- **Customer-facing roles:** every `FOH` role above (Server, Bartender, Host, Busser, Food Runner, FOH Supervisor, FOH Manager).
- **Commercial/sales-exposure roles:** Server, Bartender (direct upsell/check-total responsibility in a restaurant context).
- **Supervisory roles:** FOH Supervisor, FOH Manager, Sous Chef, Chef, BOH Manager, General Manager.

These lists are Restaurant-specific judgment calls, kept here rather than in Selection Core precisely so a different industry can supply its own without touching the engine.

---

## Seniority, for trajectory detection

A coarse seniority ranking, used only to detect a lateral move vs. an apparent increase/decrease in responsibility (`ResumeScreening/ExperienceAndTrajectory.md`, "Career trajectory") — never used to rank candidates against each other:

```text
1  DISHWASHER, BUSSER, HOST, PREP_COOK
2  FOOD_RUNNER, SERVER, BARTENDER, LINE_COOK, PIZZA_COOK
3  SOUS_CHEF, FOH_SUPERVISOR
4  CHEF, FOH_MANAGER, BOH_MANAGER
5  GENERAL_MANAGER
```

This is a Restaurant-only convenience for trajectory detection, not a Core concept, not a compensation scale, and not exposed to the evaluator as a "level."

---

## Not decided here

Role relevance coefficients (weights) for Rome's Flavours' Server and FOH Team Leader roles, and any other Restaurant role's Configuration beyond these two, are not created here — see `ResumeScreening/RoleModel.md`, "Role relevance coefficients — not defined here."
