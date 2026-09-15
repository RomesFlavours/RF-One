#!/usr/bin/env python
"""Canonical Supplier name cleanup ("Purchased Supplier Training — Phase 2",
§8: "Correggi il Supplier canonico esistente... NON cancellare il vecchio
valore").

A small, checked-in, idempotent maintenance script — not a one-off shell
command — so a known dirty name discovered in the future can just be added
to `CANONICAL_RENAMES` below and this re-run safely. Uses
`purchasing.repository.rename_supplier_canonical()` (renames a Supplier's
`name` IN PLACE, same `id`, so every existing `PurchaseDocument.supplier_id`
foreign key stays valid untouched, and records the old name as a
`SupplierAlias` before overwriting it — see that function's own docstring)
for every Restaurant that has a Supplier under the dirty name. Safe to
re-run: a Supplier already carrying the clean name is left alone.

Usage:
    python fix_supplier_canonical_names.py
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m
from rfone_data_store.purchasing import repository as repo

# (dirty name observed in real acquired data, clean canonical name).
# Illustrative/non-exhaustive: add a new pair here whenever a future
# Supplier Training phase finds another one — never remove an entry once
# real data may have depended on it.
CANONICAL_RENAMES: list[tuple[str, str]] = [
    ("PRIME LINE DISTRIBUTORS INVOICE", "Prime Line Distributors"),
]


def fix_supplier_canonical_names() -> list[str]:
    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    report: list[str] = []
    with session_factory() as session:
        for dirty_name, clean_name in CANONICAL_RENAMES:
            dirty_suppliers = session.scalars(select(m.Supplier).where(m.Supplier.name == dirty_name)).all()
            for supplier in dirty_suppliers:
                linked_documents = len(
                    session.scalars(
                        select(m.PurchaseDocument.id).where(m.PurchaseDocument.supplier_id == supplier.id)
                    ).all()
                )
                repo.rename_supplier_canonical(session, supplier.id, clean_name, source="Phase 2 canonical cleanup")
                report.append(
                    f"Supplier id={supplier.id} (restaurant_id={supplier.restaurant_id}): "
                    f"{dirty_name!r} -> {clean_name!r} ({linked_documents} PurchaseDocument(s) preserved)"
                )
        session.commit()
    return report


if __name__ == "__main__":
    changes = fix_supplier_canonical_names()
    if not changes:
        print("No dirty Supplier names found — nothing to do (already clean, or none of CANONICAL_RENAMES matched).")
    else:
        print(f"Renamed {len(changes)} Supplier(s):")
        for line in changes:
            print(f"  {line}")
    sys.exit(0)
