"""Offline policy oracles; real MySQL grants/rollback require engine qualification."""
import re
import pytest

from infrastructure.mysql.nas_mutations import PROCEDURES, RELATIONS, call_mutation
from infrastructure.mysql.nas_permissions import _table_grants, account_names, procedure_sql


def test_line_has_no_delete_ddl_or_account_security_write_and_no_approval_write():
    grants = dict(_table_grants("line", ["clients", "orders", "staff", "admin_users", "admin_root_account",
        "provisional_client_registrations", "provisional_registration_conflicts", "scheduling_service_day_logs"]))
    assert "admin_root_account" not in grants
    assert not any("password_hash" in value or value == "INSERT" for value in grants["admin_users"])
    assert grants["admin_users"][-1] == "UPDATE (linked_line_user_id)"
    assert grants["orders"] == ["SELECT"]
    assert grants["clients"] == ["SELECT", "UPDATE (line_user_id)"]
    assert "INSERT" in grants["provisional_client_registrations"]
    assert not any("approved" in privilege or "application_version" in privilege
                   for privilege in grants["provisional_client_registrations"])
    assert grants["scheduling_service_day_logs"] == ["SELECT"]
    assert not any("line" in profiles for _, _, profiles in PROCEDURES.values())
    assert dict(_table_grants("line", ["application_command_claims"])) == {
        "application_command_claims": ["SELECT", "INSERT"]}


def test_line_cannot_bypass_private_photo_owner_with_direct_file_metadata_writes():
    from infrastructure.mysql.nas_permissions import LINE_PRIVATE_PHOTO_TABLES
    assert all(privileges == ["SELECT"] for _, privileges in
               _table_grants("line", sorted(LINE_PRIVATE_PHOTO_TABLES)))
    assert all("INSERT" in privileges for _, privileges in
               _table_grants("management", sorted(LINE_PRIVATE_PHOTO_TABLES)))


def test_management_retains_business_writes_but_not_direct_deletes_or_audit_edits():
    grants = dict(_table_grants("management", ["staff", "holidays", "admin_users", "admin_audit_logs",
                                               "admin_audit_log_archive", "staff_certifications"]))
    assert "INSERT" in grants["holidays"]
    assert any("UPDATE" in item for item in grants["staff"])
    assert grants["admin_audit_logs"] == ["SELECT", "INSERT"]
    assert grants["admin_audit_log_archive"] == ["SELECT"]
    assert grants["staff_certifications"] == ["SELECT", "INSERT"]
    assert not any("password_hash" in item for item in grants["admin_users"])
    assert not any("DELETE" in item for values in grants.values() for item in values)


def test_fixed_procedures_have_no_dynamic_sql_or_transaction_commit():
    for name, (_, body, _) in PROCEDURES.items():
        sql = procedure_sql(name, account_names("lu_test_nas_permissions")["definer"])
        assert "SQL SECURITY DEFINER" in sql
        assert not re.search(r"\b(?:COMMIT|ROLLBACK|PREPARE|EXECUTE|DROP|TRUNCATE)\b", body, re.I)
    assert set(RELATIONS) == {"staff_regions", "staff_time_slots", "staff_cooking_skills", "staff_holiday_availability",
                              "staff_weekly_rest", "staff_baby_types", "staff_certifications", "staff_transportation"}


def test_unknown_procedure_never_reaches_database():
    class NoSql:
        def execute(self, *args):
            pytest.fail("unapproved operation reached DB")
    with pytest.raises(ValueError, match="unknown NAS mutation"):
        call_mutation(NoSql(), "delete_arbitrary_table", "clients")


def test_registry_delete_procedures_do_not_grant_runtime_direct_root_delete():
    from infrastructure.mysql.nas_permissions import DELETE_TABLES
    assert {"orders", "clients"} <= DELETE_TABLES
    assert "staff" not in DELETE_TABLES
    assert "lu_nas_delete_unused_staff_v1" not in PROCEDURES
    assert "lu_nas_delete_unused_case_v1" not in PROCEDURES
    for profile in ("management", "line", "access", "maintenance"):
        assert all("DELETE" not in privilege for _, privileges in _table_grants(profile, ["staff", "orders", "clients"])
                   for privilege in privileges)
    _, body, profiles = PROCEDURES["lu_nas_delete_unsigned_case_v2"]
    assert profiles == ("management",)
    assert "registry_deletion_stale_version" in body
    assert "registry_deletion_signed" in body
    assert "signed_received" in body and "contract_completed" in body


def test_account_namespace_is_database_specific_and_identifiers_cannot_escape():
    assert set(account_names("lu_test_a").values()).isdisjoint(account_names("lu_test_b").values())
    assert len(set(account_names("lu_test_a").values())) == 5
    with pytest.raises(ValueError, match="invalid NAS security identifier"):
        account_names("union_db`; DROP TABLE clients;--")


def _grant_connection(grants, tables):
    from unittest.mock import MagicMock
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"partial_revokes": 0}
    cursor.fetchall.side_effect = [[{"name": table, "kind": "BASE TABLE"} for table in tables],
                                  [{"Grants": grant} for grant in grants]]
    return connection


def test_runtime_gate_checks_column_scope_not_just_no_delete():
    from infrastructure.mysql.nas_permissions import verify_runtime_permissions
    prefix = " ON `lu_test_nas`."
    grants = ["GRANT LOCK TABLES ON `lu\\_test\\_nas`.* TO 'runtime'@'%'",
              "GRANT SELECT, UPDATE (`line_user_id`)" + prefix + "`clients` TO 'runtime'@'%'",
              "GRANT SELECT, INSERT" + prefix + "`client_profile_change_requests` TO 'runtime'@'%'"]
    expected = {"expected_tables": ["clients", "client_profile_change_requests"], "expected_views": []}
    verify_runtime_permissions(_grant_connection(grants, expected["expected_tables"]), "line", "lu_test_nas", **expected)
    for extra in ("GRANT UPDATE" + prefix + "`clients` TO 'runtime'@'%'",
                  "GRANT DELETE" + prefix + "`clients` TO 'runtime'@'%'",
                  "GRANT EXECUTE ON PROCEDURE `lu_test_nas`.`lu_nas_delete_holiday_v1` TO 'runtime'@'%'",
                  "GRANT 'administrator'@'%' TO 'runtime'@'%'",
                  "GRANT USAGE ON *.* TO 'runtime'@'%' WITH GRANT OPTION"):
        with pytest.raises(ValueError):
            verify_runtime_permissions(_grant_connection([*grants, extra], expected["expected_tables"]), "line", "lu_test_nas", **expected)
    # A removed table grant also hides its information_schema row. The gate
    # must use the canonical inventory rather than treating hidden as optional.
    with pytest.raises(ValueError, match="required table"):
        verify_runtime_permissions(_grant_connection(grants[:2], ["clients"]), "line", "lu_test_nas", **expected)


def test_pending_profile_requests_are_append_only_for_external_line():
    line = dict(_table_grants("line", ["client_profile_change_requests", "client_profile_change_apply_receipts", "clients", "orders"]))
    assert line["client_profile_change_requests"] == ["SELECT", "INSERT"]
    assert line["client_profile_change_apply_receipts"] == ["SELECT", "INSERT"]
    assert line["orders"] == ["SELECT"]


def test_future_tables_are_not_automatically_added_to_line_or_access_write_scope():
    assert dict(_table_grants("line", ["line_future_unreviewed", "scheduling_service_day_future"])) == {}
    assert dict(_table_grants("access", ["line_future_unreviewed", "scheduling_service_day_logs"])) == {}


def test_permission_plan_is_read_only_and_refuses_foreign_existing_accounts():
    from unittest.mock import MagicMock
    from infrastructure.mysql.nas_permissions import DELETE_TABLES, permission_plan
    database = "lu_test_nas"
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [{"selected_database": database}, {"partial_revokes": 0}]
    tables = DELETE_TABLES | {"staff", "orders", "scheduling_generations", "staff_matching_preference_profiles",
        "staff_matching_preference_definitions", "admin_audit_log_archive"}
    results = [[{"name": table} for table in tables],
               [{"name": name} for name in ("application_payload", "application_version", "approved_by_actor", "approved_at_utc")],
               [], [], [], [{"name": account_names(database)["management"]}],
               [{"Grants": "GRANT SELECT ON `foreign_db`.* TO 'runtime'@'%'"}]]
    cursor.fetchall.side_effect = results
    with pytest.raises(ValueError, match="foreign grants or roles"):
        permission_plan(connection, database)
    assert all(call.args[0].startswith(("SELECT ", "SHOW ")) for call in cursor.execute.call_args_list)


def test_locking_grant_escapes_database_wildcards_without_widening_business_writes():
    from infrastructure.mysql.nas_permissions import _locking_scope, _grant_targets_database
    scope = _locking_scope("lu_test_a", False)
    assert scope == "`lu\\_test\\_a`"
    assert _locking_scope("lu_test_a", True) == "`lu_test_a`"
    assert _grant_targets_database(f"GRANT LOCK TABLES ON {scope}.* TO 'runtime'@'%'", "lu_test_a", scope)
    assert _grant_targets_database("GRANT EXECUTE ON PROCEDURE `lu_test_a`.`lu_nas_delete_holiday_v1` TO 'runtime'@'%'", "lu_test_a", scope)
    assert not _grant_targets_database("GRANT EXECUTE ON PROCEDURE `other`.`lu_nas_delete_holiday_v1` TO 'runtime'@'%'", "lu_test_a", scope)
    assert not _grant_targets_database("GRANT ALL PRIVILEGES ON `lu_test_a`.* TO 'nas_app'@'%'", "lu_test_a", scope)
    assert _grant_targets_database(f"GRANT ALL PRIVILEGES ON {scope}.* TO 'nas_app'@'%'", "lu_test_a", scope)


def test_read_only_configuration_plan_does_not_read_runtime_passwords(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock
    from scripts import configure_nas_permissions as cli, compact_fresh_schema, verify_validation_schema_manifest
    root_password = tmp_path / "synthetic-root-password"
    root_password.write_text("synthetic fixture only", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"format": "nas-db-security-settings/v1", "host": "db",
        "database": "lu_test_nas", "admin_user": "root", "admin_password_file": str(root_password),
        "ca_file": "synthetic-ca.pem", "password_files": {profile: str(tmp_path / f"missing-{profile}")
            for profile in ("management", "line", "maintenance", "access")}}), encoding="utf-8")
    monkeypatch.setattr(compact_fresh_schema, "load_compact_plan", lambda: {"expected": {}})
    monkeypatch.setattr(verify_validation_schema_manifest, "verify_database_objects", lambda *_: [])
    connection = MagicMock()
    monkeypatch.setattr(cli.pymysql, "connect", lambda **_: connection)
    monkeypatch.setattr(cli, "permission_plan", lambda *_: {"procedures": {}})
    monkeypatch.setattr(cli, "legacy_account_plan", lambda *_: False)
    monkeypatch.setattr(cli, "install_permissions", lambda *_: pytest.fail("plan must never install grants"))
    result = cli.configure(settings)
    assert result["status"] == "planned" and result["business_rows_changed"] is False
    connection.close.assert_called_once_with()


def test_ensure_nas_procedures_creates_missing_and_respects_existing():
    from unittest.mock import MagicMock
    from infrastructure.mysql.nas_mutations import ensure_nas_procedures, PROCEDURES

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    all_names = sorted(PROCEDURES.keys())
    missing_name = "lu_nas_replace_staff_banks_v1"
    existing_names = [n for n in all_names if n != missing_name]

    cursor.fetchall.return_value = [{"routine_name": n} for n in existing_names]
    created = ensure_nas_procedures(connection)

    assert created == [missing_name]
    assert cursor.execute.call_count == 2
    create_sql = cursor.execute.call_args_list[1][0][0]
    assert f"CREATE PROCEDURE `{missing_name}`" in create_sql
    assert "SQL SECURITY DEFINER" in create_sql
    assert "MODIFIES SQL DATA" in create_sql

    cursor.reset_mock()
    cursor.fetchall.return_value = [{"routine_name": n} for n in all_names]
    none_created = ensure_nas_procedures(connection)
    assert none_created == []
    assert cursor.execute.call_count == 1


def test_ensure_nas_procedures_cli_dry_run(capsys, monkeypatch):
    import json
    from unittest.mock import MagicMock
    from scripts import ensure_nas_procedures as cli

    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = {"db_name": "test_union_db"}
    cursor.fetchall.return_value = [{"routine_name": "lu_nas_archive_audits_v1"}]
    monkeypatch.setattr(cli, "get_connection", lambda: connection)

    exit_code = cli.main(["--dry-run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "planned"
    assert payload["database"] == "test_union_db"
    assert payload["missing_count"] == len(cli.PROCEDURES) - 1
    assert "lu_nas_replace_staff_banks_v1" in payload["missing_procedures"]
