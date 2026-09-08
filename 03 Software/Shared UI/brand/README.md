# Brand assets

Canonical, application-independent location for RF-One's official visual identity assets. **RF-One owns this branding — no individual app (Tips, Selection, InvoiceIntake, ...) owns or duplicates it; each app only consumes it.**

- `logos/` — the official RF-One logo, in its current/official version. **Currently empty: no official RF-One logo file exists in the repository yet.** Do not add a placeholder or an invented logo here — add the real, approved asset when it becomes available. Consuming apps pick it up automatically through their own shared-asset mechanism (e.g. `03 Software/Tips/app.py`'s `shared_brand_logo` route) — no per-app copy is made.
- `icons/` — alternate/small-format marks (e.g. favicon), when needed.

A sibling `css/` folder can be added under `03 Software/Shared UI/` for genuinely cross-app stylesheets if/when one is needed — not created speculatively. Module-specific CSS (e.g. Tips' own layout/colors) stays in that module's own `static/css/`.
