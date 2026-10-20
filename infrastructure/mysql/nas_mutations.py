"""Fixed-purpose NAS delete procedures; caller retains the outer transaction."""
from __future__ import annotations

import json


# Identifiers are project-owned constants, never request parameters.
RELATIONS = {
    "staff_regions": ("region_name", "custom_region_detail"),
    "staff_time_slots": ("slot_name", "custom_slot_detail"),
    "staff_cooking_skills": ("skill_name", "custom_skill_detail"),
    "staff_holiday_availability": ("holiday_name", "custom_holiday_detail"),
    "staff_weekly_rest": ("rest_type", "custom_rest_detail"),
    "staff_baby_types": ("baby_type", "custom_baby_detail"),
    "staff_certifications": ("certification_type", None),
    "staff_transportation": ("vehicle_type", None),
}


def _staff_guard() -> str:
    return """IF p_staff IS NULL OR p_staff <= 0 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_staff';
    END IF;
    IF NOT EXISTS(SELECT id FROM staff WHERE id=p_staff FOR UPDATE) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_staff_not_found';
    END IF;"""


# name -> (SQL parameters, body, allowed execution profiles).
PROCEDURES = {
    "lu_nas_delete_holiday_v1": (
        "IN p_date DATE", """
        IF p_date IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_date'; END IF;
        DELETE FROM holidays WHERE holiday_date=p_date;
        """, ("management",)),
    "lu_nas_trim_preferences_v1": (
        "IN p_staff BIGINT, IN p_version BIGINT, IN p_kept JSON",
        _staff_guard() + """
        IF p_kept IS NULL OR JSON_TYPE(p_kept)<>'ARRAY' OR NOT EXISTS(
          SELECT staff_id FROM staff_matching_preference_profiles
          WHERE staff_id=p_staff AND version=p_version FOR UPDATE
        ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_preference_version_conflict'; END IF;
        IF EXISTS(SELECT 1 FROM JSON_TABLE(p_kept,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) k
          LEFT JOIN staff_matching_preference_definitions d ON d.id=k.id AND d.status='active'
          WHERE d.id IS NULL) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_preference';
        END IF;
        DELETE v FROM staff_matching_preference_values v WHERE v.staff_id=p_staff
          AND NOT EXISTS(SELECT 1 FROM JSON_TABLE(p_kept,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) k
                         WHERE k.id=v.definition_id);
        """, ("management",)),
    "lu_nas_replace_case_account_v1": (
        "IN p_case VARCHAR(191), IN p_expected JSON, IN p_account VARCHAR(50), IN p_digest CHAR(64), IN p_actor VARCHAR(100)",
        """
        IF p_case IS NULL OR p_case='' OR p_account IS NULL OR p_account='' OR
          p_expected IS NULL OR JSON_TYPE(p_expected)<>'ARRAY' THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_case_account';
        END IF;
        IF NOT EXISTS(SELECT case_no FROM orders WHERE case_no=p_case FOR UPDATE) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_case_not_found'; END IF;
        IF JSON_LENGTH(p_expected)<>(SELECT COUNT(*) FROM client_legacy_virtual_accounts WHERE case_no=p_case)
          OR EXISTS(SELECT 1 FROM client_legacy_virtual_accounts m WHERE m.case_no=p_case
            AND NOT EXISTS(SELECT 1 FROM JSON_TABLE(p_expected,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) e WHERE e.id=m.id))
          THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_case_account_stale'; END IF;
        IF EXISTS(SELECT id FROM client_legacy_virtual_accounts
          WHERE virtual_account=p_account AND case_no<>p_case FOR UPDATE) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_case_account_collision'; END IF;
        DELETE FROM client_legacy_virtual_accounts WHERE case_no=p_case;
        INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by)
          VALUES(p_case,p_account,p_digest,2,p_actor);
        """, ("management",)),
    "lu_nas_cancel_occupancy_v1": (
        "IN p_case VARCHAR(191), IN p_generation BIGINT", """
        IF NOT EXISTS(SELECT id FROM scheduling_generations WHERE id=p_generation
          AND case_no=p_case AND status='effective' AND effective_marker=1 FOR UPDATE) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_generation_conflict'; END IF;
        DELETE FROM scheduling_effective_occupancy WHERE generation_id=p_generation;
        """, ("management",)),
    "lu_nas_remove_current_issue_v1": (
        "IN p_key CHAR(67), IN p_domain VARCHAR(191), IN p_root VARCHAR(191), IN p_snapshot VARCHAR(191)", """
        IF p_key IS NULL OR p_key='' OR p_domain IS NULL OR p_root IS NULL OR p_snapshot IS NULL THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_issue'; END IF;
        DELETE FROM current_anomaly_issues WHERE issue_key=p_key AND owner_domain=p_domain
          AND owner_root_type=p_root AND owner_snapshot_token=p_snapshot;
        IF ROW_COUNT()<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_issue_stale'; END IF;
        """, ("management", "maintenance")),
    "lu_nas_archive_audits_v1": (
        "IN p_ids JSON", """
        IF p_ids IS NULL OR JSON_TYPE(p_ids)<>'ARRAY' THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_audit_batch'; END IF;
        IF EXISTS(SELECT a.id FROM admin_audit_logs a JOIN
          JSON_TABLE(p_ids,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) e ON e.id=a.id
          WHERE a.created_at>=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 YEAR)) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_audit_not_expired'; END IF;
        INSERT IGNORE INTO admin_audit_log_archive
          (source_audit_id,admin_user_id,action,resource_type,resource_id,request_path,http_method,result_status,ip_address,details_json,created_at)
          SELECT a.id,a.admin_user_id,a.action,a.resource_type,a.resource_id,a.request_path,a.http_method,a.result_status,a.ip_address,a.details_json,a.created_at
          FROM admin_audit_logs a JOIN JSON_TABLE(p_ids,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) e ON e.id=a.id
          WHERE a.created_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 YEAR);
        IF EXISTS(SELECT a.id FROM admin_audit_logs a JOIN
          JSON_TABLE(p_ids,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) e ON e.id=a.id
          LEFT JOIN admin_audit_log_archive b ON b.source_audit_id=a.id
          WHERE b.source_audit_id IS NULL OR NOT(a.admin_user_id<=>b.admin_user_id)
            OR NOT(a.action<=>b.action) OR NOT(a.resource_type<=>b.resource_type)
            OR NOT(a.resource_id<=>b.resource_id) OR NOT(a.request_path<=>b.request_path)
            OR NOT(a.http_method<=>b.http_method) OR NOT(a.result_status<=>b.result_status)
            OR NOT(a.ip_address<=>b.ip_address) OR NOT(a.details_json<=>b.details_json)
            OR NOT(a.created_at<=>b.created_at)) THEN
          SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_audit_archive_conflict'; END IF;
        DELETE a FROM admin_audit_logs a JOIN JSON_TABLE(p_ids,'$[*]' COLUMNS(id BIGINT PATH '$' ERROR ON ERROR)) e ON e.id=a.id
          JOIN admin_audit_log_archive b ON b.source_audit_id=a.id
          WHERE a.created_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 2 YEAR);
        """, ("maintenance",)),
    "lu_nas_purge_knowledge_request_v1": (
        "IN p_id BIGINT, IN p_state VARCHAR(50), IN p_occurred DATETIME(6), IN p_receipt BIGINT, IN p_source BIGINT, IN p_job BIGINT", """
        IF p_receipt IS NULL OR p_source IS NULL OR p_job IS NULL
          OR NOT EXISTS(SELECT id FROM knowledge_answer_requests WHERE id=p_id
          AND request_status=p_state AND request_status IN ('answered','unsupported','failed')
          AND COALESCE(completed_at_utc,created_at_utc)=p_occurred FOR UPDATE)
          OR p_receipt<>(SELECT COALESCE(MAX(id),0) FROM knowledge_answer_receipts WHERE answer_request_id=p_id)
          OR p_source<>(SELECT COALESCE(MAX(s.id),0) FROM knowledge_answer_sources s JOIN knowledge_answer_receipts r
                        ON r.id=s.answer_receipt_id WHERE r.answer_request_id=p_id)
          OR p_job<>(SELECT COALESCE(MAX(id),0) FROM knowledge_jobs WHERE answer_request_id=p_id)
          THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_knowledge_request_stale'; END IF;
        DELETE s FROM knowledge_answer_sources s JOIN knowledge_answer_receipts r ON r.id=s.answer_receipt_id WHERE r.answer_request_id=p_id;
        DELETE FROM knowledge_answer_receipts WHERE answer_request_id=p_id;
        DELETE FROM knowledge_jobs WHERE answer_request_id=p_id;
        DELETE FROM knowledge_answer_requests WHERE id=p_id;
        """, ("management", "maintenance")),
    "lu_nas_purge_knowledge_job_v1": (
        "IN p_id BIGINT, IN p_state VARCHAR(50), IN p_occurred DATETIME(6), IN p_attempt BIGINT", """
        DELETE FROM knowledge_jobs WHERE id=p_id AND answer_request_id IS NULL
          AND processing_status=p_state AND processing_status IN ('completed','failed')
          AND COALESCE(completed_at_utc,created_at_utc)=p_occurred AND attempt_count=p_attempt;
        IF ROW_COUNT()<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_knowledge_job_stale'; END IF;
        """, ("management", "maintenance")),
    "lu_nas_purge_knowledge_index_v1": (
        "IN p_version BIGINT, IN p_state VARCHAR(50), IN p_occurred DATETIME(6)", """
        IF NOT EXISTS(SELECT id FROM knowledge_indexes WHERE index_version=p_version AND index_status=p_state
          AND COALESCE(built_at_utc,created_at_utc)=p_occurred FOR UPDATE)
          OR (p_state NOT IN ('failed','stale') AND NOT(p_state='ready' AND p_version<(
            SELECT COALESCE(MAX(index_version),0) FROM knowledge_indexes WHERE index_status='ready')))
          THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_knowledge_index_stale'; END IF;
        DELETE FROM knowledge_indexes WHERE index_version=p_version;
        """, ("management", "maintenance")),
}

for _table, (_value, _detail) in RELATIONS.items():
    _detail_match = f" AND `{_detail}`<=>p_detail" if _detail else ""
    PROCEDURES[f"lu_nas_remove_{_table}_v1"] = (
        "IN p_staff BIGINT, IN p_value VARCHAR(191), IN p_detail VARCHAR(100)",
        _staff_guard() + f"""
        IF p_value IS NULL OR p_value='' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_invalid_relation'; END IF;
        DELETE FROM `{_table}` WHERE staff_id=p_staff AND `{_value}`=p_value{_detail_match};
        IF ROW_COUNT()<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_relation_stale'; END IF;
        """, ("management",))
    _columns = [_value] + ([_detail] if _detail else [])
    _entries = ",".join(f"`{col}` VARCHAR(191) PATH '$.{col}' NULL ON EMPTY" for col in _columns)
    _matches = " AND ".join(f"r.`{col}`<=>(e.`{col}` COLLATE utf8mb4_unicode_ci)" for col in _columns)
    PROCEDURES[f"lu_nas_replace_{_table}_v1"] = (
        "IN p_staff BIGINT, IN p_expected JSON",
        _staff_guard() + f"""
        IF p_expected IS NULL OR JSON_TYPE(p_expected)<>'ARRAY'
          OR JSON_LENGTH(p_expected)<>(SELECT COUNT(*) FROM `{_table}` WHERE staff_id=p_staff)
          OR EXISTS(SELECT 1 FROM `{_table}` r WHERE r.staff_id=p_staff AND NOT EXISTS(
            SELECT 1 FROM JSON_TABLE(p_expected,'$[*]' COLUMNS({_entries})) e WHERE {_matches}))
          THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_import_relation_stale'; END IF;
        DELETE FROM `{_table}` WHERE staff_id=p_staff;
        """, ("management",))

PROCEDURES["lu_nas_replace_staff_banks_v1"] = (
    "IN p_staff BIGINT, IN p_expected JSON", _staff_guard() + """
    IF p_expected IS NULL OR JSON_TYPE(p_expected)<>'ARRAY'
      OR JSON_LENGTH(p_expected)<>(SELECT COUNT(*) FROM staff_bank_accounts WHERE staff_id=p_staff)
      OR EXISTS(SELECT 1 FROM staff_bank_accounts r WHERE r.staff_id=p_staff AND NOT EXISTS(
        SELECT 1 FROM JSON_TABLE(p_expected,'$[*]' COLUMNS(
          bank_code VARCHAR(10) PATH '$.bank_code', branch_code VARCHAR(10) PATH '$.branch_code',
          account_no VARCHAR(50) PATH '$.account_no', is_primary INT PATH '$.is_primary')) e
        WHERE r.bank_code<=>(e.bank_code COLLATE utf8mb4_unicode_ci)
          AND r.branch_code<=>(e.branch_code COLLATE utf8mb4_unicode_ci)
          AND r.account_no<=>(e.account_no COLLATE utf8mb4_unicode_ci) AND r.is_primary<=>e.is_primary))
      THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='nas_import_bank_stale'; END IF;
    DELETE FROM staff_bank_accounts WHERE staff_id=p_staff;
    """, ("management",))


def call_mutation(cursor, name: str, *arguments) -> None:
    if name not in PROCEDURES:
        raise ValueError("unknown NAS mutation")
    placeholders = ",".join(["%s"] * len(arguments))
    cursor.execute(f"CALL `{name}`({placeholders})", arguments)
    # CALL adds an empty result set. Drain it before the next statement/commit.
    while cursor.nextset():
        pass


def relation_snapshot(values, columns) -> str:
    return json.dumps([dict(zip(columns, row)) for row in sorted(values, key=str)],
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
