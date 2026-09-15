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
    DEFAULT_TRUST_THRESHOLD,
    FIELD_REVIEW_AMBIGUOUS,
    FIELD_REVIEW_CORRECT,
    FIELD_REVIEW_INCORRECT,
    SupplierFormatTrainingStore,
    TRUST_STATE_DEGRADED,
    TRUST_STATE_TRAINING,
    TRUST_STATE_UNTRAINED,
    TRUST_STATE_VALIDATED,
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


def test_set_trust_state_is_explicit_never_automatic(result: Result, tmp_dir: str) -> None:
    """Task requirements 10/11: promotion is a human/Product-Owner decision
    (`set_trust_state()`), never something `record_observation()` does on
    its own, and no universal N/threshold is enforced by this module --
    `set_trust_state()` accepts the caller's decision as-is."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Prime Line Distributors", source_format="OCR/Direct", was_normalized=True)
        promoted = store.set_trust_state("Prime Line Distributors", "OCR/Direct", TRUST_STATE_TRAINING)
        result.check("set_trust_state moves a pair to TRAINING when explicitly told to", promoted.trust_state == TRUST_STATE_TRAINING)

        promoted = store.set_trust_state("Prime Line Distributors", "OCR/Direct", TRUST_STATE_VALIDATED)
        result.check("set_trust_state moves a pair to VALIDATED when explicitly told to", promoted.trust_state == TRUST_STATE_VALIDATED)

        raised = False
        try:
            store.set_trust_state("Prime Line Distributors", "OCR/Direct", "NOT_A_REAL_STATE")
        except ValueError:
            raised = True
        result.check("set_trust_state rejects an unknown trust_state", raised)

        raised = False
        try:
            store.set_trust_state("Never Observed Supplier", "OCR/Direct", TRUST_STATE_TRAINING)
        except ValueError:
            raised = True
        result.check("set_trust_state rejects a (Supplier, Format) pair with no observations yet", raised)
    finally:
        store.close()


def test_record_observation_never_promotes_on_its_own(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True)
        for _ in range(10):
            store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True, signature="S1D1N1T1-L3")
        obs = store.get("Costco Wholesale", "OCR/Direct")
        result.check("many consecutive NORMALIZED observations alone never promote past UNTRAINED", obs.trust_state == TRUST_STATE_UNTRAINED)
    finally:
        store.close()


def test_validated_pair_demoted_on_layout_change(result: Result, tmp_dir: str) -> None:
    """Task requirement 12: a VALIDATED pair whose layout shape changes
    materially is demoted to DEGRADED automatically -- the one trust_state
    transition this module makes on its own."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True, signature="S1D1N1T1-L20")
        store.set_trust_state("Costco Wholesale", "OCR/Direct", TRUST_STATE_VALIDATED)

        # A materially different shape: the date is no longer being found at all.
        obs = store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=False, signature="S1D0N1T1-L18")
        result.check("a VALIDATED pair is demoted to DEGRADED when its layout shape changes", obs.trust_state == TRUST_STATE_DEGRADED)
    finally:
        store.close()


def test_validated_pair_not_demoted_by_line_count_alone(result: Result, tmp_dir: str) -> None:
    """A bigger or smaller invoice (different `line_count`) is normal
    variation, not a layout change -- only the field-presence shape matters
    (Task requirement 12's own "materially diverso", not any difference)."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Prime Line Distributors", source_format="PDF-Text/Direct", was_normalized=True, signature="S1D1N1T1-L3")
        store.set_trust_state("Prime Line Distributors", "PDF-Text/Direct", TRUST_STATE_VALIDATED)

        obs = store.record_observation(supplier_name="Prime Line Distributors", source_format="PDF-Text/Direct", was_normalized=True, signature="S1D1N1T1-L9")
        result.check("same field-presence shape, different line_count -> stays VALIDATED", obs.trust_state == TRUST_STATE_VALIDATED)
    finally:
        store.close()


def test_trust_state_independent_of_normalized_human_counts(result: Result, tmp_dir: str) -> None:
    """Task requirement 5/Purchased/README.md distinction: SOURCE FORMAT
    trust (`trust_state`) and per-document NORMALIZED/HUMAN outcomes are
    tracked side by side but are never the same thing -- a HUMAN-heavy
    stretch of observations must not, by itself, change trust_state."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=True)
        store.set_trust_state("Ben E. Keith Foods", "PDF-Text/Direct", TRUST_STATE_TRAINING)
        for _ in range(5):
            store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=False)
        obs = store.get("Ben E. Keith Foods", "PDF-Text/Direct")
        result.check("human_count reflects the HUMAN-heavy stretch", obs.human_count == 5)
        result.check("trust_state (TRAINING) is untouched by the HUMAN outcomes themselves", obs.trust_state == TRUST_STATE_TRAINING)
    finally:
        store.close()


def test_instacart_and_direct_are_distinct_training_units(result: Result, tmp_dir: str) -> None:
    """Task requirement 9: Costco direct != Costco via Instacart."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True)
        store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Instacart", was_normalized=False)
        result.check(
            "(Costco, OCR/Direct) and (Costco, OCR/Instacart) are distinct units",
            store.get("Costco Wholesale", "OCR/Direct").reviewed_count == 1 and store.get("Costco Wholesale", "OCR/Instacart").reviewed_count == 1,
        )
        result.check(
            "they are not merged just because the Supplier is the same",
            store.get("Costco Wholesale", "OCR/Direct").normalized_count == 1 and store.get("Costco Wholesale", "OCR/Instacart").human_count == 1,
        )
    finally:
        store.close()


def test_field_review_recorded_and_summarized(result: Result, tmp_dir: str) -> None:
    """Task requirement 5 (Human Review Model): field-level classification
    against the real document, never a silent correction."""

    store = _make_store(tmp_dir)
    try:
        store.record_field_review(
            supplier_name="Prime Line Distributors",
            source_format="OCR/Direct",
            document_reference="PL20200630125750_001.pdf",
            field_name="total",
            classification=FIELD_REVIEW_CORRECT,
            extracted_value="523.72",
            expected_value="523.72",
        )
        store.record_field_review(
            supplier_name="Prime Line Distributors",
            source_format="OCR/Direct",
            document_reference="PL20200602113022_001.pdf",
            field_name="total",
            classification=FIELD_REVIEW_INCORRECT,
            extracted_value="8.49",
            expected_value="468.47",
        )
        reviews = store.list_field_reviews(supplier_name="Prime Line Distributors")
        result.check("both field reviews are recorded", len(reviews) == 2)
        result.check("classification is stored as given, never auto-corrected", {r.classification for r in reviews} == {FIELD_REVIEW_CORRECT, FIELD_REVIEW_INCORRECT})

        summaries = {(s.supplier_name, s.source_format, s.field_name): s.counts for s in store.summarize_field_reviews()}
        counts = summaries[("Prime Line Distributors", "OCR/Direct", "total")]
        result.check("summary counts CORRECT and INCORRECT for this (Supplier, Format, field)", counts[FIELD_REVIEW_CORRECT] == 1 and counts[FIELD_REVIEW_INCORRECT] == 1)
        result.check("summary always reports every classification bucket, even at 0", counts[FIELD_REVIEW_AMBIGUOUS] == 0)
    finally:
        store.close()


def test_field_review_rejects_unknown_classification(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        raised = False
        try:
            store.record_field_review(
                supplier_name="Costco Wholesale",
                source_format="OCR/Direct",
                document_reference="CO2020-02-11.pdf",
                field_name="total",
                classification="LOOKS_FINE",  # not a real classification
            )
        except ValueError:
            raised = True
        result.check("an unknown field-review classification is rejected, not silently accepted", raised)
    finally:
        store.close()


def test_default_trust_threshold_is_5(result: Result, tmp_dir: str) -> None:
    """Task requirement 11: "Default operativo iniziale: 5 documenti
    consecutivi verificati corretti" — and requirement 9 of the test list."""

    store = _make_store(tmp_dir)
    try:
        result.check("DEFAULT_TRUST_THRESHOLD constant is 5", DEFAULT_TRUST_THRESHOLD == 5)
        result.check(
            "get_trust_threshold() returns the default (5) with no configuration at all",
            store.get_trust_threshold("Prime Line Distributors", "OCR/Direct") == 5,
        )
    finally:
        store.close()


def test_global_trust_threshold_override(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        store.set_trust_threshold(8)
        result.check(
            "a global override applies to every (Supplier, Format) pair with no pair-specific override",
            store.get_trust_threshold("Costco Wholesale", "OCR/Direct") == 8
            and store.get_trust_threshold("Ben E. Keith Foods", "PDF-Text/Direct") == 8,
        )
    finally:
        store.close()


def test_per_supplier_format_trust_threshold_override(result: Result, tmp_dir: str) -> None:
    """Task requirement 10 of the test list: "threshold override works" —
    and requirement 14: "global default; eventualmente override
    Supplier+Format"."""

    store = _make_store(tmp_dir)
    try:
        store.set_trust_threshold(3, supplier_name="Costco Wholesale", source_format="OCR/Direct")
        result.check(
            "a pair-specific override applies only to that exact pair",
            store.get_trust_threshold("Costco Wholesale", "OCR/Direct") == 3,
        )
        result.check(
            "an unrelated pair still gets the global default (unchanged, 5)",
            store.get_trust_threshold("Costco Wholesale", "OCR/Instacart") == 5,
        )

        raised = False
        try:
            store.set_trust_threshold(3, supplier_name="Costco Wholesale")  # source_format missing
        except ValueError:
            raised = True
        result.check("supplier_name without source_format (or vice versa) is rejected", raised)

        raised = False
        try:
            store.set_trust_threshold(0)
        except ValueError:
            raised = True
        result.check("a non-positive threshold is rejected", raised)
    finally:
        store.close()


def test_five_consecutive_correct_makes_a_training_pair_eligible(result: Result, tmp_dir: str) -> None:
    """Task requirement 12 / test list requirement 11: "5 consecutive
    correct can become eligible"."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True)
        store.set_trust_state("Costco Wholesale", "OCR/Direct", TRUST_STATE_TRAINING)

        for _ in range(4):
            store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True)
        obs = store.get("Costco Wholesale", "OCR/Direct")
        eligible, reason = store.is_eligible_for_validation("Costco Wholesale", "OCR/Direct")
        result.check("after only 5 total observations, reviewed_count/streak both reach 5", obs.reviewed_count == 5 and obs.consecutive_correct_count == 5)
        result.check("is_eligible_for_validation() is True once the default threshold (5) is met", eligible and "5" in reason)

        promoted = store.promote_if_eligible("Costco Wholesale", "OCR/Direct")
        result.check("promote_if_eligible() actually promotes an eligible pair to VALIDATED", promoted.trust_state == TRUST_STATE_VALIDATED)
    finally:
        store.close()


def test_recent_incorrect_prevents_promotion(result: Result, tmp_dir: str) -> None:
    """Task requirement 12 / test list requirement 12: "recent incorrect
    prevents promotion" — a HUMAN observation resets the streak, so
    reaching a high reviewed_count is never enough by itself."""

    store = _make_store(tmp_dir)
    try:
        store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=True)
        store.set_trust_state("Ben E. Keith Foods", "PDF-Text/Direct", TRUST_STATE_TRAINING)
        for _ in range(3):
            store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=True)
        # A HUMAN observation right before the streak would have reached 5.
        store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=False)
        store.record_observation(supplier_name="Ben E. Keith Foods", source_format="PDF-Text/Direct", was_normalized=True)

        obs = store.get("Ben E. Keith Foods", "PDF-Text/Direct")
        result.check("reviewed_count is high (6) but the streak reset", obs.reviewed_count == 6 and obs.consecutive_correct_count == 1)
        eligible, reason = store.is_eligible_for_validation("Ben E. Keith Foods", "PDF-Text/Direct")
        result.check(
            "not eligible despite a high reviewed_count — the streak, not just the count, matters",
            not eligible and "consecutive correct" in reason,
        )

        raised = False
        try:
            store.promote_if_eligible("Ben E. Keith Foods", "PDF-Text/Direct")
        except ValueError:
            raised = True
        result.check("promote_if_eligible() refuses (raises) rather than silently no-op or promote anyway", raised)
    finally:
        store.close()


def test_promotion_requires_training_state_first(result: Result, tmp_dir: str) -> None:
    """Task requirement 12: promotion needs "human confirmation / explicit
    approval dove previsto" — an UNTRAINED pair, however many correct
    observations it has, is never eligible until a human explicitly moves
    it to TRAINING first."""

    store = _make_store(tmp_dir)
    try:
        for _ in range(10):
            store.record_observation(supplier_name="Prime Line Distributors", source_format="OCR/Direct", was_normalized=True)
        eligible, reason = store.is_eligible_for_validation("Prime Line Distributors", "OCR/Direct")
        result.check("still UNTRAINED (never explicitly moved to TRAINING) -> not eligible", not eligible and "TRAINING" in reason)
    finally:
        store.close()


def test_degraded_pair_needs_explicit_training_before_re_eligible(result: Result, tmp_dir: str) -> None:
    """Task requirement 13: "Dopo DEGRADED: serve nuova verifica/training"
    — a DEGRADED pair is not directly eligible again; a human must move it
    back to TRAINING first (same discipline as the initial promotion)."""

    store = _make_store(tmp_dir)
    try:
        for _ in range(5):
            store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True, signature="S1D1N1T1-L5")
        store.set_trust_state("Costco Wholesale", "OCR/Direct", TRUST_STATE_TRAINING)
        store.promote_if_eligible("Costco Wholesale", "OCR/Direct")

        # A real error while VALIDATED -- Task requirement 13.
        degraded = store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=False, signature="S1D1N1T1-L5")
        result.check("a real HUMAN outcome while VALIDATED demotes to DEGRADED (not just a layout change)", degraded.trust_state == TRUST_STATE_DEGRADED)

        eligible, reason = store.is_eligible_for_validation("Costco Wholesale", "OCR/Direct")
        result.check("a DEGRADED pair is not directly eligible again", not eligible and "DEGRADED" in reason)

        store.set_trust_state("Costco Wholesale", "OCR/Direct", TRUST_STATE_TRAINING)
        for _ in range(5):
            store.record_observation(supplier_name="Costco Wholesale", source_format="OCR/Direct", was_normalized=True, signature="S1D1N1T1-L5")
        eligible_again, _ = store.is_eligible_for_validation("Costco Wholesale", "OCR/Direct")
        result.check("eligible again once explicitly retrained with a fresh correct streak", eligible_again)
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
            test_set_trust_state_is_explicit_never_automatic,
            test_record_observation_never_promotes_on_its_own,
            test_validated_pair_demoted_on_layout_change,
            test_validated_pair_not_demoted_by_line_count_alone,
            test_trust_state_independent_of_normalized_human_counts,
            test_instacart_and_direct_are_distinct_training_units,
            test_field_review_recorded_and_summarized,
            test_field_review_rejects_unknown_classification,
            test_default_trust_threshold_is_5,
            test_global_trust_threshold_override,
            test_per_supplier_format_trust_threshold_override,
            test_five_consecutive_correct_makes_a_training_pair_eligible,
            test_recent_incorrect_prevents_promotion,
            test_promotion_requires_training_state_first,
            test_degraded_pair_needs_explicit_training_before_re_eligible,
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
