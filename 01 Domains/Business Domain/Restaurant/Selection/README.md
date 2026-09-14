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

Role relevance coefficients (weights) for Rome's Flavours' Server role, and any other Restaurant role's Configuration beyond Server, are not created by this task — see `ResumeScreening/RoleModel.md`, "Role relevance coefficients — not defined here."
