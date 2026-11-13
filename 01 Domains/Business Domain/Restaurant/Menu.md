# Restaurant Menu Knowledge

## Visual Menu module and Training use

Product Owner approval, 2026-11-10: Visual Menu is an independent module, not a
Kitchen page or component. The module title is Visual Menu and its navigation
does not include Kitchen. It reads the shared recipe and photo data live from
Kitchen Recipes without storing copies.

The trainer maintains restaurant-specific presentation phrases and sales
phrases. Trainees access the same module through an assigned Training course;
servers access it through MyRF. Both are read-only, including direct POST/API
requests. Editing requires a Training trainer role, CSRF and a matching content
version. A Kitchen grant alone confers no Visual Menu access.

The Training catalog includes the assignable consultation content `visual-menu`.
Opening an assignment opens the shared module. It has no quiz, does not certify
learning, and is excluded from the scored whole-path quiz and its prerequisites.
The MyRF access code is an application permission, not a new conceptual Domain.

## Kitchen recipe storage extension — 2026-11-09

The Product Owner approved preparing Kitchen storage for the per-dish information
in `Cartel1.xlsx`: ingredients, intermediate preparations, quantities, procedures,
work time, costs and nutrition, plus organoleptic properties and an explicit
vegan/vegetarian/standard classification. Unknown properties remain unknown;
dietary class and sensory properties are not inferred from names. Ingredient
mass, cooked yield and portion size are distinct facts.

Subsequent explicit clarification: the recipe catalog is common to all restaurants.
Recipes and preparations are maintained once and may be referenced by multiple
restaurant Menu cards. The Product Owner authorized importing Cartel1.xlsx into
this shared catalog. Source conflicts remain visible and pending validation.

Future photographs document standard plating. Multiple
photos may belong to a recipe; a Menu card can select one photo of its linked
recipe as the standard image. This prepares Visual Menu consumption without
publishing photographs or changing current cards. Recipe and photo ownership
must remain consistent with the linked shared recipe; Menu cards stay restaurant-scoped.

Implementation: `03 Software/RF-One Data Store/KITCHEN.md`. Five Kitchen tables
are created in the existing canonical local PostgreSQL by revision `e4d520261110`,
with the common-catalog correction in `e5e620261110`.

## Approved initial scope

Product Owner approval, 2026-11-09: prepare separate dish cards for Winter Park
and Mount Dora, initially shrimp and pistachio fettuccine. Exclude prices.
One restaurant-specific card supports quick table-side consultation and a
deeper training section. This content repository does not certify learning.

## Restaurant separation

Each card belongs to exactly one existing Restaurant. The dish key may be
shared, but the restaurant/dish pair is unique. Menu-card portions, allergens,
modifications, preparation times and validation are independently maintained;
the underlying Kitchen recipe catalog is common, per the later PO clarification.
Never copy Winter Park recipe details into Mount Dora as confirmed facts.

## Content and evidence

Update approved 2026-11-09: consume Kitchen components and other recipe data
live, without persisting copies in Visual Menu. The two existing cards link to
the shared D125 recipe through `kitchen_visual_menu_links`. Existing copied
recipe fields were removed from their `content_json`; identity and provenance
remain. Allergen presence is inferred on each request from ingredient names,
recursing through linked preparations. Unknown compositions and unresolved or
circular references remain explicit; no absence or cross-contact guarantee is
inferred. Recipe validation is not implied by an inferred allergen.

Store title, category, guest presentation, documented ingredients, allergen
evidence, allowed modifications, training notes, questions and answers, pending
clarifications, source document/hash/page, photo provenance, content version,
validation status, validator and validation date. Missing information stays
unknown. Ingredients are not a validated allergen or cross-contact matrix.

The Mount Dora source names the dish Fettuccine Gamberi e Pistacchio; the Winter
Park source names it Fettuccine Shrimp & Pistacchio. Four shrimp, anchovy,
tomato and a ten-minute indication are documented only in Winter Park sources.
The course photograph may be used as a labelled reference for both cards;
its correspondence with each restaurant's current plating is unverified.

## Initial prepared artifacts

`03 Software/RF-One Data Store/prepare_visual_menu.py` generates the two local
English read-only card previews (explicit Product Owner request, 2026-11-09)
and structured seed content in
`output/visual-menu/`. Both pages include contextual modal help and restaurant
navigation. No application login, operational route or training assessment is
introduced by these previews.

Visible cards omit source-document references at the Product Owner's request.
Provenance remains internal metadata. Both restaurant cards are persisted in
the existing local PostgreSQL database under revision `e3c420261109`, content
version 2. Kitchen validation remains pending independently for each card.

The prepared relational schema uses the existing `restaurants.id` identity.
Import requires mapping both restaurant identities in the canonical local
database and an Alembic migration compatible with that database's actual
revision. No new permanent local database is permitted. The generator verifies
the schema using only a disposable in-memory database and never opens the
operational database.
