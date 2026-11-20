"""Restaurant — Wines (RESTAURANT_WINES_FIRST_RELEASE_001).

Module of the Restaurant Business Domain:

  * `wine_types`  — the wine type registry (standard name + alternative
    names, never the same type twice under two names);
  * `catalog`     — the catalog of purchasable wines ("Availability"), not
    physical stock;
  * `wine_lists`  — the Wine lists of each Entity (`LegalEntity`, read only),
    versioned by effective date, with their prices;
  * `pricing`     — the one implementation of the `Wine.xlsb` price formula.

Out of scope for this release: inventory, purchasing, wine import/upload,
AI reading or selection, POS and sales analysis.
"""
