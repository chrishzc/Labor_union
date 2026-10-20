"""Read-only security planning and explicit installation for one NAS database.

Business schema is owned by canonical migrations. This installer creates only
locked definers, runtime accounts, fixed procedures and object-scoped grants.
It never drops/rebuilds tables or changes business rows.
"""
from __future__ import annotations

import hashlib
import re

import pymysql

from infrastructure.mysql.nas_mutations import PROCEDURES, RELATIONS


PROFILES = ("management", "line", "maintenance", "access")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
DELETE_TABLES = frozenset({
    *RELATIONS, "holidays", "staff_matching_preference_values", "staff_bank_accounts",
    "client_legacy_virtual_accounts", "scheduling_effective_occupancy", "current_anomaly_issues",
    "admin_audit_logs", "knowledge_answer_requests", "knowledge_answer_receipts",
    "knowledge_answer_sources", "knowledge_jobs", "knowledge_indexes",
})
ACCESS_TABLES = frozenset({
    "admin_users", "admin_root_account", "admin_sessions", "admin_totp_factors",
    "admin_totp_recovery_codes", "admin_login_attempts", "admin_mfa_enrollment_challenges",
    "admin_password_login_challenges", "admin_security_alert_outbox",
})
LINE_SYSTEM_TABLES = frozenset({
    "line_alert_delivery_intents", "line_alert_notification_targets",
    "line_command_receipts", "line_configuration_current", "line_configuration_revisions", "line_confirmation_requests",
    "line_delivery_attempt_events", "line_delivery_tasks", "line_domain_audit_events", "line_domain_outbox",
    "line_friend_state_events", "line_identity_binding_failure_streaks", "line_identity_bindings", "line_identity_flows",
    "line_identity_revocation_requests", "line_identity_role_binding_events", "line_identity_role_bindings",
    "line_inbox_events", "line_media_records", "line_notification_decisions", "line_notification_intents",
    "line_notification_source_events", "line_order_group_binding_events", "line_order_group_bindings",
    "line_order_group_participants", "line_order_group_runtime_events", "line_platform_users",
    "line_review_decision_events", "line_review_requests", "line_rich_menu_publication_cleanup_anomalies",
    "line_rich_menu_publication_step_acknowledgements", "line_rich_menu_publication_step_attempt_events",
    "line_rich_menu_publication_step_receipts", "line_rich_menu_publication_tasks", "line_rich_menu_publications",
    "line_rich_menu_publish_previews", "line_safe_review_link_events", "line_safe_review_link_outbox",
    "line_safe_review_link_receipts", "line_safe_review_links", "line_task_attempts", "line_tasks", "line_users",
    "line_webhook_events", "line_webhook_security_receipts", "line_worker_heartbeats",
})
LINE_SERVICE_DAY_TABLES = frozenset({
    "scheduling_service_day_checkpoint_events", "scheduling_service_day_checkpoint_outbox", "scheduling_service_day_checkpoints",
    "scheduling_service_day_log_attachments", "scheduling_service_day_log_events", "scheduling_service_day_log_outbox",
    "scheduling_service_day_logs",
})
# Public photo/day-log mutations now run through the private owner API.
# Keep readback for existing LINE projections, without direct file-fact writes.
LINE_PRIVATE_PHOTO_TABLES = frozenset({
    "scheduling_service_day_logs", "scheduling_service_day_log_attachments", "scheduling_service_day_log_events",
    "controlled_file_staging_objects", "controlled_file_objects", "controlled_file_apply_receipts",
    "controlled_file_finalize_intents", "controlled_file_leases", "controlled_file_references",
    "controlled_file_cleanup_events", "controlled_file_reconciliation_events",
})
ACCESS_LINE_TABLES = frozenset({
    "line_identity_flows", "line_identity_role_bindings", "line_identity_role_binding_events",
    "line_identity_binding_failure_streaks", "line_platform_users", "line_domain_audit_events",
    "line_domain_outbox", "line_delivery_tasks", "line_review_requests", "line_review_decision_events",
})
TECHNICAL_MAINTENANCE_TABLES = frozenset({
    "runtime_health_events", "runtime_health_status", "runtime_service_heartbeats",
    "anomaly_consumer_checkpoints", "anomaly_current_alerts", "anomaly_workflow_events",
    "knowledge_answer_receipts", "knowledge_answer_requests", "knowledge_answer_sources", "knowledge_apply_receipts",
    "knowledge_indexes", "knowledge_item_events", "knowledge_item_versions", "knowledge_items", "knowledge_jobs",
})
LINE_READ_TABLES = frozenset({
    "clients", "orders", "staff", "staff_schedule", "case_staff_assignments",
    "client_payments", "client_payment_terms", "client_payment_transactions",
    "staff_obligations", "staff_payable_projections", "staff_payout_obligation_links", "staff_payout_events",
    "holidays", "knowledge_items", "knowledge_item_versions", "knowledge_indexes",
    "staff_certifications", "staff_transportation", *RELATIONS,
    "orders_domain_outbox", "matching_coordination_outbox", "caregiver_candidate_contact_pools",
    "caregiver_candidate_contact_entries", "matching_schedule_snapshots", "matching_schedule_recipient_snapshots",
    "caregiver_matching_plans", "caregiver_matching_plan_segments", "confirmed_service_date_versions",
    "confirmed_service_date_days", "staff_lifecycle_states",
    "client_obligations", "client_obligation_events",
})
LINE_WRITE_TABLES = frozenset({
    "application_command_claims",
    "provisional_client_registrations", "provisional_registration_conflicts",
    "customer_service_tickets", "customer_service_ticket_events", "customer_service_escalations",
    "controlled_file_staging_objects", "controlled_file_objects", "controlled_file_apply_receipts",
    "controlled_file_finalize_intents", "controlled_file_leases", "controlled_file_references",
    "controlled_file_cleanup_events", "controlled_file_reconciliation_events",
    "knowledge_answer_requests", "knowledge_answer_receipts", "knowledge_answer_sources", "knowledge_jobs",
    "client_profile_change_requests", "client_profile_change_apply_receipts",
    "caregiver_candidate_contact_events", "matching_schedule_confirmation_events", "matching_schedule_line_interactions",
    "runtime_service_heartbeats", "runtime_health_status", "runtime_health_events", "admin_audit_logs",
    "scheduling_rebuild_notification_outbox",
})
MAINTENANCE_WRITE_TABLES = frozenset({
    "background_jobs", "current_anomaly_issues", "admin_audit_logs", "admin_audit_log_archive",
    "system_alerts", "system_alert_delivery_outbox", "anomaly_outbox",
})
# Exact editable scalar columns. Identity/actor/version values remain server-owned.
UPDATE_COLUMNS = {
    "provisional_client_registrations": ("active_line_user_id", "status", "client_id", "beclass_record_id",
                                         "application_version", "approved_by_actor", "approved_at_utc", "updated_at"),
    "holidays": ("holiday_name", "is_double_pay_default"),
    "staff": ("registered_at", "ip_address", "name", "phone", "tel", "tel_ext", "email", "birthday",
              "city", "zip_code", "address", "education", "emergency_contact_name", "emergency_contact_phone",
              "admin_notes", "staff_profile_version", "has_massage_cert", "status", "line_user_id",
              "weekly_rest_days", "care_babies", "service_regions", "special_skills", "union_no", "updated_at"),
    "staff_bank_accounts": ("bank_code", "branch_code", "account_no", "is_primary", "is_active"),
    "staff_matching_preference_definitions": ("display_name", "is_filterable", "status", "version", "updated_by"),
    "staff_matching_preference_profiles": ("version", "updated_by"),
    "staff_matching_preference_values": ("value_json", "profile_version", "updated_by"),
    "admin_users": ("username", "password_hash", "display_name", "linked_line_user_id", "access_control_version",
                    "enabled", "authorization_version", "last_login_at", "updated_at"),
}
NO_DIRECT_UPDATE = frozenset({
    *RELATIONS, "client_legacy_virtual_accounts", "scheduling_effective_occupancy",
    "scheduling_service_day_logs", "scheduling_service_day_log_attachments",
    "controlled_file_objects", "admin_root_account",
})


def _identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("invalid NAS security identifier")
    return f"`{value}`"


def account_names(database: str) -> dict[str, str]:
    _identifier(database)
    suffix = hashlib.sha256(database.encode("ascii")).hexdigest()[:10]
    return {profile: f"lu_nas_{profile}_{suffix}" for profile in (*PROFILES, "definer")}


def _locking_scope(database: str, partial_revokes: bool) -> str:
    _identifier(database)
    # Database-level grants interpret '_' as a wildcard unless partial_revokes
    # is enabled. Object-level table grants do not have this wildcard meaning.
    name = database if partial_revokes else database.replace("_", "\\_")
    return f"`{name}`"


def _grant_targets_database(grant: str, database: str, locking_scope: str) -> bool:
    if grant.startswith("GRANT USAGE ON *.*"):
        return True
    normalized = grant.replace(" ON PROCEDURE ", " ON ")
    # Schema-level wildcards have different escaping from object-level names.
    # Accept only the exact schema scope; never mistake an unescaped '_' grant
    # spanning several schemas for an object grant on this database.
    return (f" ON {locking_scope}.* TO " in normalized
            or f" ON `{database}`.`" in normalized)


def procedure_sql(name: str, definer: str) -> str:
    parameters, body, _ = PROCEDURES[name]
    _identifier(definer)
    return (f"CREATE DEFINER='{definer}'@'%' PROCEDURE {_identifier(name)}({parameters})\n"
            f"SQL SECURITY DEFINER MODIFIES SQL DATA\nBEGIN\n{body.strip()}\nEND")


def permission_plan(connection, database: str) -> dict:
    """SELECT only. Refuse any pre-existing routine drift before making changes."""
    names = account_names(database)
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT DATABASE() AS selected_database")
        if (cursor.fetchone() or {}).get("selected_database") != database:
            raise ValueError("NAS security target mismatch")
        cursor.execute("SELECT @@GLOBAL.partial_revokes AS partial_revokes")
        locking_scope = _locking_scope(database, bool(cursor.fetchone()["partial_revokes"]))
        cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE'", (database,))
        tables = {row["name"] for row in cursor.fetchall()}
        cursor.execute("SELECT column_name AS name FROM information_schema.columns WHERE table_schema=%s AND table_name='provisional_client_registrations'", (database,))
        application_columns = {row["name"] for row in cursor.fetchall()}
        if not {"application_payload", "application_version", "approved_by_actor", "approved_at_utc"} <= application_columns:
            raise ValueError("NAS security requires the additive registration upgrade first")
        missing = (DELETE_TABLES | {"staff", "orders", "scheduling_generations", "staff_matching_preference_profiles",
                                  "staff_matching_preference_definitions", "admin_audit_log_archive"}) - tables
        if missing:
            raise ValueError("NAS security requires the current complete business schema")
        cursor.execute("SELECT routine_name AS name,routine_definition AS body,definer AS definer,security_type AS security_type,sql_data_access AS sql_data_access FROM information_schema.routines WHERE routine_schema=%s AND routine_type='PROCEDURE'", (database,))
        existing = {row["name"]: row for row in cursor.fetchall()}
        cursor.execute("SELECT TABLE_NAME AS name FROM information_schema.tables WHERE table_schema=%s AND table_type='VIEW'", (database,))
        views = [row["name"] for row in cursor.fetchall()]
        cursor.execute("SELECT specific_name AS name,ordinal_position AS position,parameter_mode AS mode,parameter_name AS parameter,dtd_identifier AS type FROM information_schema.parameters WHERE specific_schema=%s ORDER BY specific_name,ordinal_position", (database,))
        parameters = {}
        for row in cursor.fetchall():
            parameters.setdefault(row["name"], []).append(
                (row["mode"] + " " + row["parameter"] + " " + row["type"]).lower())
        cursor.execute("SELECT User AS name FROM mysql.user WHERE Host=%s AND User IN (" +
                       ",".join(["%s"] * len(names)) + ")", ("%", *names.values()))
        existing_accounts = {row["name"] for row in cursor.fetchall()}
        for account in sorted(existing_accounts):
            cursor.execute(f"SHOW GRANTS FOR '{account}'@'%'")
            for row in cursor.fetchall():
                grant = str(next(iter(row.values())))
                if not _grant_targets_database(grant, database, locking_scope):
                    raise ValueError("NAS identity has foreign grants or roles; no changes applied")
    states = {}
    for name, (signature, body, _) in PROCEDURES.items():
        current = existing.get(name)
        states[name] = "absent" if current is None else "exact"
        if current is not None and (
            current["body"] is None or current["body"].strip().replace("\r\n", "\n") != "BEGIN\n" + body.strip() + "\nEND"
            or current["definer"] != names["definer"] + "@%"
            or current["security_type"] != "DEFINER" or current["sql_data_access"] != "MODIFIES SQL DATA"
            or parameters.get(name) != [part.strip().lower() for part in signature.split(",")]
        ):
            raise ValueError("NAS security procedure drift; no changes applied")
    if len(set(states.values())) > 1:
        raise ValueError("partial NAS security installation; preserve state for explicit recovery")
    return {"database": database, "locking_scope": locking_scope, "accounts": names, "existing_accounts": sorted(existing_accounts),
            "tables": sorted(tables), "views": sorted(views), "procedures": states}


def _table_grants(profile: str, tables: list[str]):
    for table in tables:
        read = write = False
        if profile == "management":
            read = table not in ACCESS_TABLES
            write = read
        elif profile == "access":
            read = table in ACCESS_TABLES or table in ACCESS_LINE_TABLES or table in {"admin_audit_logs", "admin_command_receipts", "application_command_claims"}
            write = read
        elif profile == "line":
            write = table in LINE_WRITE_TABLES or table in LINE_SYSTEM_TABLES or table in LINE_SERVICE_DAY_TABLES
            read = write or table in LINE_READ_TABLES or table in LINE_PRIVATE_PHOTO_TABLES
            write = write and table not in LINE_PRIVATE_PHOTO_TABLES
        elif profile == "maintenance":
            read = table not in ACCESS_TABLES
            write = table in MAINTENANCE_WRITE_TABLES or table in LINE_SYSTEM_TABLES or table in TECHNICAL_MAINTENANCE_TABLES
        if not read and table == "admin_users" and profile in {"management", "maintenance", "line"}:
            privileges = ["SELECT (id,username,display_name,enabled,role,linked_line_user_id)"]
            if profile in {"management", "line"}:
                privileges.append("UPDATE (linked_line_user_id)")
            yield table, privileges
            continue
        if not read:
            continue
        privileges = ["SELECT"]
        if profile == "line" and table in {"clients", "staff"}:
            # Existing verified binding owns only this system projection, never profile/order/payment fields.
            privileges.append("UPDATE (line_user_id)")
        if table == "admin_audit_log_archive":
            yield table, privileges
            continue
        if write:
            privileges.append("INSERT")
            if table not in NO_DIRECT_UPDATE | {"admin_audit_logs", "admin_command_receipts", "staff_bank_account_events"} and not table.endswith("_events"):
                columns = UPDATE_COLUMNS.get(table)
                if profile == "line" and table in {"provisional_client_registrations", "provisional_registration_conflicts"}:
                    columns = ("active_line_user_id",) if table == "provisional_client_registrations" else ()
                if profile == "line" and table == "customer_service_tickets":
                    columns = ("status", "version", "resolved_at_utc", "active_marker")
                if profile == "line" and table in {"client_profile_change_requests", "client_profile_change_apply_receipts"}:
                    columns = ()  # Intake only; approval and core Client writes stay internal.
                if profile == "line" and table == "application_command_claims":
                    columns = ()  # Append-only idempotency claims for controlled media.
                if profile == "line" and table == "matching_schedule_line_interactions":
                    columns = ("interaction_status", "consumed_at_utc")
                if profile == "line" and table == "scheduling_rebuild_notification_outbox":
                    columns = ("delivery_status", "published_at_utc", "attempt_count", "last_error_code")
                if columns == ():
                    yield table, privileges
                    continue
                privileges.append("UPDATE" if columns is None else "UPDATE (" + ",".join(_identifier(column) for column in columns) + ")")
        yield table, privileges


def install_permissions(connection, database: str, passwords: dict[str, str]) -> dict:
    """Explicit operation; caller must stop writers and preserve its source first."""
    if set(passwords) != set(PROFILES) or any(len(value) < 32 for value in passwords.values()):
        raise ValueError("all runtime profiles require independent credentials")
    if len(set(passwords.values())) != len(PROFILES):
        raise ValueError("runtime profiles must not share a password")
    plan = permission_plan(connection, database)
    names = plan["accounts"]
    schema = _identifier(database)
    with connection.cursor() as cursor:
        # These accounts are database-specific. No root, host, or unrelated user is changed.
        cursor.execute(f"CREATE USER IF NOT EXISTS '{names['definer']}'@'%' ACCOUNT LOCK")
        cursor.execute(f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM '{names['definer']}'@'%'")
        cursor.execute(f"ALTER USER '{names['definer']}'@'%' ACCOUNT LOCK")
        # Required by MySQL SELECT ... FOR UPDATE even for read-only parent
        # facts. This grants locking, not UPDATE/DELETE on those parent tables.
        cursor.execute(f"GRANT LOCK TABLES ON {plan['locking_scope']}.* TO '{names['definer']}'@'%'")
        for table in sorted(DELETE_TABLES | {"staff", "orders", "scheduling_generations", "staff_matching_preference_profiles", "staff_matching_preference_definitions", "admin_audit_log_archive"}):
            privileges = ["SELECT"]
            if table in DELETE_TABLES:
                privileges.append("DELETE")
            if table in {"client_legacy_virtual_accounts", "admin_audit_log_archive"}:
                privileges.append("INSERT")
            cursor.execute(f"GRANT {','.join(privileges)} ON {schema}.{_identifier(table)} TO '{names['definer']}'@'%'")
        for name, state in plan["procedures"].items():
            if state == "absent":
                cursor.execute(procedure_sql(name, names["definer"]))
            cursor.execute(f"GRANT EXECUTE ON PROCEDURE {schema}.{_identifier(name)} TO '{names['definer']}'@'%'")
        for profile in PROFILES:
            account = names[profile]
            cursor.execute(f"CREATE USER IF NOT EXISTS '{account}'@%s IDENTIFIED BY %s", ("%", passwords[profile]))
            cursor.execute(f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM '{account}'@'%'")
            cursor.execute(f"ALTER USER '{account}'@'%' REQUIRE SSL")
            cursor.execute(f"GRANT LOCK TABLES ON {plan['locking_scope']}.* TO '{account}'@'%'")
            for table, privileges in _table_grants(profile, plan["tables"]):
                cursor.execute(f"GRANT {','.join(privileges)} ON {schema}.{_identifier(table)} TO '{account}'@'%'")
            for view in plan["views"]:
                if profile in {"management", "maintenance"} or profile == "line" and view == "v_order_details":
                    cursor.execute(f"GRANT SELECT, SHOW VIEW ON {schema}.{_identifier(view)} TO '{account}'@'%'")
            for name, (_, _, allowed) in PROCEDURES.items():
                if profile in allowed:
                    cursor.execute(f"GRANT EXECUTE ON PROCEDURE {schema}.{_identifier(name)} TO '{account}'@'%'")
    return permission_plan(connection, database)


def legacy_account_plan(connection, database: str) -> bool:
    """Retire only the known old NAS identity, never a shared/foreign DB account."""
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT User AS name FROM mysql.user WHERE User='nas_app' AND Host='%'")
        if cursor.fetchone() is None:
            return False
        cursor.execute("SELECT @@GLOBAL.partial_revokes AS partial_revokes")
        locking_scope = _locking_scope(database, bool(cursor.fetchone()["partial_revokes"]))
        cursor.execute("SHOW GRANTS FOR 'nas_app'@'%'")
        for row in cursor.fetchall():
            grant = str(next(iter(row.values())))
            if grant.startswith("GRANT USAGE ON *.*"):
                continue
            if not _grant_targets_database(grant, database, locking_scope):
                raise ValueError("old NAS account has out-of-scope grants; preserve for explicit review")
    return True


def retire_legacy_account(connection, database: str) -> None:
    if legacy_account_plan(connection, database):
        with connection.cursor() as cursor:
            cursor.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'nas_app'@'%'")
            cursor.execute("ALTER USER 'nas_app'@'%' ACCOUNT LOCK")


def verify_runtime_permissions(connection, profile: str, database: str, *, expected_tables, expected_views) -> None:
    """Check the actual account without asking a low-privilege API to see all schema metadata."""
    if profile not in PROFILES:
        raise ValueError("unknown NAS permission profile")
    expected_procedures = {name for name, (_, _, profiles) in PROCEDURES.items() if profile in profiles}
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT @@GLOBAL.partial_revokes AS partial_revokes")
        locking_scope = _locking_scope(database, bool(cursor.fetchone()["partial_revokes"]))
        cursor.execute("SELECT TABLE_NAME AS name,TABLE_TYPE AS kind FROM information_schema.tables WHERE table_schema=%s", (database,))
        objects = cursor.fetchall()
        visible_tables = {row["name"] for row in objects if row["kind"] == "BASE TABLE"}
        visible_views = {row["name"] for row in objects if row["kind"] == "VIEW"}
        cursor.execute("SHOW GRANTS FOR CURRENT_USER")
        grants = [str(next(iter(row.values()))) for row in cursor.fetchall()]
        actual = set()
        for grant in grants:
            if grant.startswith("GRANT USAGE ON *.*") and "WITH GRANT OPTION" not in grant:
                continue
            if grant.startswith(f"GRANT LOCK TABLES ON {locking_scope}.* TO ") and "WITH GRANT OPTION" not in grant:
                actual.add(("database", database, "LOCK TABLES", "*"))
                continue
            match = re.fullmatch(r"GRANT (.+) ON (PROCEDURE )?`([A-Za-z0-9_]+)`\.`([A-Za-z0-9_]+)` TO .+", grant)
            if match is None or match[3] != database or "WITH GRANT OPTION" in grant:
                raise ValueError("out-of-scope NAS runtime grant")
            for privilege in re.split(r",\s*(?![^()]*\))", match[1]):
                actual.update(_capabilities("procedure" if match[2] else "table", match[4], privilege))
        expected = {("database", database, "LOCK TABLES", "*")}
        for table, privileges in _table_grants(profile, sorted(expected_tables)):
            if table not in visible_tables:
                raise ValueError("NAS runtime required table is not accessible")
            for privilege in privileges:
                expected.update(_capabilities("table", table, privilege))
        for view in expected_views:
            if profile in {"management", "maintenance"} or profile == "line" and view == "v_order_details":
                if view not in visible_views:
                    raise ValueError("NAS runtime required view is not accessible")
                expected.update({("table", view, "SELECT", "*"), ("table", view, "SHOW VIEW", "*")})
        expected.update(("procedure", name, "EXECUTE", "*") for name in expected_procedures)
        if actual != expected:
            raise ValueError("NAS runtime grants differ from the approved profile")


def _capabilities(kind: str, name: str, privilege: str) -> set[tuple[str, str, str, str]]:
    match = re.fullmatch(r"([A-Z ]+?)(?:\s*\(([^)]+)\))?", privilege.strip())
    if match is None:
        raise ValueError("invalid NAS privilege syntax")
    columns = [column.strip().strip("`") for column in match[2].split(",")] if match[2] else ["*"]
    return {(kind, name, match[1].strip(), column) for column in columns}
