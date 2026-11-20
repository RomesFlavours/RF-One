# TASK 3A — Universal Selection Requirement Framework + Template Library: Implementation Report

## 1. What I implemented

A universal Requirement Framework that defines **what a restaurant is looking for**, completely separate from candidate data: a persistent `RequirementSet`/`Requirement` model any restaurant can own and edit, a reusable `RequirementTemplate`/`RequirementTemplateItem` library (multiple templates for the same nominal role), a clean clone-then-customize mechanism (editing a restaurant's set never touches its source template), a service layer, and a functional UI. Rome's Flavours is included only as example seed *data* (one template instantiation plus its own restaurant-specific traits) — the universal framework code never references it.

## 2. Main files changed

- New: `rfone_data_store/selection/core/requirement_model.py` (vocabulary: criticality/trainability/assessment-stage/category constants)
- New: `rfone_data_store/selection/requirements_service.py` (service layer — all CRUD/clone/deactivate operations)
- New: `rfone_data_store/selection/industry/restaurant_templates.py` (sample templates + Rome's Flavours example data — seed-only, never imported by the universal framework)
- New: migration `a7c3e9f2d5b8_add_selection_requirement_framework.py`
- Extended: `models.py` (+4 tables: `requirement_templates`, `requirement_template_items`, `requirement_sets`, `requirements`)
- Extended: `03 Software/Selection/app.py` (+9 routes), `templates/base.html` (+nav), new `templates/requirements_home.html`, `templates/requirement_set_detail.html`
- Extended: `rfone_data_store/selection_validation.py` (+15 checks, `_assert_requirement_framework`)

## 3. Requirement Set model

`RequirementSet`: `restaurant_id` (nullable FK, same convention as `Candidate`), `location_label` (free text, e.g. "Mount Dora" — not a FK to Restaurant's own Location schema), `target_role`, `name`, `description`, `version` (int, starts at 1), `is_active`, `created_at`/`updated_at`, `source_template_id` (nullable FK, traceability only). Fully restaurant-owned and independently editable once created — no live link back to its template.

## 4. Individual Requirement structure

`Requirement`: `name`, `description`, `category` (free text, UI offers `STARTER_CATEGORIES` as suggestions only), `criticality`, `trainability`, `assessment_stages` (JSON list), `evidence_positive`/`evidence_contrary`/`evidence_insufficient`/`guidance_notes`, `display_order`, `is_active`, timestamps. `RequirementTemplateItem` mirrors this shape exactly, so cloning is a direct field-by-field copy.

## 5. Criticality / trainability / assessment-stage model

- **Criticality:** `MUST_HAVE`, `PREFERRED`, `OPTIONAL`, `DISQUALIFIER`.
- **Trainability:** `TRAINABLE`, `NOT_TRAINABLE`, `PARTIALLY_TRAINABLE`, `UNKNOWN` (covers "not applicable" too) — never inferred by RF-One, always restaurant/template data.
- **Assessment stage(s):** `RESUME`, `PHONE_INTERVIEW`, `IN_PERSON_INTERVIEW`, `PRACTICAL_ASSESSMENT`, `REFERENCE_CHECK`, `OTHER` — stored as a JSON list, so one requirement can declare multiple stages.

All three are validated against the vocabulary by `requirements_service.py` (raises on an unrecognized value); `category` stays free-text by design (task §7: restaurants must customize freely).

## 6. Template-library implementation

`RequirementTemplate` + `RequirementTemplateItem`, both persisted (not Python constants) so they can be listed/read through the same service layer as Requirement Sets. Seed data (`industry/restaurant_templates.py`, called idempotently from the `/requirements` route) provides four representative templates: **High-Touch Hospitality Server**, **High-Volume Server**, **Sales-Oriented Server** (three different styles for the same SERVER role, proving task §9), and **Restaurant Assistant General Manager**.

## 7. Template → restaurant Requirement Set behavior

`instantiate_requirement_set_from_template()` copies every active template item's fields by value into new `Requirement` rows under a brand-new `RequirementSet`; nothing in the new set references the template's own rows. Verified directly: editing a cloned requirement's criticality leaves the source template's item unchanged (test 3A-I). `add_requirement`/`update_requirement`/`deactivate_requirement` all work identically on a from-template set and a from-scratch set — restaurants can add, remove (deactivate), and modify freely after cloning.

## 8. UI/API added

Flask routes (`03 Software/Selection/app.py`): `GET /requirements` (list sets + templates, create-new forms), `POST /requirements/new-custom`, `POST /requirements/new-from-template`, `GET /requirements/<id>` (view/edit one set and its requirements), `POST /requirements/<id>/update`, `POST /requirements/<id>/toggle-active`, `POST .../requirements/add`, `POST .../requirements/<id>/update`, `POST .../requirements/<id>/toggle-active`. Every route delegates to `requirements_service.py` — no business logic lives in the routes themselves. Two new templates (`requirements_home.html`, `requirement_set_detail.html`) reuse the existing Selection app's visual style; a small nav bar was added to `base.html` linking Candidates ↔ Requirement Sets. No candidate-matching UI was added.

## 9. Sample templates / Requirement Sets included

Four templates as listed in §6, seeded idempotently. One example Requirement Set, `seed_romes_flavours_requirement_set()`, clones the High-Touch Hospitality Server template for Rome's Flavours and adds its five specific non-negotiable attitude traits (teamwork, listens to instruction, applies coaching, humility, absence of counter-dependent behavior) as ordinary `Requirement` rows — `DISQUALIFIER` criticality, `NOT_TRAINABLE`, assessed at `PHONE_INTERVIEW` only, per task §10.

## 10. Targeted tests performed and results

- `python test_selection_engine.py` (`selection_validation.py`, incl. new `_assert_requirement_framework`): **61/61 checks passed** (46 pre-existing Task 2A/2B checks + 15 new Task 3A checks 3A-A through 3A-O, covering every item in the task's checklist including template cloning independence, multiple templates for one role, deactivation without deletion, per-restaurant isolation, and confirmation the universal modules never import the Rome's-Flavours-specific data module).
- `python test_batch_upload.py`: **19/19 checks passed** — confirms the existing résumé/candidate pipeline is unaffected.
- Full manual smoke test through the real Flask app (`test_client`): create-from-scratch, create-from-template, view/edit detail page, add a requirement, toggle active/inactive — all verified working end to end.
- Full Alembic migration chain verified to apply cleanly through the new head revision on a fresh database.

## 11. Known limitations directly relevant to Task 3A

- `version` on `RequirementSet` is a counter, not a content snapshot (task's own "practical minimal" instruction) — it proves *that* a set changed and by how many edits, but does not by itself let a future stage retrieve the exact historical content of an older version; that would need snapshotting when something (e.g. a future Fit Assessment) actually references a specific version.
- `location_label` is free text, not linked to Restaurant's own `Location` entity — deliberate, to avoid coupling Selection to Restaurant's location schema for what is, today, just a display label.
- Category is intentionally unvalidated free text; `STARTER_CATEGORIES` is UI guidance only, not an enforced list.
- No candidate matching, Fit Assessment, or scoring exists — by design, this task defines requirements only.
