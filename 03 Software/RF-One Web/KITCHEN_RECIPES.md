# Recipes and Preparations

## Plating image and description — 2026-11-10

Each recipe/preparation has a Plating button opening an image upload and a
free-text description modal. Description reuses `plating_instructions`; images
reuse `kitchen_recipe_photos`, with no new schema. Uploaded files are validated by
actual decoded format (JPEG/PNG/WebP), max 10 MB/40 megapixels, stored with opaque
names in local `output/kitchen-plating`, and served only through authenticated
RECIPES access. The latest Kitchen plating upload is the current image; original
photos remain available as history. Existing Menu links for the same shared
recipe select the new image. No new links or Menu cards are created.

Saves use existing CSRF and optimistic recipe revision controls. Description-only
saves keep the current image; Cancel applies nothing. Failed transactions remove
any newly written orphan file. Existing photo bytes are never overwritten.

## Exclusive composition source — 2026-11-10

PO correction: each composition row can contain a Component or a Preparation,
never both. Selecting either source clears the opposite selection without
changing grams/instructions. The server rejects dual-source payloads atomically.
Imported dual-source rows remain intact until edited, are visibly flagged and
must have one selection cleared before composition can be saved. No implicit
choice or data cleanup is performed when opening a recipe. Standalone instruction
rows remain valid. Page and modal help explain this rule.

Approved by the Product Owner on 2026-11-10: replace the Recipes shell with two
expandable sections, Recipes and Preparations. Each section has a New button;
each record has Edit (the same name/category dialog) and Components (composition
dialog). Keep English Kitchen labels and explain the page and both dialogs in
contextual How Works. Existing RECIPES access protects every page/API/write.

Use the existing shared Kitchen recipe identity and `kind` (dish/preparation).
Add nullable category_id referencing the Category configuration list and an
optimistic revision counter. Category choices come from Configuration; archived
categories remain readable on existing records. No category is inferred or seeded
onto existing records. Add nullable component_item_id to composition lines, using
the existing Components configuration identity. Imported text and source evidence
remain available; unmatched imported references must survive opening/saving.

Composition columns: Components, Preparation used, Grams, Instructions. Repeated
components/preparations are permitted. Standalone instructions are preserved.
Actual work time is edited separately in minutes, excluded from gram totals.
Save applies the complete modal draft in one transaction; Cancel/close applies
nothing. Existing line IDs and unchanged source/cost/nutrition values survive;
changed composition invalidates derived cached totals rather than displaying stale
cost/nutrition as current. Recipe source_payload remains the original evidence.
Do not generate or publish Menu content, change photos, or invent missing costs.

Reject invalid categories/components/preparations, negative/nonfinite quantities,
foreign line IDs, duplicate row IDs, stale saves and recursive preparation use.
Preserve original instruction-only rows and synchronize imported step duplicates
when editing their matching component notes. New recipe codes are generated
internally using a per-draft key so retrying a creation cannot duplicate it.
Retain page sections, scroll, row and modal draft through validation and help.

Schema: revision e8b920261110, after e7a820261110. Local schema setup is additive;
existing recipe content is not rewritten by the migration.
