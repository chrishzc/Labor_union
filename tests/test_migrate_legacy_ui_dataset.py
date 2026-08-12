import pytest

from scripts.migrate_legacy_ui_dataset import (
    _blocked_preflight_report,
    _preflight_report,
    _preserved_root_tables,
    copy_statement,
)
from scripts.rebuild_legacy_ui_dataset_projections import PROJECTION_TABLES
from scripts.plan_legacy_ui_dataset_integration import classify_table


def test_preservation_copy_uses_only_explicitly_shared_columns():
    statement = copy_statement(
        "union_db_candidate_20260803_v5",
        "lu_test_dataset_contract_signing_v4",
        "orders",
        ("case_no", "contract_identity"),
    )

    assert statement == (
        "INSERT INTO `lu_test_dataset_contract_signing_v4`.`orders` "
        "(`case_no`,`contract_identity`) SELECT `case_no`,`contract_identity` "
        "FROM `union_db_candidate_20260803_v5`.`orders`"
    )


def test_system_alert_copy_preserves_retired_columns_inside_legacy_payload():
    statement = copy_statement(
        "union_db_candidate_20260803_v5",
        "lu_test_dataset_contract_signing_v4",
        "system_alerts",
        ("id", "details"),
    )

    assert "'_legacy'" in statement
    assert "`description`" in statement
    assert "`event_type`" in statement


def test_bootstrap_policy_rows_are_inserted_without_overwriting_the_current_baseline():
    statement = copy_statement(
        "union_db_candidate_20260803_v5",
        "lu_test_dataset_contract_signing_v4",
        "payroll_rate_policies",
        ("policy_version", "policy_kind"),
    )

    assert statement.startswith("INSERT IGNORE INTO")


def test_preservation_copy_rejects_untrusted_sql_identifiers():
    with pytest.raises(ValueError, match="invalid SQL identifier"):
        copy_statement("source;drop", "lu_test_dataset_contract_signing_v4", "orders", ("case_no",))


def test_preservation_migration_only_copies_explicit_root_tables():
    assert _preserved_root_tables(("orders", "system_alerts", "unknown_table")) == (
        "orders",
    )


def test_preservation_migration_never_copies_current_alert_projections():
    assert classify_table("system_alerts") == "rebuild_projection"
    assert "anomaly_current_alerts" in PROJECTION_TABLES


def test_preflight_refuses_to_describe_a_nonempty_target_as_migration_permitted():
    report = _preflight_report(
        "lu_test_dataset_contract_signing_v4",
        ("orders",),
        {"orders": ("case_no", "contract_identity")},
        "a" * 64,
        False,
    )

    assert report["dry_run"] is True
    assert report["migration_permitted"] is False
    assert report["target_is_empty"] is False


def test_blocked_preflight_exposes_unclassified_tables_without_permitting_copy():
    report = _blocked_preflight_report(
        _preflight_report(
            "lu_test_dataset_contract_signing_v4",
            ("orders",),
            {"orders": ("case_no",)},
            "b" * 64,
            True,
        ),
        ("application_command_claims",),
    )

    assert report["migration_permitted"] is False
    assert report["blocker_code"] == "unclassified_source_tables"
    assert report["unclassified_source_tables"] == ["application_command_claims"]
