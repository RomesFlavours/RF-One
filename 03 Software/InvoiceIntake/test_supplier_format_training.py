#!/usr/bin/env python
"""Tests for `supplier_format_training.py` (the foundation only — Purchased
Invoice Intake — Improve Generic Parser and Prepare Supplier Format
Training, §8). Confirms observations are recorded correctly and that
`trust_state` is never anything but `UNTRAINED` — this module never
auto-validates a supplier.

Usage:
    python test_supplier_format_training.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supplier_format_training import (  # noqa: E402
    SupplierFormatTrainingStore,
    TRUST_STATE_UNTRAINED,
    layout_signature,
)


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


def _make_store(tmp_dir: str) -> SupplierFormatTrainingStore:
    return SupplierFormatTrainingStore(os.path.join(tmp_dir, f"training_test_{uuid.uuid4().hex}.db"))


def test_first_observation_recorded(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        obs = store.record_observation(supplier_name="Costco", source_format="OCR", was_normalized=True, signature="S1D1N0T1-L0")
        result.check("reviewed_count starts at 1", obs.reviewed_count == 1)
        result.check("normalized_count is 1 for a NORMALIZED observation", obs.normalized_count == 1)
        result.check("human_count is 0", obs.human_count == 0)
        result.check("trust_state is always UNTRAINED, never auto-promoted", obs.trust_state == TRUST_STATE_UNTRAINED)
    finally:
        store.close()


def test_observations_accumulate_per_supplier_and_format(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco", source_format="OCR", was_normalized=True)
        store.record_observation(supplier_name="Costco", source_format="OCR", was_normalized=False)
        store.record_observation(supplier_name="Costco", source_format="OCR", was_normalized=True)
        obs = store.get("Costco", "OCR")
        result.check("reviewed_count accumulates across calls", obs.reviewed_count == 3)
        result.check("normalized_count accumulates", obs.normalized_count == 2)
        result.check("human_count accumulates", obs.human_count == 1)
        result.check("trust_state remains UNTRAINED after multiple observations too", obs.trust_state == TRUST_STATE_UNTRAINED)
    finally:
        store.close()


def test_supplier_and_format_are_a_distinct_unit(result: Result, tmp_dir: str) -> None:
    """Task requirement 8: Supplier + Source Format is the training unit,
    not the Supplier alone -- the same Supplier via a different acquisition
    method is tracked separately."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco", source_format="OCR", was_normalized=True)
        store.record_observation(supplier_name="Costco", source_format="PDF-Text", was_normalized=True)
        result.check("(Costco, OCR) and (Costco, PDF-Text) are tracked as separate units", store.get("Costco", "OCR").reviewed_count == 1 and store.get("Costco", "PDF-Text").reviewed_count == 1)

        store.record_observation(supplier_name="Trader Joe's", source_format="OCR", was_normalized=True)
        all_rows = store.list_all()
        result.check("3 distinct (Supplier, Format) units are recorded", len(all_rows) == 3)
    finally:
        store.close()


def test_layout_signature_is_a_coarse_shape_only(result: Result) -> None:
    sig_complete = layout_signature(supplier_found=True, date_found=True, number_found=True, total_found=True, line_count=3)
    sig_missing_date = layout_signature(supplier_found=True, date_found=False, number_found=True, total_found=True, line_count=3)
    result.check("a different field-presence shape produces a different signature", sig_complete != sig_missing_date)
    result.check("the same shape produces the same signature", sig_complete == layout_signature(supplier_found=True, date_found=True, number_found=True, total_found=True, line_count=3))


def test_never_auto_promotes(result: Result, tmp_dir: str) -> None:
    """Task requirement 8: "NON auto-validare ancora nessun supplier" --
    even after many consecutive NORMALIZED observations, trust_state stays
    UNTRAINED. No N, no threshold, no promotion logic exists here."""

    store = _make_store(tmp_dir)
    try:
        for _ in range(50):
            store.record_observation(supplier_name="Trader Joe's", source_format="OCR", was_normalized=True)
        obs = store.get("Trader Joe's", "OCR")
        result.check("50 consecutive NORMALIZED observations still leave trust_state UNTRAINED", obs.trust_state == TRUST_STATE_UNTRAINED)
        result.check("reviewed_count correctly reflects all 50 observations", obs.reviewed_count == 50)
    finally:
        store.close()


def main() -> int:
    tmp_dir = tempfile.mkdtemp(prefix="supplier_format_training_test_")
    result = Result()
    try:
        for test_fn in (
            test_first_observation_recorded,
            test_observations_accumulate_per_supplier_and_format,
            test_supplier_and_format_are_a_distinct_unit,
            test_never_auto_promotes,
        ):
            test_fn(result, tmp_dir)
        test_layout_signature_is_a_coarse_shape_only(result)
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Supplier Format Training foundation tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Supplier Format Training foundation tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
