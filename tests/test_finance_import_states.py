from services.finance_import_states import (
    ALERT_STATUSES,
    BATCH_STATUSES,
    BUSINESS_CLASSIFICATION_TYPES,
    CLASSIFICATION_TYPES,
    ILLEGAL_TRANSITION,
    INVALID_AXES,
    OCCURRENCE_OUTCOMES,
    RECONCILIATION_STATUSES,
    TARGET_REQUIRED,
    FinanceImportAxes,
    evaluate_finance_import_transition,
)


def _axes(**changes: str) -> FinanceImportAxes:
    values = {
        "batch_status": "staged",
        "classification_type": "pending",
        "reconciliation_status": "pending",
        "alert_status": "open",
    }
    values.update(changes)
    return FinanceImportAxes(**values)


def test_canonical_vocabularies_are_disjoint_by_axis() -> None:
    assert BATCH_STATUSES == {"staged", "completed", "failed"}
    assert OCCURRENCE_OUTCOMES == {"inserted", "skipped_existing"}
    assert RECONCILIATION_STATUSES == {"pending", "reconciled"}
    assert ALERT_STATUSES == {"open", "claimed", "resolved"}
    assert CLASSIFICATION_TYPES == {
        "pending",
        "client_receipt",
        "government_subsidy",
        "client_subsidy_return",
        "staff_salary",
        "staff_legacy_subsidy",
        "non_business_review",
    }
    assert BUSINESS_CLASSIFICATION_TYPES == {
        "client_receipt",
        "government_subsidy",
        "client_subsidy_return",
        "staff_salary",
        "staff_legacy_subsidy",
    }


def test_batch_can_only_leave_staged_for_a_terminal_status() -> None:
    completed = evaluate_finance_import_transition(_axes(), "stage", "completed")
    failed = evaluate_finance_import_transition(_axes(), "stage", "failed")

    assert completed.allowed
    assert completed.validated_axes == _axes(batch_status="completed")
    assert failed.allowed
    assert failed.validated_axes == _axes(batch_status="failed")
    assert not evaluate_finance_import_transition(
        _axes(batch_status="completed"), "stage", "failed"
    ).allowed


def test_normal_classification_only_leaves_pending() -> None:
    decision = evaluate_finance_import_transition(
        _axes(), "classify", "non_business_review"
    )

    assert decision.allowed
    assert decision.validated_axes == _axes(
        classification_type="non_business_review"
    )
    assert (
        evaluate_finance_import_transition(_axes(), "classify").refusal_reason
        == TARGET_REQUIRED
    )
    assert (
        evaluate_finance_import_transition(
            _axes(classification_type="client_receipt"),
            "classify",
            "staff_salary",
        ).refusal_reason
        == ILLEGAL_TRANSITION
    )


def test_reclassification_only_promotes_review_to_business_or_is_unchanged() -> None:
    promoted = evaluate_finance_import_transition(
        _axes(classification_type="non_business_review"),
        "reclassify",
        "client_receipt",
    )
    unchanged = evaluate_finance_import_transition(
        _axes(classification_type="client_receipt"),
        "reclassify",
        "client_receipt",
    )
    regression = evaluate_finance_import_transition(
        _axes(classification_type="client_receipt"),
        "reclassify",
        "non_business_review",
    )

    assert promoted.allowed
    assert unchanged.allowed
    assert not regression.allowed
    assert regression.refusal_reason == ILLEGAL_TRANSITION


def test_reconciliation_never_moves_back_to_pending() -> None:
    reconciled = evaluate_finance_import_transition(_axes(), "reconcile")
    repeated = evaluate_finance_import_transition(
        _axes(reconciliation_status="reconciled"), "reconcile"
    )

    assert reconciled.allowed
    assert reconciled.validated_axes == _axes(
        reconciliation_status="reconciled"
    )
    assert not repeated.allowed
    assert repeated.refusal_reason == ILLEGAL_TRANSITION


def test_duplicate_occurrence_does_not_change_canonical_axes() -> None:
    current = _axes(
        classification_type="client_receipt",
        reconciliation_status="reconciled",
        alert_status="resolved",
    )
    decision = evaluate_finance_import_transition(
        current, "duplicate_occurrence"
    )

    assert decision.allowed
    assert decision.occurrence_outcome == "skipped_existing"
    assert decision.validated_axes == current


def test_alert_lifecycle_claim_resolve_and_reopen() -> None:
    claimed = evaluate_finance_import_transition(_axes(), "claim")
    resolved = evaluate_finance_import_transition(
        claimed.validated_axes, "resolve"
    )
    reopened = evaluate_finance_import_transition(
        resolved.validated_axes, "reopen"
    )

    assert claimed.validated_axes == _axes(alert_status="claimed")
    assert resolved.validated_axes == _axes(alert_status="resolved")
    assert reopened.validated_axes == _axes(alert_status="open")


def test_invalid_or_cross_axis_values_are_stably_rejected() -> None:
    invalid = evaluate_finance_import_transition(
        {
            "batch_status": "dry_run",
            "classification_type": "pending",
            "reconciliation_status": "pending",
            "alert_status": "open",
        },
        "stage",
        "completed",
    )
    cross_axis = evaluate_finance_import_transition(
        _axes(), "classify", "skipped_existing"
    )

    assert not invalid.allowed
    assert invalid.refusal_reason == INVALID_AXES
    assert not cross_axis.allowed
    assert cross_axis.refusal_reason is not None
