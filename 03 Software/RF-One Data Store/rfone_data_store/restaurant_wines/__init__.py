"""Restaurant — Wines (RESTAURANT_WINES_FIRST_RELEASE_001).

Module of the Restaurant Business Domain:

  * `wine_types`  — the wine type registry (standard name + alternative
    names, never the same type twice under two names);
  * `catalog`     — the catalog of purchasable wines ("Availability"), not
    physical stock;
  * `wine_lists`  — the Wine lists of each Entity (`LegalEntity`, read only),
    versioned by effective date, with their prices;
  * `pricing`     — the one implementation of the `Wine.xlsb` price formula;
  * `drink_card`  — the printable drink card of a site (WINES_DRINK_CARD_001):
    descriptions, pairings with the active Kitchen menu, mineral waters and
    print settings; `drink_card_pdf` lays it out, `drink_card_ai` asks the
    AI for proposals.

Out of scope: inventory, purchasing, wine import/upload, AI selection of
wines, beers, POS and sales analysis.
"""
