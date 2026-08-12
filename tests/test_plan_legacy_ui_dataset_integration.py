from scripts.plan_legacy_ui_dataset_integration import (
    classify_table,
    describe_columns,
    execution_blockers,
    require_target_database,
    source_column_actions,
)


def test_plan_classifies_only_known_derived_or_retired_legacy_tables():
    assert classify_table("anomaly_current_alerts") == "rebuild_projection"
    assert classify_table("staff_monthly_settlements") == "retire_after_evidence_audit"
    assert classify_table("orders") == "preserve_root"
    assert classify_table("system_alerts") == "rebuild_projection"
    assert classify_table("client_obligations") == "retire_no_copy"
    assert classify_table("future_unknown_table") == "legacy_unresolved"


def test_plan_exposes_column_delta_without_silently_dropping_columns():
    assert describe_columns(("case_no", "contract_id"), ("case_no", "contract_identity")) == {
        "source_only": ["contract_id"],
        "target_only": ["contract_identity"],
        "shared": ["case_no"],
    }


def test_plan_requires_a_rebuild_when_target_is_not_empty():
    assert execution_blockers(
        source_case_count=53,
        target_case_count=2,
        overlapping_cases=(),
    ) == ["target contains data and must be explicitly rebuilt"]


def test_plan_rejects_a_non_disposable_target_database():
    try:
        require_target_database("union_db_candidate_20260803_v5")
    except ValueError as error:
        assert str(error) == "target database must match lu_test_dataset_[a-z0-9_]+"
    else:
        raise AssertionError("non-disposable database must be rejected")


def test_system_alert_legacy_columns_have_a_lossless_mapping_contract():
    assert source_column_actions("system_alerts", ("description", "event_type")) == {
        "description": "merge_into_details._legacy.description",
        "event_type": "merge_into_details._legacy.event_type",
    }
    assert source_column_actions("orders", ("unknown_legacy_column",)) == {
        "unknown_legacy_column": "unmapped_blocker",
    }
