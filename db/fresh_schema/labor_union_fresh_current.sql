-- Generated final fresh schema. Regenerate; do not edit by hand.

-- Existing databases are never modified by this asset.

SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `accounting_pricing_policies` (
  `id` bigint NOT NULL,
  `effective_on` date NOT NULL,
  `policy_json` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_accounting_pricing_effective` (`effective_on`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `accounting_pricing_receipts` (
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `command_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_json` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `accounting_pricing_state` (
  `singleton_id` tinyint NOT NULL,
  `revision` bigint NOT NULL DEFAULT '0',
  PRIMARY KEY (`singleton_id`),
  CONSTRAINT `chk_accounting_pricing_singleton` CHECK ((`singleton_id` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `actual_hours_adjustments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `previous_actual_hours` decimal(10,2) NOT NULL,
  `adjusted_actual_hours` decimal(10,2) NOT NULL,
  `adjustment_reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjusted_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjusted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_actual_hours_adjustment_assignment` (`assignment_id`,`adjusted_at`),
  CONSTRAINT `fk_actual_hours_adjustment_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_actual_hours_adjustment_adjusted_nonnegative` CHECK ((`adjusted_actual_hours` >= 0)),
  CONSTRAINT `chk_actual_hours_adjustment_previous_nonnegative` CHECK ((`previous_actual_hours` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_audit_log_archive` (
  `source_audit_id` bigint NOT NULL,
  `admin_user_id` bigint DEFAULT NULL,
  `action` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resource_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resource_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `http_method` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_status` int DEFAULT NULL,
  `ip_address` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `archived_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`source_audit_id`),
  KEY `idx_admin_audit_archive_created_at` (`created_at`),
  KEY `idx_admin_audit_archive_actor_time` (`admin_user_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_user_id` bigint DEFAULT NULL,
  `action` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resource_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resource_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_path` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `http_method` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_status` int DEFAULT NULL,
  `ip_address` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_actor_time` (`admin_user_id`,`created_at`),
  KEY `idx_admin_audit_resource` (`resource_type`,`resource_id`,`created_at`),
  CONSTRAINT `fk_admin_audit_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_command_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `command_family` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_admin_command_receipt` (`command_family`,`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_login_attempts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outcome` enum('failed','succeeded','rate_limited','mfa_replay') COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_admin_login_attempt_subject` (`username_hash`,`source_hash`,`occurred_at`),
  KEY `idx_admin_login_attempt_time` (`occurred_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_mfa_enrollment_challenges` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `admin_user_id` bigint NOT NULL,
  `challenge_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_mfa_challenge_hash` (`challenge_hash`),
  KEY `idx_admin_mfa_challenge_user_expiry` (`admin_user_id`,`expires_at`,`consumed_at`),
  CONSTRAINT `fk_admin_mfa_challenge_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_password_login_challenges` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `admin_user_id` bigint NOT NULL,
  `credential_version` bigint unsigned NOT NULL,
  `factor_id` bigint unsigned NOT NULL,
  `challenge_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_password_login_challenge_hash` (`challenge_hash`),
  KEY `idx_admin_password_login_challenge_expiry` (`admin_user_id`,`expires_at`,`consumed_at`),
  KEY `fk_admin_password_login_challenge_factor` (`factor_id`),
  CONSTRAINT `fk_admin_password_login_challenge_factor` FOREIGN KEY (`factor_id`) REFERENCES `admin_totp_factors` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_admin_password_login_challenge_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_root_account` (
  `singleton_key` tinyint NOT NULL DEFAULT '1',
  `admin_user_id` bigint NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`singleton_key`),
  UNIQUE KEY `uk_admin_root_account_user` (`admin_user_id`),
  CONSTRAINT `fk_admin_root_account_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_admin_root_account_singleton` CHECK ((`singleton_key` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_security_alert_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `source_audit_id` bigint NOT NULL,
  `alert_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_identity` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `processing_status` enum('pending','processing','completed','dead') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '5',
  `next_attempt_at` datetime(6) DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_security_alert_outbox_audit` (`source_audit_id`),
  KEY `idx_admin_security_alert_outbox_due` (`processing_status`,`next_attempt_at`,`lease_expires_at`,`id`),
  CONSTRAINT `fk_admin_security_alert_outbox_audit` FOREIGN KEY (`source_audit_id`) REFERENCES `admin_audit_logs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_admin_security_alert_outbox_attempts` CHECK (((`max_attempts` > 0) and (`attempt_count` <= `max_attempts`))),
  CONSTRAINT `chk_admin_security_alert_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_user_id` bigint NOT NULL,
  `session_token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SHA-256；原始 Session Token 只回傳一次',
  `expires_at` datetime NOT NULL,
  `absolute_expires_at` datetime DEFAULT NULL COMMENT 'hard re-authentication deadline',
  `last_seen_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_session_token_hash` (`session_token_hash`),
  KEY `idx_admin_session_active` (`admin_user_id`,`revoked_at`,`expires_at`),
  CONSTRAINT `fk_admin_session_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_totp_factors` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `admin_user_id` bigint NOT NULL,
  `factor_state` enum('enrollment_pending','active','revoked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `seed_ciphertext` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `encryption_key_version` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enrollment_challenge_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enrollment_expires_at` datetime(6) NOT NULL,
  `last_successful_step` bigint DEFAULT NULL,
  `activated_at` datetime(6) DEFAULT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_totp_factor_user` (`admin_user_id`),
  KEY `idx_admin_totp_factor_enrollment` (`factor_state`,`enrollment_expires_at`),
  CONSTRAINT `fk_admin_totp_factor_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_admin_totp_factor_activation` CHECK ((((`factor_state` = _utf8mb4'active') and (`activated_at` is not null) and (`revoked_at` is null)) or ((`factor_state` = _utf8mb4'enrollment_pending') and (`activated_at` is null) and (`revoked_at` is null)) or ((`factor_state` = _utf8mb4'revoked') and (`revoked_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_totp_recovery_codes` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `factor_id` bigint unsigned NOT NULL,
  `code_hash` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `consumed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_totp_recovery_code_hash` (`code_hash`),
  KEY `idx_admin_totp_recovery_factor` (`factor_id`,`consumed_at`),
  CONSTRAINT `fk_admin_totp_recovery_factor` FOREIGN KEY (`factor_id`) REFERENCES `admin_totp_factors` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `admin_users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'scrypt 雜湊；不得保存明碼密碼',
  `display_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `linked_line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '選填：對應 line_users.line_user_id',
  `role` enum('line_viewer','line_agent','line_manager','system_admin') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'line_viewer',
  `access_control_version` bigint unsigned NOT NULL DEFAULT '1' COMMENT '帳號中心 optimistic-lock version',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `authorization_version` bigint unsigned NOT NULL DEFAULT '0' COMMENT 'effective capability grant revision',
  `last_login_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_username` (`username`),
  UNIQUE KEY `uk_admin_linked_line_user` (`linked_line_user_id`),
  CONSTRAINT `fk_admin_linked_line_user` FOREIGN KEY (`linked_line_user_id`) REFERENCES `line_users` (`line_user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `anomaly_consumer_checkpoints` (
  `consumer_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `partition_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `processed_at` datetime NOT NULL,
  PRIMARY KEY (`consumer_identity`,`partition_identity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `anomaly_current_alerts` (
  `fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_code` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_version` int unsigned NOT NULL,
  `source_domain` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `predicate_active` tinyint(1) NOT NULL,
  `workflow_status` enum('open','claimed','resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `workflow_version` bigint unsigned NOT NULL,
  `projection_version` bigint unsigned NOT NULL,
  `claimed_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claimed_at` datetime DEFAULT NULL,
  `resolved_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `display_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`fingerprint`),
  UNIQUE KEY `uq_anomaly_current_source` (`definition_code`,`source_identity`),
  KEY `idx_anomaly_current_workflow` (`predicate_active`,`workflow_status`,`definition_code`),
  CONSTRAINT `chk_anomaly_current_display` CHECK ((json_type(`display_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_anomaly_current_fingerprint` CHECK (regexp_like(`fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_anomaly_current_workflow` CHECK ((((`workflow_status` = _utf8mb4'open') and (`claimed_by` is null) and (`claimed_at` is null) and (`resolved_by` is null) and (`resolved_at` is null)) or ((`workflow_status` = _utf8mb4'claimed') and (char_length(trim(`claimed_by`)) > 0) and (`claimed_at` is not null) and (`resolved_by` is null) and (`resolved_at` is null)) or ((`workflow_status` = _utf8mb4'resolved') and (char_length(trim(`resolved_by`)) > 0) and (`resolved_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `anomaly_workflow_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('claim','resolve','reopen','auto_resolve') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_workflow_version` bigint unsigned NOT NULL,
  `resulting_workflow_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(320) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_anomaly_workflow_event_idempotency` (`idempotency_key`),
  KEY `idx_anomaly_workflow_event_alert` (`alert_fingerprint`,`resulting_workflow_version`),
  CONSTRAINT `fk_anomaly_workflow_event_alert` FOREIGN KEY (`alert_fingerprint`) REFERENCES `anomaly_current_alerts` (`fingerprint`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_anomaly_workflow_event_version` CHECK ((`resulting_workflow_version` = (`expected_workflow_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `application_command_claims` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`),
  CONSTRAINT `chk_application_command_claim_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_application_command_claim_text` CHECK (((char_length(trim(`command_family`)) > 0) and (char_length(trim(`aggregate_identity`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `assignment_payroll_rate_snapshots` (
  `assignment_id` bigint NOT NULL,
  `policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen','twins') COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`assignment_id`),
  KEY `fk_assignment_payroll_rate_policy` (`policy_version`,`policy_kind`),
  CONSTRAINT `fk_assignment_payroll_rate_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_payroll_rate_policy` FOREIGN KEY (`policy_version`, `policy_kind`) REFERENCES `payroll_rate_policies` (`policy_version`, `policy_kind`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_assignment_payroll_rate_amount` CHECK ((`hourly_rate_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `assignment_plan_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `resulting_generation_number` int unsigned NOT NULL,
  `expected_client_finance_version` bigint unsigned NOT NULL,
  `resulting_client_finance_version` bigint unsigned NOT NULL,
  `expected_payroll_version` bigint unsigned NOT NULL,
  `resulting_payroll_version` bigint unsigned NOT NULL,
  `scheduling_receipt_id` bigint NOT NULL,
  `cancelled_assignment_ids` json NOT NULL,
  `created_assignment_keys` json NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_assignment_plan_receipt_key` (`idempotency_key`),
  KEY `fk_assignment_plan_receipt_order` (`case_no`),
  KEY `fk_assignment_plan_scheduling_receipt` (`scheduling_receipt_id`),
  CONSTRAINT `fk_assignment_plan_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_plan_scheduling_receipt` FOREIGN KEY (`scheduling_receipt_id`) REFERENCES `scheduling_command_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_assignment_plan_receipt_arrays` CHECK (((json_type(`cancelled_assignment_ids`) = _utf8mb4'ARRAY') and (json_type(`created_assignment_keys`) = _utf8mb4'ARRAY'))),
  CONSTRAINT `chk_assignment_plan_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_assignment_plan_receipt_versions` CHECK (((`resulting_order_version` = (`expected_order_version` + 1)) and (`resulting_scheduling_version` = (`expected_scheduling_version` + 1)) and (`resulting_client_finance_version` = (`expected_client_finance_version` + 1)) and (`resulting_payroll_version` = (`expected_payroll_version` + 1))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `assignment_schedule_leave_substitution_batches` (
  `batch_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '整批冪等鍵',
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'canonical preview sha256 lowercase hex',
  `item_count` int unsigned NOT NULL COMMENT 'canonical items 數量',
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '執行者管理員識別',
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '統一 non-empty 原因',
  `request_snapshot` json NOT NULL COMMENT 'canonical request snapshot',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '批次建立時間',
  PRIMARY KEY (`batch_key`),
  KEY `idx_assignment_schedule_leave_substitution_batches_case_time` (`case_no`,`occurred_at`),
  CONSTRAINT `fk_assignment_schedule_leave_substitution_batches_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_assignment_schedule_leave_substitution_batches_identity` CHECK (((char_length(trim(`batch_key`)) > 0) and (char_length(trim(`case_no`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0))),
  CONSTRAINT `chk_assignment_schedule_leave_substitution_batches_item_count` CHECK ((`item_count` >= 1)),
  CONSTRAINT `chk_leave_batch_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_leave_batch_request_snapshot` CHECK ((json_type(`request_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `assignment_schedule_leave_substitution_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
  `original_assignment_id` bigint NOT NULL COMMENT '請假日原始正式服務指派 id',
  `original_schedule_id` int NOT NULL COMMENT '被處置之日排班 id',
  `work_date` date NOT NULL COMMENT '被處置之休假日期',
  `resolution_type` enum('leave_only','defer_following_assignments','substitute') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '處置類型',
  `substitute_assignment_id` bigint DEFAULT NULL COMMENT '只在 substitute 時為非空',
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全域唯一冪等鍵',
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '執行者管理員識別',
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '非空原因',
  `schedule_snapshot` json NOT NULL COMMENT '原排班/順延/代班日套用前後快照',
  `payroll_snapshot` json NOT NULL COMMENT '原 assignment 與代班 assignment 的核對快照',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
  `batch_key` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `batch_item_index` int unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_assignment_schedule_leave_substitution_event_key` (`event_key`),
  UNIQUE KEY `uq_assignment_schedule_leave_substitution_events_batch_linkage` (`batch_key`,`batch_item_index`),
  KEY `idx_assignment_schedule_leave_substitution_event_case_time` (`case_no`,`occurred_at`),
  KEY `idx_assignment_schedule_leave_substitution_event_assignments` (`original_assignment_id`,`substitute_assignment_id`,`work_date`),
  KEY `fk_assignment_schedule_leave_substitution_substitute_assignment` (`substitute_assignment_id`),
  KEY `fk_assignment_schedule_leave_substitution_original_schedule` (`original_schedule_id`),
  KEY `idx_assignment_schedule_leave_substitution_events_batch_key` (`batch_key`,`work_date`),
  CONSTRAINT `fk_assignment_schedule_leave_substitution_event_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_schedule_leave_substitution_events_batch` FOREIGN KEY (`batch_key`) REFERENCES `assignment_schedule_leave_substitution_batches` (`batch_key`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_schedule_leave_substitution_original_assignment` FOREIGN KEY (`original_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_schedule_leave_substitution_original_schedule` FOREIGN KEY (`original_schedule_id`) REFERENCES `staff_schedule` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_schedule_leave_substitution_substitute_assignment` FOREIGN KEY (`substitute_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_assignment_schedule_leave_substitution_events_batch_linkage` CHECK ((((`batch_key` is null) and (`batch_item_index` is null)) or ((`batch_key` is not null) and (`batch_item_index` is not null) and (`batch_item_index` >= 0)))),
  CONSTRAINT `chk_assignment_schedule_leave_substitution_resolution` CHECK ((((`resolution_type` = _utf8mb4'substitute') and (`substitute_assignment_id` is not null) and (`substitute_assignment_id` <> `original_assignment_id`)) or ((`resolution_type` in (_utf8mb4'leave_only',_utf8mb4'defer_following_assignments')) and (`substitute_assignment_id` is null)))),
  CONSTRAINT `chk_leave_sub_actor_reason_key` CHECK (((char_length(trim(`event_key`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0))),
  CONSTRAINT `chk_leave_sub_payroll_snapshot` CHECK ((json_type(`payroll_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_leave_sub_schedule_snapshot` CHECK ((json_type(`schedule_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `background_jobs` (
  `job_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_type` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `command_version` smallint unsigned DEFAULT NULL,
  `command_payload` json DEFAULT NULL,
  `submitted_by` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('queued','running','succeeded','failed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'queued',
  `receipt_payload` json DEFAULT NULL,
  `error_payload` json DEFAULT NULL,
  `available_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `attempt_count` smallint unsigned NOT NULL DEFAULT '0',
  `max_attempts` smallint unsigned NOT NULL DEFAULT '3',
  `lease_token` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `result_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`job_id`),
  UNIQUE KEY `uk_command_identity` (`command_identity`),
  KEY `idx_status` (`status`),
  KEY `idx_background_jobs_queue` (`status`,`available_at`,`created_at`),
  KEY `idx_background_jobs_lease` (`status`,`lease_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_import_review_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_row_id` bigint NOT NULL,
  `event_type` enum('resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `candidate_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owning_record_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `corrected_payload` json NOT NULL,
  `resolved_issue_codes` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_review_event_version` (`review_row_id`,`resulting_version`),
  UNIQUE KEY `uq_beclass_review_event_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_beclass_review_event_row` FOREIGN KEY (`review_row_id`) REFERENCES `beclass_import_review_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_beclass_review_event_fingerprint` CHECK (regexp_like(`candidate_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_beclass_review_event_issues` CHECK ((json_type(`resolved_issue_codes`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_beclass_review_event_payload` CHECK ((json_type(`corrected_payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_beclass_review_event_text` CHECK (((char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (char_length(trim(`idempotency_key`)) > 0))),
  CONSTRAINT `chk_beclass_review_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_import_review_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_row_id` bigint NOT NULL,
  `review_event_id` bigint DEFAULT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('review_opened','review_resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` datetime DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_review_outbox_intent` (`intent_key`),
  KEY `idx_beclass_review_outbox_pending` (`published_at`,`id`),
  KEY `fk_beclass_review_outbox_row` (`review_row_id`),
  KEY `fk_beclass_review_outbox_event` (`review_event_id`),
  CONSTRAINT `fk_beclass_review_outbox_event` FOREIGN KEY (`review_event_id`) REFERENCES `beclass_import_review_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_beclass_review_outbox_row` FOREIGN KEY (`review_row_id`) REFERENCES `beclass_import_review_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_beclass_review_outbox_event_shape` CHECK ((((`intent_type` = _utf8mb4'review_opened') and (`review_event_id` is null)) or ((`intent_type` = _utf8mb4'review_resolved') and (`review_event_id` is not null)))),
  CONSTRAINT `chk_beclass_review_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_import_review_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_row_id` bigint NOT NULL,
  `owning_record_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_event_id` bigint NOT NULL,
  `outbox_id` bigint NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_review_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_beclass_review_receipt_event` (`review_event_id`),
  KEY `fk_beclass_review_receipt_row` (`review_row_id`),
  KEY `fk_beclass_review_receipt_outbox` (`outbox_id`),
  CONSTRAINT `fk_beclass_review_receipt_event` FOREIGN KEY (`review_event_id`) REFERENCES `beclass_import_review_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_beclass_review_receipt_outbox` FOREIGN KEY (`outbox_id`) REFERENCES `beclass_import_review_outbox` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_beclass_review_receipt_row` FOREIGN KEY (`review_row_id`) REFERENCES `beclass_import_review_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_beclass_review_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_beclass_review_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_import_review_rows` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` enum('client','staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_sheet` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_row` int unsigned NOT NULL,
  `identifier` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_payload` json NOT NULL,
  `issue_codes` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_review_identity` (`review_identity`),
  UNIQUE KEY `uq_beclass_review_source_event` (`source_kind`,`source_event_identity`),
  CONSTRAINT `chk_beclass_review_fingerprint` CHECK (regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_beclass_review_issues` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_length(`issue_codes`) > 0))),
  CONSTRAINT `chk_beclass_review_payload` CHECK ((json_type(`source_payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_beclass_review_source_location` CHECK (((char_length(trim(`source_sheet`)) > 0) and (`source_row` > 0) and (char_length(trim(`identifier`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_record_correction_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `beclass_record_id` int NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_values_json` json NOT NULL,
  `after_values_json` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_correction_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_beclass_correction_event_version` (`beclass_record_id`,`resulting_version`),
  CONSTRAINT `fk_beclass_correction_event_record` FOREIGN KEY (`beclass_record_id`) REFERENCES `beclass_records` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_beclass_correction_event_payload` CHECK (((json_type(`before_values_json`) = _utf8mb4'OBJECT') and (json_type(`after_values_json`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_beclass_correction_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_record_correction_states` (
  `beclass_record_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `effective_values_json` json NOT NULL,
  `updated_by` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`beclass_record_id`),
  CONSTRAINT `fk_beclass_correction_state_record` FOREIGN KEY (`beclass_record_id`) REFERENCES `beclass_records` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_beclass_correction_state_payload` CHECK ((json_type(`effective_values_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `beclass_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `seq_num` int DEFAULT NULL COMMENT '項次',
  `query_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '查詢序號 - 與 clients.case_no 進行主關聯',
  `client_id` int DEFAULT NULL COMMENT '過渡期唯一比對後的 Client 綁定',
  `bound_case_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '過渡期唯一比對後的案件編號',
  `record_origin` enum('imported','admin_manual') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'imported',
  `created_at` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '報名時間',
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '姓名',
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Email',
  `birth_date` date DEFAULT NULL COMMENT '生日',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `tel` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '市話',
  `ext` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分機',
  `city` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '縣市',
  `zip_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '郵遞區號',
  `address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '地址',
  `refund_bank_code` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助款退款:銀行代號+分行代號',
  `refund_account_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助款退款:銀行帳號',
  `survey_details` json DEFAULT NULL COMMENT 'BeClass 問卷詳細內容 (包含餐點、用油、烹煮工具、特殊計費等 JSON)',
  `admin_notes` text COLLATE utf8mb4_unicode_ci COMMENT '管理者註記事項',
  `db_created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `db_updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `query_no` (`query_no`),
  KEY `idx_query_no` (`query_no`),
  KEY `idx_phone` (`phone`),
  KEY `idx_name` (`name`),
  KEY `idx_beclass_client_case` (`client_id`,`bound_case_no`),
  CONSTRAINT `fk_beclass_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_availability_lock_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `lock_id` bigint NOT NULL COMMENT '對應 caregiver_availability_locks.id',
  `segment_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plan_segments.id',
  `staff_id` int NOT NULL COMMENT '月嫂識別；對應 staff.id',
  `lock_date` date NOT NULL COMMENT '等待訂金占用日期',
  `active_marker` tinyint(1) DEFAULT NULL COMMENT '1表示該月嫂該日有效等待訂金鎖；已解除為 NULL 以支援 UNIQUE(staff_id, lock_date, active_marker)',
  `released_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '解除鎖定的管理員識別',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
  `released_at` timestamp NULL DEFAULT NULL COMMENT '解除時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_availability_lock_segment_date` (`lock_id`,`segment_id`,`lock_date`),
  UNIQUE KEY `uq_availability_lock_staff_date_active` (`staff_id`,`lock_date`,`active_marker`),
  KEY `idx_availability_lock_days_segment` (`segment_id`,`lock_date`),
  CONSTRAINT `fk_availability_lock_days_lock` FOREIGN KEY (`lock_id`) REFERENCES `caregiver_availability_locks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_availability_lock_days_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_availability_lock_days_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_availability_lock_days_active_state` CHECK ((((`active_marker` = 1) and (`released_by` is null) and (`released_at` is null)) or ((`active_marker` is null) and (char_length(trim(`released_by`)) > 0) and (`released_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_availability_lock_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `lock_id` bigint NOT NULL COMMENT '對應 caregiver_availability_locks.id',
  `event_type` enum('lock_acquired','lock_released','lock_converted','lock_cancelled') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件類型',
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全域唯一非空冪等鍵',
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '記錄事件的非空管理員識別',
  `reason` text COLLATE utf8mb4_unicode_ci COMMENT 'release/convert/cancel 的非空原因；acquired 為 NULL',
  `payload` json NOT NULL COMMENT '不可變 JSON Object 事件內容',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_availability_lock_event_key` (`event_key`),
  KEY `idx_availability_lock_events_lock` (`lock_id`,`occurred_at`),
  KEY `idx_availability_lock_events_type` (`event_type`,`occurred_at`),
  CONSTRAINT `fk_availability_lock_events_lock` FOREIGN KEY (`lock_id`) REFERENCES `caregiver_availability_locks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_availability_lock_events_nonempty` CHECK (((char_length(trim(`event_key`)) > 0) and (char_length(trim(`actor`)) > 0))),
  CONSTRAINT `chk_availability_lock_events_payload_object` CHECK ((json_type(`payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_availability_lock_events_reason` CHECK ((((`event_type` = _utf8mb4'lock_acquired') and (`reason` is null)) or ((`event_type` in (_utf8mb4'lock_released',_utf8mb4'lock_converted',_utf8mb4'lock_cancelled')) and (char_length(trim(`reason`)) > 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_availability_locks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plans.id',
  `status` enum('active','released','converted','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '鎖定批次狀態',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '1表示該方案目前有效鎖定批次；歷史/無效為 NULL 以支援 UNIQUE(plan_id, is_active)',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '建立鎖定批次的非空管理員識別',
  `released_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '解除/轉換/取消鎖定批次的管理員識別',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
  `released_at` timestamp NULL DEFAULT NULL COMMENT '解除/轉換/取消時間',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_availability_lock_plan_active` (`plan_id`,`is_active`),
  KEY `idx_availability_locks_status` (`status`,`created_at`),
  CONSTRAINT `fk_availability_locks_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_availability_locks_created_by` CHECK ((char_length(trim(`created_by`)) > 0)),
  CONSTRAINT `chk_availability_locks_status_state` CHECK ((((`status` = _utf8mb4'active') and (`is_active` = 1) and (`released_by` is null) and (`released_at` is null)) or ((`status` in (_utf8mb4'released',_utf8mb4'converted',_utf8mb4'cancelled')) and (`is_active` is null) and (char_length(trim(`released_by`)) > 0) and (`released_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_candidate_contact_entries` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `pool_id` bigint unsigned NOT NULL,
  `staff_id` int NOT NULL,
  `service_start_date` date NOT NULL,
  `service_end_date` date NOT NULL,
  `coverage_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('active','selected','withdrawn') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `active_marker` tinyint DEFAULT '1',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_candidate_contact_active_staff` (`pool_id`,`staff_id`,`active_marker`),
  KEY `fk_candidate_contact_entry_staff` (`staff_id`),
  CONSTRAINT `fk_candidate_contact_entry_pool` FOREIGN KEY (`pool_id`) REFERENCES `caregiver_candidate_contact_pools` (`id`),
  CONSTRAINT `fk_candidate_contact_entry_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`),
  CONSTRAINT `chk_candidate_contact_active` CHECK (((`active_marker` is null) or (`active_marker` = 1))),
  CONSTRAINT `chk_candidate_contact_dates` CHECK ((`service_start_date` <= `service_end_date`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_candidate_contact_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `pool_id` bigint unsigned NOT NULL,
  `candidate_id` bigint unsigned DEFAULT NULL,
  `event_type` enum('candidates_added','info_1_sent','info_2_sent','willingness_changed','candidate_selected','candidate_withdrawn','info_3_sent') COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `occurred_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_candidate_contact_event_key` (`event_key`),
  KEY `idx_candidate_contact_event_candidate` (`candidate_id`,`occurred_at`),
  KEY `fk_candidate_contact_event_pool` (`pool_id`),
  CONSTRAINT `fk_candidate_contact_event_candidate` FOREIGN KEY (`candidate_id`) REFERENCES `caregiver_candidate_contact_entries` (`id`),
  CONSTRAINT `fk_candidate_contact_event_pool` FOREIGN KEY (`pool_id`) REFERENCES `caregiver_candidate_contact_pools` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_candidate_contact_pools` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_candidate_contact_pool_case` (`case_no`),
  CONSTRAINT `fk_candidate_contact_pool_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_matching_plan_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plans.id',
  `segment_id` bigint DEFAULT NULL COMMENT '對應 caregiver_matching_plan_segments.id；方案層級事件為 NULL',
  `event_type` enum('info_1_sent','info_2_sent','willingness_changed','resume_sent','plan_cancelled') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件類型',
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全表唯一非空冪等鍵',
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '記錄事件的非空管理員識別',
  `payload` json NOT NULL COMMENT '事件型別限定的不可變 JSON 內容',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_caregiver_matching_plan_event_key` (`event_key`),
  KEY `idx_caregiver_matching_plan_events_plan` (`plan_id`,`occurred_at`),
  KEY `idx_caregiver_matching_plan_events_segment` (`segment_id`,`occurred_at`),
  KEY `idx_caregiver_matching_plan_events_type` (`event_type`,`occurred_at`),
  CONSTRAINT `fk_caregiver_matching_plan_events_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_caregiver_matching_plan_events_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_caregiver_matching_plan_events_nonempty` CHECK (((char_length(trim(`event_key`)) > 0) and (char_length(trim(`actor`)) > 0))),
  CONSTRAINT `chk_caregiver_matching_plan_events_payload_object` CHECK ((json_type(`payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_caregiver_matching_plan_events_target` CHECK ((((`event_type` in (_utf8mb4'info_1_sent',_utf8mb4'info_2_sent',_utf8mb4'willingness_changed',_utf8mb4'resume_sent')) and (`segment_id` is not null)) or ((`event_type` = _utf8mb4'plan_cancelled') and (`segment_id` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_matching_plan_segments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plans.id',
  `segment_order` tinyint NOT NULL COMMENT '服務區段順序 (1 至 4)',
  `staff_id` int NOT NULL COMMENT '月嫂識別；對應 staff.id',
  `assigned_start_date` date NOT NULL COMMENT '該區段預計服務開始日',
  `assigned_end_date` date NOT NULL COMMENT '該區段預計服務結束日',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_plan_segment_order` (`plan_id`,`segment_order`),
  UNIQUE KEY `uq_matching_plan_staff` (`plan_id`,`staff_id`),
  KEY `idx_matching_plan_segment_staff` (`staff_id`,`assigned_start_date`,`assigned_end_date`),
  CONSTRAINT `fk_matching_plan_segments_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_plan_segments_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_plan_segments_dates` CHECK ((`assigned_start_date` <= `assigned_end_date`)),
  CONSTRAINT `chk_matching_plan_segments_order` CHECK ((`segment_order` between 1 and 4))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `caregiver_matching_plans` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '洽談中訂單案件編號；對應 orders.case_no',
  `version` int NOT NULL DEFAULT '1' COMMENT '配對方案版本號 (1, 2, ...)',
  `communication_version` int unsigned NOT NULL DEFAULT '0' COMMENT '配對通知與回覆的 optimistic version',
  `status` enum('draft','proposed','accepted','rejected','superseded','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft' COMMENT '配對方案狀態',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '1表示該案件目前有效版本；歷史版本或無效版本為 NULL 以支援 UNIQUE(case_no, is_active)',
  `start_date` date NOT NULL COMMENT '本方案完整服務開始日',
  `end_date` date NOT NULL COMMENT '本方案完整服務結束日',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '建立方案版本的非空管理員識別',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_caregiver_matching_plan_case_version` (`case_no`,`version`),
  UNIQUE KEY `uq_caregiver_matching_plan_active` (`case_no`,`is_active`),
  KEY `idx_caregiver_matching_plan_status` (`status`,`created_at`),
  CONSTRAINT `fk_caregiver_matching_plans_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_caregiver_matching_plans_created_by` CHECK (((`created_by` is not null) and (char_length(trim(`created_by`)) > 0))),
  CONSTRAINT `chk_caregiver_matching_plans_dates` CHECK ((`start_date` <= `end_date`)),
  CONSTRAINT `chk_caregiver_matching_plans_is_active` CHECK (((`is_active` is null) or (`is_active` = 1))),
  CONSTRAINT `chk_caregiver_matching_plans_version` CHECK ((`version` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_architecture_bootstrap_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `client_payment_terms_event_id` bigint NOT NULL,
  `client_policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_hourly_rate_ntd` bigint NOT NULL,
  `payroll_policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payroll_policy_kind` enum('citizen','subsidized_citizen','non_citizen','twins') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payroll_hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_architecture_bootstrap_case` (`case_no`),
  UNIQUE KEY `uq_case_architecture_bootstrap_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_case_architecture_bootstrap_terms_event` (`client_payment_terms_event_id`),
  KEY `fk_case_architecture_bootstrap_payroll_policy` (`payroll_policy_version`,`payroll_policy_kind`),
  CONSTRAINT `fk_case_architecture_bootstrap_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_architecture_bootstrap_payroll_policy` FOREIGN KEY (`payroll_policy_version`, `payroll_policy_kind`) REFERENCES `payroll_rate_policies` (`policy_version`, `policy_kind`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_architecture_bootstrap_terms_event` FOREIGN KEY (`client_payment_terms_event_id`) REFERENCES `client_payment_terms_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_architecture_bootstrap_amounts` CHECK (((`client_hourly_rate_ntd` > 0) and (`payroll_hourly_rate_ntd` > 0))),
  CONSTRAINT `chk_case_architecture_bootstrap_fingerprint` CHECK (regexp_like(`candidate_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_case_architecture_bootstrap_text` CHECK (((char_length(trim(`source_identity_status`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_architecture_bootstrap_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bootstrap_event_id` bigint NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `bootstrap_created` tinyint(1) NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_architecture_bootstrap_receipt_key` (`idempotency_key`),
  KEY `fk_case_architecture_bootstrap_receipt_order` (`case_no`),
  KEY `fk_case_architecture_bootstrap_receipt_event` (`bootstrap_event_id`),
  CONSTRAINT `fk_case_architecture_bootstrap_receipt_event` FOREIGN KEY (`bootstrap_event_id`) REFERENCES `case_architecture_bootstrap_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_architecture_bootstrap_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_architecture_receipt_bootstrap_versions` CHECK (((`client_finance_version` = 0) and (`payroll_version` = 0))),
  CONSTRAINT `chk_case_architecture_receipt_created` CHECK ((`bootstrap_created` in (0,1))),
  CONSTRAINT `chk_case_architecture_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_architecture_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `bootstrap_event_id` bigint DEFAULT NULL,
  `source_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_snapshot` json NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_import_case` (`case_no`),
  UNIQUE KEY `uq_case_import_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_case_import_source` (`source_fingerprint`),
  KEY `fk_case_import_client` (`client_id`),
  KEY `fk_case_import_bootstrap` (`bootstrap_event_id`),
  CONSTRAINT `fk_case_import_bootstrap` FOREIGN KEY (`bootstrap_event_id`) REFERENCES `case_architecture_bootstrap_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_import_fingerprints` CHECK ((regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`candidate_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_import_snapshot` CHECK ((json_type(`source_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_case_import_text` CHECK (((char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_correction_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `review_binding_id` bigint NOT NULL,
  `prior_occurrence_id` bigint DEFAULT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `candidate_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `adopted_field_paths` json NOT NULL,
  `root_before_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `root_after_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `canonical_review_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Immutable Case Import HCM review identity; NULL only for historical events',
  `expected_review_version` bigint unsigned DEFAULT NULL,
  `resulting_review_version` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hcm_correction_event_identity` (`event_identity`),
  UNIQUE KEY `uq_hcm_correction_event_prior_source` (`prior_occurrence_id`,`source_event_identity`),
  UNIQUE KEY `uq_hcm_correction_event_review_version` (`canonical_review_identity`,`resulting_review_version`),
  KEY `idx_hcm_correction_event_case` (`case_no`,`id`),
  KEY `idx_hcm_correction_event_prior` (`prior_occurrence_id`,`id`),
  KEY `fk_hcm_correction_event_client` (`client_id`),
  KEY `fk_hcm_correction_event_binding` (`review_binding_id`),
  KEY `idx_hcm_correction_event_canonical_review` (`canonical_review_identity`,`id`),
  CONSTRAINT `fk_hcm_correction_event_binding` FOREIGN KEY (`review_binding_id`) REFERENCES `case_import_hcm_review_case_bindings` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_correction_event_canonical_review` FOREIGN KEY (`canonical_review_identity`) REFERENCES `case_import_hcm_review_rows` (`review_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_correction_event_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_correction_event_occurrence` FOREIGN KEY (`prior_occurrence_id`) REFERENCES `import_warning_occurrences` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_correction_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_hcm_correction_event_fields` CHECK (((json_type(`adopted_field_paths`) = _utf8mb4'ARRAY') and (json_length(`adopted_field_paths`) > 0))),
  CONSTRAINT `chk_hcm_correction_event_fingerprints` CHECK ((regexp_like(`source_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`candidate_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`root_before_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`root_after_fingerprint`,_ascii'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_hcm_correction_event_review_version` CHECK ((((`canonical_review_identity` is null) and (`expected_review_version` is null) and (`resulting_review_version` is null)) or ((`canonical_review_identity` is not null) and (char_length(trim(`canonical_review_identity`)) > 0) and (`expected_review_version` is not null) and (`resulting_review_version` = (`expected_review_version` + 1))))),
  CONSTRAINT `chk_hcm_correction_event_text` CHECK (((char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_correction_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `correction_event_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hcm_correction_outbox_event` (`correction_event_id`),
  UNIQUE KEY `uq_hcm_correction_outbox_intent` (`intent_key`),
  KEY `idx_hcm_correction_outbox_pending` (`published_at`,`attempts`,`id`),
  CONSTRAINT `fk_hcm_correction_outbox_event` FOREIGN KEY (`correction_event_id`) REFERENCES `case_import_hcm_correction_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_hcm_correction_outbox_attempts` CHECK ((`attempts` >= 0)),
  CONSTRAINT `chk_hcm_correction_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_correction_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `correction_event_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hcm_correction_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_hcm_correction_receipt_event` (`correction_event_id`),
  CONSTRAINT `fk_hcm_correction_receipt_event` FOREIGN KEY (`correction_event_id`) REFERENCES `case_import_hcm_correction_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_hcm_correction_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_hcm_correction_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_review_case_bindings` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `binding_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_row_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `root_import_event_id` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_hcm_review_case_binding_identity` (`binding_identity`),
  UNIQUE KEY `uq_hcm_review_case_binding_review` (`review_row_id`),
  KEY `idx_hcm_review_case_binding_case` (`case_no`,`id`),
  KEY `fk_hcm_review_case_binding_import_event` (`root_import_event_id`),
  CONSTRAINT `fk_hcm_review_case_binding_import_event` FOREIGN KEY (`root_import_event_id`) REFERENCES `case_import_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_review_case_binding_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_hcm_review_case_binding_review` FOREIGN KEY (`review_row_id`) REFERENCES `case_import_hcm_review_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_review_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_row_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp NULL DEFAULT NULL,
  `attempts` int NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_import_hcm_review_outbox_intent` (`intent_key`),
  KEY `idx_case_import_hcm_review_outbox_pending` (`published_at`,`attempts`,`id`),
  KEY `fk_case_import_hcm_review_outbox_row` (`review_row_id`),
  CONSTRAINT `fk_case_import_hcm_review_outbox_row` FOREIGN KEY (`review_row_id`) REFERENCES `case_import_hcm_review_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_import_hcm_review_outbox_attempts` CHECK ((`attempts` >= 0)),
  CONSTRAINT `chk_case_import_hcm_review_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_hcm_review_rows` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_sheet_identity` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_row` int NOT NULL,
  `case_identity` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `issue_codes` json NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_import_hcm_review_identity` (`review_identity`),
  UNIQUE KEY `uq_case_import_hcm_review_source` (`source_event_identity`),
  CONSTRAINT `chk_case_import_hcm_review_digests` CHECK ((regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_sheet_identity`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_import_hcm_review_payloads` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_type(`evidence_snapshot`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_case_import_hcm_review_source_row` CHECK ((`source_row` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_import_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `import_event_id` bigint NOT NULL,
  `bootstrap_event_id` bigint DEFAULT NULL,
  `order_version` bigint unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `provisional_registration_id` bigint DEFAULT NULL,
  `provisional_case_issue_event_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_import_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_case_import_receipt_event` (`import_event_id`),
  KEY `fk_case_import_receipt_order` (`case_no`),
  KEY `fk_case_import_receipt_client` (`client_id`),
  KEY `fk_case_import_receipt_bootstrap_event` (`bootstrap_event_id`),
  KEY `fk_case_import_receipt_provisional_registration` (`provisional_registration_id`),
  KEY `fk_case_import_receipt_provisional_issue_event` (`provisional_case_issue_event_id`),
  CONSTRAINT `fk_case_import_receipt_bootstrap_event` FOREIGN KEY (`bootstrap_event_id`) REFERENCES `case_architecture_bootstrap_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_import_event` FOREIGN KEY (`import_event_id`) REFERENCES `case_import_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_provisional_issue_event` FOREIGN KEY (`provisional_case_issue_event_id`) REFERENCES `provisional_registration_case_issue_events` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_provisional_registration` FOREIGN KEY (`provisional_registration_id`) REFERENCES `provisional_client_registrations` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_case_import_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_import_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_case_import_receipt_versions` CHECK (((`order_version` = 0) and (`client_finance_version` = 0) and (`payroll_version` = 0) and (`scheduling_version` = 0) and (`scheduling_generation` = 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_payroll_rate_policy_snapshots` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen','twins') COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_id` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  UNIQUE KEY `uq_case_payroll_policy_source_event` (`source_event_id`),
  KEY `fk_case_payroll_policy_definition` (`policy_version`,`policy_kind`),
  CONSTRAINT `fk_case_payroll_policy_definition` FOREIGN KEY (`policy_version`, `policy_kind`) REFERENCES `payroll_rate_policies` (`policy_version`, `policy_kind`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_payroll_policy_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_payroll_policy_source_event` FOREIGN KEY (`source_event_id`) REFERENCES `case_architecture_bootstrap_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_payroll_policy_amount` CHECK ((`hourly_rate_ntd` > 0)),
  CONSTRAINT `chk_case_payroll_policy_identity` CHECK ((char_length(trim(`source_identity_status`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_pricing_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_revision` bigint NOT NULL,
  `pricing_json` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_pricing_revision` (`case_no`,`resulting_revision`),
  CONSTRAINT `fk_case_pricing_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `case_staff_assignments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generation_id` bigint DEFAULT NULL,
  `candidate_key` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `staff_id` int NOT NULL,
  `assignment_sequence` int NOT NULL COMMENT '同案服務區段順序，從 1 起',
  `assigned_start_date` date DEFAULT NULL,
  `assigned_end_date` date DEFAULT NULL,
  `original_assigned_start_date` date DEFAULT NULL,
  `original_assigned_end_date` date DEFAULT NULL,
  `planned_hours` decimal(10,2) DEFAULT NULL,
  `actual_hours` decimal(10,2) DEFAULT NULL,
  `hourly_rate` decimal(10,2) DEFAULT NULL,
  `floor_fee_allocated` decimal(12,2) NOT NULL DEFAULT '0.00',
  `status` enum('planned','active','completed','replaced','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'planned',
  `replacement_reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `replaced_assignment_id` bigint DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_assignment_case_staff` (`id`,`case_no`,`staff_id`),
  UNIQUE KEY `uq_case_assignment_candidate` (`candidate_key`),
  UNIQUE KEY `uq_case_assignment_generation_sequence` (`generation_id`,`assignment_sequence`),
  UNIQUE KEY `uq_case_assignment_generation` (`id`,`generation_id`),
  UNIQUE KEY `uq_case_assignment_generation_staff` (`id`,`generation_id`,`staff_id`),
  KEY `idx_assignment_staff_status` (`staff_id`,`status`),
  KEY `fk_assignment_replaced` (`replaced_assignment_id`),
  KEY `idx_case_assignment_case_no` (`case_no`),
  CONSTRAINT `fk_assignment_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_assignment_replaced` FOREIGN KEY (`replaced_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_assignment_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_case_assignment_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_deposit_reversal_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_account_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_deposit_reversal_receipt_key` (`idempotency_key`),
  KEY `fk_client_deposit_reversal_receipt_order` (`case_no`),
  CONSTRAINT `fk_client_deposit_reversal_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_deposit_reversal_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_deposit_reversal_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_deposit_settlement_projection` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `deposit_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `settlement_state` enum('unsettled','settled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `contracted_amount_ntd` bigint unsigned NOT NULL,
  `allocated_net_amount_ntd` bigint NOT NULL,
  `settlement_identity` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `projection_version` bigint unsigned NOT NULL,
  `latest_ledger_entry_id` bigint DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  UNIQUE KEY `uq_client_deposit_projection_obligation` (`deposit_obligation_identity`,`case_no`),
  KEY `idx_client_deposit_projection_state` (`settlement_state`,`case_no`),
  KEY `fk_client_deposit_projection_latest_ledger` (`latest_ledger_entry_id`),
  CONSTRAINT `fk_client_deposit_projection_account` FOREIGN KEY (`case_no`) REFERENCES `client_finance_accounts` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_deposit_projection_latest_ledger` FOREIGN KEY (`latest_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_deposit_projection_obligation` FOREIGN KEY (`deposit_obligation_identity`, `case_no`) REFERENCES `client_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_deposit_projection_amount` CHECK ((`contracted_amount_ntd` > 0)),
  CONSTRAINT `chk_client_deposit_projection_fingerprints` CHECK ((regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and ((`settlement_identity` is null) or regexp_like(`settlement_identity`,_utf8mb4'^[0-9a-f]{64}$')))),
  CONSTRAINT `chk_client_deposit_projection_state` CHECK ((((`settlement_state` = _utf8mb4'settled') and (`allocated_net_amount_ntd` = `contracted_amount_ntd`) and (`settlement_identity` is not null) and (`latest_ledger_entry_id` is not null)) or ((`settlement_state` = _utf8mb4'unsettled') and (`allocated_net_amount_ntd` <> `contracted_amount_ntd`) and (`settlement_identity` is null)))),
  CONSTRAINT `chk_client_deposit_projection_version` CHECK ((`projection_version` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_finance_accounts` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  CONSTRAINT `fk_client_finance_account_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_finance_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_account_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_finance_receipt_key` (`idempotency_key`),
  KEY `fk_client_finance_receipt_order` (`case_no`),
  CONSTRAINT `fk_client_finance_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_finance_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_finance_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_finance_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('orders_deposit_reconciled','orders_deposit_reversed','anomaly_review_required','projection_refresh','client_over_refund_recovery_matched','client_over_refund_recovery_collected','client_refund_underpayment_required') COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_finance_outbox_intent` (`intent_key`),
  KEY `idx_client_finance_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_client_finance_outbox_order` (`case_no`),
  CONSTRAINT `fk_client_finance_outbox_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_finance_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_ledger_entries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `entry_type` enum('receipt','refund','subsidy_return','subsidy_advance','adjustment','reversal','refund_reversal','subsidy_return_reversal','subsidy_advance_reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `occurred_on` date NOT NULL,
  `reconciliation_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_entry_id` bigint DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_ledger_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_client_ledger_import_row` (`finance_import_row_id`),
  KEY `idx_client_ledger_case_date` (`case_no`,`occurred_on`,`id`),
  KEY `fk_client_ledger_reversal` (`reversal_of_entry_id`),
  CONSTRAINT `fk_client_ledger_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_ledger_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_ledger_reversal` FOREIGN KEY (`reversal_of_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_ledger_amount` CHECK ((`amount_ntd` > 0)),
  CONSTRAINT `chk_client_ledger_reversal_shape` CHECK ((((`entry_type` in (_utf8mb4'reversal',_utf8mb4'refund_reversal',_utf8mb4'subsidy_return_reversal',_utf8mb4'subsidy_advance_reversal')) and (`reversal_of_entry_id` is not null)) or ((`entry_type` not in (_utf8mb4'reversal',_utf8mb4'refund_reversal',_utf8mb4'subsidy_return_reversal',_utf8mb4'subsidy_advance_reversal')) and (`reversal_of_entry_id` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_ledger_obligation_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ledger_entry_id` bigint NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `allocation_ordinal` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_ledger_obligation_allocation` (`ledger_entry_id`,`obligation_identity`),
  UNIQUE KEY `uq_client_ledger_allocation_ordinal` (`ledger_entry_id`,`allocation_ordinal`),
  KEY `idx_client_allocation_obligation` (`obligation_identity`,`ledger_entry_id`),
  CONSTRAINT `fk_client_allocation_ledger` FOREIGN KEY (`ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_allocation_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_allocation_amount` CHECK ((`amount_ntd` > 0)),
  CONSTRAINT `chk_client_allocation_ordinal` CHECK ((`allocation_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_legacy_virtual_accounts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `virtual_account` varchar(14) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_row` int unsigned NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_legacy_virtual_account_pair` (`case_no`,`virtual_account`),
  KEY `idx_client_legacy_virtual_account_lookup` (`virtual_account`,`case_no`),
  CONSTRAINT `fk_client_legacy_virtual_account_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_legacy_virtual_account_format` CHECK (regexp_like(`virtual_account`,_utf8mb4'^99781699[0-9]{6}$')),
  CONSTRAINT `chk_client_legacy_virtual_account_source` CHECK ((regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$') and (`source_row` >= 2) and (char_length(trim(`created_by`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_obligation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_type` enum('deposit','first','second','refund','subsidy_return','adjustment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('receivable_from_client','payable_to_client') COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('established','recalculated','adjusted','reversed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_amount_ntd` bigint NOT NULL,
  `after_amount_ntd` bigint NOT NULL,
  `before_due_date` date DEFAULT NULL,
  `after_due_date` date DEFAULT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_account_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_obligation_event_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_client_obligation_source_event` (`obligation_identity`,`source_event_identity`),
  KEY `idx_client_obligation_event_case_type` (`case_no`,`obligation_type`,`created_at`),
  KEY `fk_client_obligation_event_source` (`source_obligation_identity`,`case_no`),
  CONSTRAINT `fk_client_obligation_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_obligation_event_source` FOREIGN KEY (`source_obligation_identity`, `case_no`) REFERENCES `client_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_obligation_event_amount` CHECK (((`before_amount_ntd` >= 0) and (`after_amount_ntd` >= 0) and ((`before_amount_ntd` <> `after_amount_ntd`) or (not((`before_due_date` <=> `after_due_date`))) or ((`event_type` = _utf8mb4'established') and (`before_amount_ntd` = 0) and (`after_amount_ntd` = 0) and (`before_due_date` is null) and (`after_due_date` is null)))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_obligations` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_type` enum('deposit','first','second','refund','subsidy_return','adjustment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('receivable_from_client','payable_to_client') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount_due_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `status` enum('open','settled','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint NOT NULL,
  `projection_version` bigint unsigned NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`obligation_identity`),
  UNIQUE KEY `uq_client_obligation_case_identity` (`obligation_identity`,`case_no`),
  KEY `idx_client_obligation_case_status` (`case_no`,`status`,`obligation_type`),
  KEY `fk_client_obligation_current_event` (`current_event_id`),
  KEY `fk_client_obligation_source` (`source_obligation_identity`,`case_no`),
  CONSTRAINT `fk_client_obligation_current_event` FOREIGN KEY (`current_event_id`) REFERENCES `client_obligation_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_obligation_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_obligation_source` FOREIGN KEY (`source_obligation_identity`, `case_no`) REFERENCES `client_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_obligation_amount` CHECK ((`amount_due_ntd` >= 0)),
  CONSTRAINT `chk_client_obligation_state` CHECK ((((`status` = _utf8mb4'open') and (`amount_due_ntd` > 0)) or ((`status` in (_utf8mb4'settled',_utf8mb4'cancelled')) and (`amount_due_ntd` = 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recoveries` (
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `refund_ledger_entry_id` bigint NOT NULL,
  `refund_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_due_ntd` bigint NOT NULL,
  `status` enum('open','partially_recovered','recovered','adjusted','settled','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `projection_version` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`recovery_identity`),
  UNIQUE KEY `uq_client_over_refund_bank_row` (`finance_import_row_id`),
  UNIQUE KEY `uq_client_over_refund_ledger` (`refund_ledger_entry_id`),
  UNIQUE KEY `uq_client_over_refund_idempotency` (`idempotency_key`),
  KEY `idx_client_over_refund_case_status` (`case_no`,`status`),
  KEY `fk_client_over_refund_refund_obligation` (`refund_obligation_identity`),
  CONSTRAINT `fk_client_over_refund_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_ledger` FOREIGN KEY (`refund_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_refund_obligation` FOREIGN KEY (`refund_obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_over_refund_amount` CHECK (((`amount_due_ntd` >= 0) and (((`amount_due_ntd` > 0) and (`status` in (_utf8mb4'open',_utf8mb4'partially_recovered'))) or ((`amount_due_ntd` = 0) and (`status` in (_utf8mb4'recovered',_utf8mb4'adjusted'))))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recovery_adjustment_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `remaining_after_ntd` bigint NOT NULL,
  `resulting_status` enum('open','adjusted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_over_refund_adjustment_receipt_key` (`idempotency_key`),
  KEY `fk_client_over_refund_adjustment_receipt_recovery` (`recovery_identity`),
  CONSTRAINT `fk_client_over_refund_adjustment_receipt_recovery` FOREIGN KEY (`recovery_identity`) REFERENCES `client_over_refund_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_over_refund_adjustment_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_over_refund_adjustment_receipt_remaining` CHECK ((`remaining_after_ntd` >= 0)),
  CONSTRAINT `chk_client_over_refund_adjustment_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recovery_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `receipt_ledger_entry_id` bigint NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `remaining_after_ntd` bigint NOT NULL,
  `resulting_status` enum('partially_recovered','recovered') COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_over_refund_recovery_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_client_over_refund_recovery_receipt_bank_row` (`finance_import_row_id`),
  KEY `fk_client_over_refund_recovery_receipt_recovery` (`recovery_identity`),
  KEY `fk_client_over_refund_recovery_receipt_ledger` (`receipt_ledger_entry_id`),
  CONSTRAINT `fk_client_over_refund_recovery_receipt_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_recovery_receipt_ledger` FOREIGN KEY (`receipt_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_recovery_receipt_recovery` FOREIGN KEY (`recovery_identity`) REFERENCES `client_over_refund_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_over_refund_recovery_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_over_refund_recovery_receipt_remaining` CHECK ((`remaining_after_ntd` >= 0)),
  CONSTRAINT `chk_client_over_refund_recovery_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recovery_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('established','collected','authorized_adjustment','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `receipt_ledger_entry_id` bigint DEFAULT NULL,
  `before_amount_ntd` bigint NOT NULL,
  `after_amount_ntd` bigint NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_over_refund_event_idempotency` (`idempotency_key`),
  KEY `fk_client_over_refund_event_recovery` (`recovery_identity`),
  KEY `fk_client_over_refund_event_bank_row` (`finance_import_row_id`),
  KEY `fk_client_over_refund_event_ledger` (`receipt_ledger_entry_id`),
  CONSTRAINT `fk_client_over_refund_event_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_event_ledger` FOREIGN KEY (`receipt_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_over_refund_event_recovery` FOREIGN KEY (`recovery_identity`) REFERENCES `client_over_refund_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_over_refund_event_amount` CHECK (((`after_amount_ntd` >= 0) and (((`event_type` = _utf8mb4'established') and (`before_amount_ntd` = 0) and (`after_amount_ntd` > 0)) or ((`event_type` = _utf8mb4'collected') and (`before_amount_ntd` > `after_amount_ntd`)) or ((`event_type` = _utf8mb4'authorized_adjustment') and (`before_amount_ntd` > `after_amount_ntd`)) or ((`event_type` = _utf8mb4'cancelled') and (`before_amount_ntd` > `after_amount_ntd`))))),
  CONSTRAINT `chk_client_over_refund_recovery_event_evidence` CHECK (((`evidence_reference` is null) or (char_length(trim(`evidence_reference`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recovery_matching_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_recovery_matching_receipt_key` (`idempotency_key`),
  KEY `fk_client_recovery_matching_receipt` (`matching_identity`),
  CONSTRAINT `fk_client_recovery_matching_receipt` FOREIGN KEY (`matching_identity`) REFERENCES `client_over_refund_recovery_matchings` (`matching_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_recovery_matching_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_recovery_matching_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_over_refund_recovery_matchings` (
  `matching_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `recovery_version` bigint unsigned NOT NULL,
  `account_version` bigint unsigned NOT NULL,
  `matching_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`matching_identity`),
  UNIQUE KEY `uq_client_recovery_matching_bank_row` (`finance_import_row_id`),
  UNIQUE KEY `uq_client_recovery_matching_idempotency` (`idempotency_key`),
  KEY `idx_client_recovery_matching_recovery` (`recovery_identity`,`matching_version`),
  KEY `fk_client_recovery_matching_order` (`case_no`),
  CONSTRAINT `fk_client_recovery_matching_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_recovery_matching_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_recovery_matching_recovery` FOREIGN KEY (`recovery_identity`) REFERENCES `client_over_refund_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_over_refund_recovery_matching_evidence` CHECK (((`evidence_reference` is null) or (char_length(trim(`evidence_reference`)) > 0))),
  CONSTRAINT `chk_client_recovery_matching_version` CHECK ((`matching_version` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_destination_configuration_current` (
  `singleton_id` tinyint NOT NULL,
  `current_event_id` bigint NOT NULL,
  `account_display` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `revision` bigint NOT NULL,
  PRIMARY KEY (`singleton_id`),
  UNIQUE KEY `uq_client_payment_destination_current_event` (`current_event_id`),
  CONSTRAINT `fk_client_payment_destination_current_event` FOREIGN KEY (`current_event_id`) REFERENCES `client_payment_destination_configuration_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_payment_destination_current_revision` CHECK ((`revision` > 0)),
  CONSTRAINT `chk_client_payment_destination_current_text` CHECK ((char_length(trim(`account_display`)) > 0)),
  CONSTRAINT `chk_client_payment_destination_singleton` CHECK ((`singleton_id` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_destination_configuration_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `expected_revision` bigint NOT NULL,
  `resulting_revision` bigint NOT NULL,
  `account_display` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payment_destination_event_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_client_payment_destination_event_revision` (`resulting_revision`),
  CONSTRAINT `chk_client_payment_destination_event_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_client_payment_destination_event_revision` CHECK ((`resulting_revision` = (`expected_revision` + 1))),
  CONSTRAINT `chk_client_payment_destination_event_text` CHECK (((char_length(trim(`account_display`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_destination_configuration_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` bigint NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`idempotency_key`),
  UNIQUE KEY `uq_client_payment_destination_receipt_event` (`event_id`),
  CONSTRAINT `fk_client_payment_destination_receipt_event` FOREIGN KEY (`event_id`) REFERENCES `client_payment_destination_configuration_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_payment_destination_receipt_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_client_payment_destination_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_terms` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_hourly_rate_ntd` bigint NOT NULL,
  `deposit_service_days` int unsigned NOT NULL,
  `deposit_due_date` date NOT NULL,
  `first_payment_due_date` date NOT NULL,
  `second_payment_due_date` date DEFAULT NULL,
  `current_event_id` bigint NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  UNIQUE KEY `uq_client_payment_terms_current_event` (`current_event_id`),
  CONSTRAINT `fk_client_payment_terms_current_event` FOREIGN KEY (`current_event_id`) REFERENCES `client_payment_terms_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_payment_terms_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_payment_terms_values` CHECK (((`client_hourly_rate_ntd` > 0) and (char_length(trim(`policy_version`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_terms_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_hourly_rate_ntd` bigint NOT NULL,
  `deposit_service_days` int unsigned NOT NULL,
  `deposit_due_date` date NOT NULL,
  `first_payment_due_date` date NOT NULL,
  `second_payment_due_date` date DEFAULT NULL,
  `expected_account_version` bigint unsigned NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payment_terms_source` (`case_no`,`source_event_identity`),
  UNIQUE KEY `uq_client_payment_terms_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_client_payment_terms_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_payment_terms_event_values` CHECK (((`client_hourly_rate_ntd` > 0) and (char_length(trim(`policy_version`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payment_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `client_payment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `stage` enum('deposit','first_payment','second_payment','subsidy_refund','subsidy_return','adjustment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_type` enum('receipt','refund','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行流水或金流平台唯一識別',
  `finance_import_row_id` bigint DEFAULT NULL COMMENT 'canonical 銀行流水；人工補登允許 NULL',
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payment_tx_reference` (`external_reference`),
  KEY `idx_client_payment_tx_case_stage` (`case_no`,`stage`),
  KEY `fk_client_payment_tx_summary` (`client_payment_id`),
  KEY `fk_client_payment_tx_reversal` (`reversal_of_transaction_id`),
  KEY `idx_client_payment_tx_finance_import_row` (`finance_import_row_id`),
  CONSTRAINT `fk_client_payment_tx_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_client_payment_tx_finance_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_payment_tx_reversal` FOREIGN KEY (`reversal_of_transaction_id`) REFERENCES `client_payment_transactions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_client_payment_tx_summary` FOREIGN KEY (`client_payment_id`) REFERENCES `client_payments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_payments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '唯一案件鍵，對應 orders.case_no',
  `deposit_receivable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `deposit_received` decimal(12,2) NOT NULL DEFAULT '0.00',
  `deposit_due_date` date DEFAULT NULL,
  `deposit_received_at` date DEFAULT NULL COMMENT '訂金全額核銷日；部分入款見交易明細',
  `first_payment_receivable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `first_payment_received` decimal(12,2) NOT NULL DEFAULT '0.00',
  `first_payment_due_date` date DEFAULT NULL,
  `first_payment_received_at` date DEFAULT NULL COMMENT '第一期全額核銷日',
  `second_payment_receivable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `second_payment_received` decimal(12,2) NOT NULL DEFAULT '0.00',
  `second_payment_due_date` date DEFAULT NULL,
  `second_payment_received_at` date DEFAULT NULL COMMENT '第二期全額核銷日',
  `amount_receivable` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '三階段應收總額',
  `amount_received` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '三階段實收總額',
  `subsidy_refund_receivable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `subsidy_refund_refunded` decimal(12,2) NOT NULL DEFAULT '0.00',
  `subsidy_refund_due_date` date DEFAULT NULL,
  `subsidy_refund_at` date DEFAULT NULL COMMENT '補助退款全額完成日',
  `subsidy_return_receivable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `subsidy_return_refunded` decimal(12,2) NOT NULL DEFAULT '0.00',
  `subsidy_return_due_date` date DEFAULT NULL,
  `subsidy_return_at` date DEFAULT NULL,
  `subsidy_return_review_status` enum('review_required') COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助退還人工覆核狀態；NULL 表示未暫停自動核銷',
  `subsidy_return_review_reason` text COLLATE utf8mb4_unicode_ci COMMENT '補助退還需人工覆核的原因',
  `payment_status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '待收訂金',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payments_case_no` (`case_no`),
  CONSTRAINT `fk_client_payments_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_profile_admin_change_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `client_id` int NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_values_json` json NOT NULL,
  `after_values_json` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_profile_admin_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_client_profile_admin_event_version` (`client_id`,`resulting_version`),
  CONSTRAINT `fk_client_profile_admin_event_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_profile_admin_event_payload` CHECK (((json_type(`before_values_json`) = _utf8mb4'OBJECT') and (json_type(`after_values_json`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_client_profile_admin_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_profile_change_apply_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_json` json NOT NULL,
  `created_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`),
  CONSTRAINT `chk_client_profile_change_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_profile_change_receipt_result` CHECK ((json_type(`result_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_profile_change_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_id` bigint NOT NULL,
  `client_id` int NOT NULL,
  `event_type` enum('approved_applied','rejected') COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_profile_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_values_json` json NOT NULL,
  `after_values_json` json NOT NULL,
  `created_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_profile_change_event_key` (`idempotency_key`),
  KEY `idx_client_profile_change_event_request` (`request_id`,`id`),
  KEY `fk_client_profile_change_event_client` (`client_id`),
  CONSTRAINT `fk_client_profile_change_event_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_profile_change_event_request` FOREIGN KEY (`request_id`) REFERENCES `client_profile_change_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_profile_change_event_payload` CHECK (((json_type(`before_values_json`) = _utf8mb4'OBJECT') and (json_type(`after_values_json`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_profile_change_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_id` bigint NOT NULL,
  `event_type` enum('client_profile.approved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_json` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `delivered_at_utc` datetime DEFAULT NULL,
  `last_error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_profile_change_outbox_key` (`idempotency_key`,`event_type`),
  KEY `idx_client_profile_change_outbox_due` (`status`,`next_attempt_at_utc`,`id`),
  KEY `fk_client_profile_change_outbox_request` (`request_id`),
  CONSTRAINT `fk_client_profile_change_outbox_request` FOREIGN KEY (`request_id`) REFERENCES `client_profile_change_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_profile_change_outbox_payload` CHECK ((json_type(`payload_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_profile_change_requests` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '提出異動申請的 LINE 用戶',
  `client_id` int NOT NULL COMMENT '欲異動的客戶資料',
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '申請當下的案件編號',
  `ticket_id` bigint DEFAULT NULL COMMENT '關聯客服單',
  `status` enum('pending','approved','approved_applied','partially_approved','rejected','reverted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `request_version` bigint unsigned NOT NULL DEFAULT '0',
  `client_profile_version` bigint unsigned NOT NULL DEFAULT '0',
  `requested_changes_json` json NOT NULL COMMENT '用戶送出的欄位異動內容',
  `old_values_json` json NOT NULL COMMENT '送出當下 DB 原始值快照',
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `applied_values_json` json DEFAULT NULL COMMENT '審核通過後實際套用的新值',
  `rejection_reason` text COLLATE utf8mb4_unicode_ci,
  `review_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reviewed_by_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '審核人員姓名快照',
  `reviewed_by_admin_user_id` bigint DEFAULT NULL COMMENT '審核工會人員',
  `reviewed_at` datetime DEFAULT NULL COMMENT '審核時間',
  `reverted_by_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '回復人員姓名快照',
  `reverted_by_admin_user_id` bigint DEFAULT NULL COMMENT '回復工會人員',
  `reverted_at` datetime DEFAULT NULL COMMENT '回復時間',
  `revert_reason` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_profile_change_request_idempotency` (`idempotency_key`),
  KEY `idx_client_profile_change_status_time` (`status`,`created_at`),
  KEY `idx_client_profile_change_line_user` (`line_user_id`,`created_at`),
  KEY `idx_client_profile_change_client` (`client_id`,`created_at`),
  KEY `idx_client_profile_change_ticket` (`ticket_id`),
  KEY `fk_client_profile_change_reviewer` (`reviewed_by_admin_user_id`),
  KEY `fk_client_profile_change_reverter` (`reverted_by_admin_user_id`),
  CONSTRAINT `fk_client_profile_change_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_client_profile_change_reverter` FOREIGN KEY (`reverted_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_client_profile_change_reviewer` FOREIGN KEY (`reviewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_client_profile_change_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `customer_service_tickets` (`id`) ON DELETE SET NULL,
  CONSTRAINT `chk_client_profile_change_request_fingerprints` CHECK ((((`preview_fingerprint` is null) or regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')) and ((`command_fingerprint` is null) or regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_receipt_overage_dispositions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `receipt_ledger_entry_id` bigint NOT NULL,
  `receivable_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `refund_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `overage_amount_ntd` bigint NOT NULL,
  `settlement_identity` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_receipt_overage_bank_row` (`finance_import_row_id`),
  UNIQUE KEY `uq_client_receipt_overage_ledger` (`receipt_ledger_entry_id`),
  UNIQUE KEY `uq_client_receipt_overage_refund` (`refund_obligation_identity`),
  UNIQUE KEY `uq_client_receipt_overage_idempotency` (`idempotency_key`),
  KEY `fk_client_receipt_overage_order` (`case_no`),
  KEY `fk_client_receipt_overage_receivable` (`receivable_obligation_identity`),
  CONSTRAINT `fk_client_receipt_overage_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_receipt_overage_ledger` FOREIGN KEY (`receipt_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_receipt_overage_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_receipt_overage_receivable` FOREIGN KEY (`receivable_obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_receipt_overage_refund` FOREIGN KEY (`refund_obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_receipt_overage_amount` CHECK ((`overage_amount_ntd` > 0)),
  CONSTRAINT `chk_client_receipt_overage_settlement` CHECK (regexp_like(`settlement_identity`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_recipient_snapshots` (
  `refund_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_code` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_account` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`refund_obligation_identity`),
  KEY `fk_client_refund_snapshot_order` (`case_no`),
  CONSTRAINT `fk_client_refund_snapshot_obligation` FOREIGN KEY (`refund_obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_snapshot_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_snapshot_account` CHECK (((char_length(trim(`bank_code`)) > 0) and (char_length(trim(`bank_account`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_return_review_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `finance_import_row_id` bigint NOT NULL,
  `original_refund_ledger_entry_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_refund_return_review_bank_refund` (`finance_import_row_id`,`original_refund_ledger_entry_id`),
  UNIQUE KEY `uq_client_refund_return_review_idempotency` (`idempotency_key`),
  KEY `idx_client_refund_return_review_case` (`case_no`,`created_at`,`id`),
  KEY `fk_client_refund_return_review_ledger` (`original_refund_ledger_entry_id`),
  CONSTRAINT `fk_client_refund_return_review_ledger` FOREIGN KEY (`original_refund_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_return_review_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_return_review_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_return_review_evidence` CHECK ((json_type(`evidence`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_client_refund_return_review_text` CHECK (((char_length(trim(`reason`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_return_review_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `review_event_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_refund_return_review_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_client_refund_return_review_receipt_event` (`review_event_id`),
  KEY `fk_client_refund_return_review_receipt_row` (`finance_import_row_id`),
  CONSTRAINT `fk_client_refund_return_review_receipt_event` FOREIGN KEY (`review_event_id`) REFERENCES `client_refund_return_review_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_return_review_receipt_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_return_review_receipt_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_client_refund_return_review_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_reversal_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correction_type` enum('refund','refund_return','reversal','refund_overage') COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_account_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_refund_reversal_receipt_key` (`idempotency_key`),
  KEY `idx_client_refund_reversal_case` (`case_no`,`correction_type`,`created_at`),
  CONSTRAINT `fk_client_refund_reversal_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_reversal_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_client_refund_reversal_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_underpayment_source_bank_rows` (
  `underpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `ordinal` int NOT NULL,
  PRIMARY KEY (`underpayment_identity`,`finance_import_row_id`),
  UNIQUE KEY `uq_client_refund_underpayment_consumed_row` (`finance_import_row_id`),
  CONSTRAINT `fk_client_refund_underpayment_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_underpayment_row_source` FOREIGN KEY (`underpayment_identity`) REFERENCES `client_refund_underpayment_sources` (`underpayment_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_underpayment_row_ordinal` CHECK ((`ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_underpayment_source_obligations` (
  `underpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `refund_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `remaining_after_ntd` bigint NOT NULL,
  PRIMARY KEY (`underpayment_identity`,`refund_obligation_identity`),
  KEY `fk_client_refund_underpayment_obligation` (`refund_obligation_identity`),
  CONSTRAINT `fk_client_refund_underpayment_obligation` FOREIGN KEY (`refund_obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_refund_underpayment_obligation_source` FOREIGN KEY (`underpayment_identity`) REFERENCES `client_refund_underpayment_sources` (`underpayment_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_underpayment_obligation_remaining` CHECK ((`remaining_after_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_refund_underpayment_sources` (
  `underpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_total_ntd` bigint NOT NULL,
  `remaining_after_ntd` bigint NOT NULL,
  `resulting_account_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`underpayment_identity`),
  UNIQUE KEY `uq_client_refund_underpayment_idempotency` (`idempotency_key`),
  KEY `fk_client_refund_underpayment_order` (`case_no`),
  CONSTRAINT `fk_client_refund_underpayment_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_refund_underpayment_amount` CHECK (((`bank_total_ntd` > 0) and (`remaining_after_ntd` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_subsidy_advance_recoveries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `advance_ledger_entry_id` bigint NOT NULL,
  `government_allocation_id` bigint NOT NULL,
  `recovered_amount_ntd` bigint unsigned NOT NULL,
  `source_outbox_id` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_subsidy_advance_recovery` (`advance_ledger_entry_id`,`government_allocation_id`),
  UNIQUE KEY `uq_client_subsidy_advance_once` (`advance_ledger_entry_id`),
  UNIQUE KEY `uq_client_subsidy_recovery_outbox_advance` (`source_outbox_id`,`advance_ledger_entry_id`),
  KEY `idx_client_subsidy_recovery_case` (`case_no`,`created_at`),
  KEY `fk_client_subsidy_recovery_allocation` (`government_allocation_id`),
  CONSTRAINT `fk_client_subsidy_recovery_advance` FOREIGN KEY (`advance_ledger_entry_id`) REFERENCES `client_ledger_entries` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_subsidy_recovery_allocation` FOREIGN KEY (`government_allocation_id`) REFERENCES `government_subsidy_allocations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_subsidy_recovery_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_subsidy_recovery_outbox` FOREIGN KEY (`source_outbox_id`) REFERENCES `government_subsidy_outbox` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_subsidy_recovery_amount` CHECK ((`recovered_amount_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_subsidy_identity_label_changes` (
  `client_id` int NOT NULL,
  `before_identity` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_identity` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`client_id`),
  CONSTRAINT `fk_subsidy_identity_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_subsidy_policy_migrations` (
  `policy_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`policy_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `client_subsidy_return_claim_item_links` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `claim_item_id` bigint NOT NULL,
  `entitled_amount_ntd` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_subsidy_return_claim_item` (`obligation_identity`,`claim_item_id`),
  KEY `idx_client_subsidy_return_claim_item` (`claim_item_id`),
  CONSTRAINT `fk_client_subsidy_return_link_claim_item` FOREIGN KEY (`claim_item_id`) REFERENCES `subsidy_claim_batch_items` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_subsidy_return_link_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_subsidy_return_link_amount` CHECK ((`entitled_amount_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `clients` (
  `id` int NOT NULL AUTO_INCREMENT,
  `seq_num` int DEFAULT NULL COMMENT '項次',
  `reject_reason` text COLLATE utf8mb4_unicode_ci COMMENT '不符合原因',
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '查詢序號(案件編號) - 去重唯一識別碼',
  `created_at` datetime DEFAULT NULL COMMENT '報名時間(建檔)',
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'IP位址',
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '姓名',
  `gender` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '性別',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `city` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '縣市',
  `address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '地址',
  `identity_status` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '身分資格',
  `service_time` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '服務時間',
  `due_month` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '預產期/預計服務開始月份',
  `service_start_date` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '預計服務日期',
  `notes` text COLLATE utf8mb4_unicode_ci COMMENT '其他事項',
  `service_days` int DEFAULT NULL COMMENT '希望服務天數',
  `residence_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '居住型態',
  `delivery_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '生產方式',
  `service_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '服務方式',
  `baby_info` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '寶寶資訊',
  `line_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE ID',
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
  `admin_notes` text COLLATE utf8mb4_unicode_ci COMMENT '管理者註記事項',
  `db_created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '資料庫匯入時間',
  `db_updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '資料庫更新時間',
  `client_hcm_correction_version` bigint unsigned NOT NULL DEFAULT '0' COMMENT 'Client-owned HCM correction aggregate version',
  `client_profile_version` bigint unsigned NOT NULL DEFAULT '0',
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'HCM Email',
  PRIMARY KEY (`id`),
  UNIQUE KEY `case_no` (`case_no`),
  KEY `idx_case_no` (`case_no`),
  KEY `idx_phone` (`phone`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `confirmed_service_date_days` (
  `confirmed_version_id` bigint unsigned NOT NULL,
  `ordinal` int unsigned NOT NULL,
  `service_date` date NOT NULL,
  PRIMARY KEY (`confirmed_version_id`,`ordinal`),
  UNIQUE KEY `uq_confirmed_service_date_day` (`confirmed_version_id`,`service_date`),
  CONSTRAINT `fk_confirmed_service_date_day_version` FOREIGN KEY (`confirmed_version_id`) REFERENCES `confirmed_service_date_versions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `confirmed_service_date_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `confirmed_version_id` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_confirmed_service_date_receipt_key` (`idempotency_key`),
  KEY `fk_confirmed_service_date_receipt_version` (`confirmed_version_id`),
  CONSTRAINT `fk_confirmed_service_date_receipt_version` FOREIGN KEY (`confirmed_version_id`) REFERENCES `confirmed_service_date_versions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `confirmed_service_date_versions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` int unsigned NOT NULL,
  `order_version` int unsigned NOT NULL,
  `scheduling_version` int unsigned NOT NULL,
  `service_day_count` int unsigned NOT NULL,
  `service_date_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_current` tinyint DEFAULT NULL,
  `confirmed_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `confirmed_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `invalidated_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_confirmed_service_date_version` (`case_no`,`version`),
  UNIQUE KEY `uq_confirmed_service_date_current` (`case_no`,`is_current`),
  CONSTRAINT `fk_confirmed_service_date_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`),
  CONSTRAINT `chk_confirmed_service_date_current` CHECK (((`is_current` is null) or (`is_current` = 1))),
  CONSTRAINT `chk_confirmed_service_date_fingerprint` CHECK (regexp_like(`service_date_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_document_access_grants` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `document_version_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_subject_type` enum('customer','staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_document_access_token` (`token_sha256`),
  KEY `idx_contract_document_access_document` (`document_version_id`,`recipient_line_user_id`,`expires_at`),
  KEY `fk_contract_document_access_case` (`case_no`),
  CONSTRAINT `fk_contract_document_access_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_access_document` FOREIGN KEY (`document_version_id`) REFERENCES `contract_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_document_access_text` CHECK (((char_length(trim(`recipient_line_user_id`)) > 0) and (char_length(trim(`recipient_subject_reference`)) > 0) and (char_length(trim(`created_by`)) > 0))),
  CONSTRAINT `chk_contract_document_access_token` CHECK (regexp_like(`token_sha256`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_document_versions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `document_scope` enum('staff_segment','client_contract') COLLATE utf8mb4_unicode_ci NOT NULL,
  `document_role` enum('template_generated','signed_return') COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_plan_id` bigint NOT NULL,
  `matching_segment_id` bigint DEFAULT NULL,
  `document_target_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_document_version_id` bigint DEFAULT NULL,
  `template_key` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `template_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mapping_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `facts_snapshot_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `media_asset_id` bigint NOT NULL,
  `version_number` int NOT NULL,
  `replaces_document_version_id` bigint DEFAULT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_document_version` (`case_no`,`document_scope`,`document_target_key`,`version_number`),
  KEY `idx_contract_document_case` (`case_no`,`document_scope`,`created_at`),
  KEY `idx_contract_document_segment` (`matching_segment_id`,`created_at`),
  KEY `fk_contract_document_plan` (`matching_plan_id`),
  KEY `fk_contract_document_source` (`source_document_version_id`),
  KEY `fk_contract_document_media_asset` (`media_asset_id`),
  KEY `fk_contract_document_replaces` (`replaces_document_version_id`),
  CONSTRAINT `fk_contract_document_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_media_asset` FOREIGN KEY (`media_asset_id`) REFERENCES `media_assets` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_plan` FOREIGN KEY (`matching_plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_replaces` FOREIGN KEY (`replaces_document_version_id`) REFERENCES `contract_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_segment` FOREIGN KEY (`matching_segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_document_source` FOREIGN KEY (`source_document_version_id`) REFERENCES `contract_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_document_source` CHECK ((((`document_role` = _utf8mb4'template_generated') and (`template_key` is not null) and (`template_sha256` is not null) and (`mapping_sha256` is not null) and (`facts_snapshot_sha256` is not null) and (`source_document_version_id` is null)) or ((`document_role` = _utf8mb4'signed_return') and (`source_document_version_id` is not null)))),
  CONSTRAINT `chk_contract_document_target` CHECK ((((`document_scope` = _utf8mb4'staff_segment') and (`matching_segment_id` is not null) and (char_length(trim(`document_target_key`)) > 0)) or ((`document_scope` = _utf8mb4'client_contract') and (`matching_segment_id` is null) and (char_length(trim(`document_target_key`)) > 0)))),
  CONSTRAINT `chk_contract_document_version` CHECK (((`version_number` >= 1) and (char_length(trim(`created_by`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_external_completion_reports` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `report_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `external_signing_session_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `report_scope` enum('staff','client') COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_segment_id` bigint DEFAULT NULL,
  `document_version_id` bigint NOT NULL,
  `commitment_id` bigint DEFAULT NULL,
  `reporter_subject_type` enum('staff','customer') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reporter_subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` enum('verified_line','manual_attested') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_payload_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_inbox_event_id` bigint unsigned DEFAULT NULL,
  `verified_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `verified_binding_version` bigint unsigned DEFAULT NULL,
  `manual_confirmation_method` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manual_reason` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manual_evidence_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `manual_evidence_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `target_identity` varchar(191) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS (concat(`report_scope`,_utf8mb4':',coalesce(cast(`matching_segment_id` as char charset utf8mb4),_utf8mb4'client'))) STORED,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_status_version` bigint unsigned NOT NULL,
  `resulting_status_version` bigint unsigned NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_external_report_id` (`report_id`),
  UNIQUE KEY `uq_contract_external_report_source` (`source_event_identity`),
  UNIQUE KEY `uq_contract_external_report_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_contract_external_report_target` (`external_signing_session_id`,`target_identity`),
  KEY `idx_contract_external_report_case` (`case_no`,`id`),
  KEY `idx_contract_external_report_document` (`document_version_id`,`id`),
  KEY `idx_contract_external_report_segment` (`matching_segment_id`,`id`),
  KEY `fk_contract_external_report_commitment` (`commitment_id`),
  KEY `fk_contract_external_report_inbox` (`line_inbox_event_id`),
  KEY `fk_contract_external_report_binding` (`verified_line_user_id`),
  CONSTRAINT `fk_contract_external_report_binding` FOREIGN KEY (`verified_line_user_id`) REFERENCES `line_identity_bindings` (`line_user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_commitment` FOREIGN KEY (`commitment_id`) REFERENCES `precontract_service_commitments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_document` FOREIGN KEY (`document_version_id`) REFERENCES `contract_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_inbox` FOREIGN KEY (`line_inbox_event_id`) REFERENCES `line_inbox_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_segment` FOREIGN KEY (`matching_segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_report_session` FOREIGN KEY (`external_signing_session_id`) REFERENCES `contract_external_signing_sessions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_external_report_identity` CHECK ((regexp_like(`report_id`,_utf8mb4'^cer_[0-9a-f]{32}$') and regexp_like(`source_payload_sha256`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`source_event_identity`)) > 0) and (char_length(trim(`reporter_subject_reference`)) > 0) and (char_length(trim(`actor_ref`)) > 0) and (`resulting_status_version` = (`expected_status_version` + 1)))),
  CONSTRAINT `chk_contract_external_report_source` CHECK ((((`source_kind` = _utf8mb4'verified_line') and (`line_inbox_event_id` is not null) and (`verified_line_user_id` is not null) and (`verified_binding_version` is not null) and (`manual_confirmation_method` is null) and (`manual_reason` is null) and (`manual_evidence_reference` is null) and (`manual_evidence_sha256` is null)) or ((`source_kind` = _utf8mb4'manual_attested') and (`line_inbox_event_id` is null) and (`verified_line_user_id` is null) and (`verified_binding_version` is null) and (`manual_confirmation_method` is not null) and (`manual_reason` is not null) and (`manual_evidence_reference` is not null) and (`manual_evidence_sha256` is not null) and (char_length(trim(`manual_confirmation_method`)) > 0) and (char_length(trim(`manual_reason`)) > 0) and (char_length(trim(`manual_evidence_reference`)) > 0) and regexp_like(`manual_evidence_sha256`,_utf8mb4'^[0-9a-f]{64}$')))),
  CONSTRAINT `chk_contract_external_report_target` CHECK ((((`report_scope` = _utf8mb4'staff') and (`matching_segment_id` is not null) and (`commitment_id` is null) and (`reporter_subject_type` = _utf8mb4'staff')) or ((`report_scope` = _utf8mb4'client') and (`matching_segment_id` is null) and (`commitment_id` is not null) and (`reporter_subject_type` = _utf8mb4'customer'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_external_signing_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `external_signing_session_id` bigint unsigned NOT NULL,
  `command_type` enum('record_staff_report','record_client_report','apply_final_signed_contract') COLLATE utf8mb4_unicode_ci NOT NULL,
  `schema_version` enum('contract-external-signing-receipt.v1') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_status_version` bigint unsigned NOT NULL,
  `result_status_version` bigint unsigned NOT NULL,
  `completion_report_id` bigint unsigned DEFAULT NULL,
  `final_document_version_id` bigint unsigned DEFAULT NULL,
  `result_snapshot` json NOT NULL,
  `outcome_state` enum('recorded','completed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_external_receipt_id` (`receipt_id`),
  UNIQUE KEY `uq_contract_external_receipt_idempotency` (`idempotency_key`),
  KEY `idx_contract_external_receipt_session` (`external_signing_session_id`,`id`),
  KEY `idx_contract_external_receipt_report` (`completion_report_id`,`id`),
  KEY `idx_contract_external_receipt_document` (`final_document_version_id`,`id`),
  CONSTRAINT `fk_contract_external_receipt_document` FOREIGN KEY (`final_document_version_id`) REFERENCES `contract_final_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_receipt_report` FOREIGN KEY (`completion_report_id`) REFERENCES `contract_external_completion_reports` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_receipt_session` FOREIGN KEY (`external_signing_session_id`) REFERENCES `contract_external_signing_sessions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_external_receipt_identity` CHECK ((regexp_like(`receipt_id`,_utf8mb4'^cesr_[0-9a-f]{32}$') and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`actor_ref`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (`result_status_version` = (`expected_status_version` + 1)))),
  CONSTRAINT `chk_contract_external_receipt_result` CHECK (((json_type(`result_snapshot`) = _utf8mb4'OBJECT') and (json_length(`result_snapshot`) > 0))),
  CONSTRAINT `chk_contract_external_receipt_target` CHECK ((((`command_type` in (_utf8mb4'record_staff_report',_utf8mb4'record_client_report')) and (`completion_report_id` is not null) and (`final_document_version_id` is null) and (`preview_fingerprint` is null) and (`outcome_state` = _utf8mb4'recorded')) or ((`command_type` = _utf8mb4'apply_final_signed_contract') and (`completion_report_id` is null) and (`final_document_version_id` is not null) and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (`outcome_state` = _utf8mb4'completed'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_external_signing_sessions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `external_signing_session_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_plan_id` bigint NOT NULL,
  `current_document_set_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `commitment_id` bigint DEFAULT NULL,
  `client_reminder_task_id` bigint unsigned DEFAULT NULL,
  `session_state` enum('staff_reporting','staff_reports_complete','client_reported_final_pdf_pending','completed','superseded') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'staff_reporting',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `active_case_key` varchar(50) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS ((case when (`session_state` = _utf8mb4'superseded') then NULL else `case_no` end)) STORED,
  `activated_by_actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_external_session_id` (`external_signing_session_id`),
  UNIQUE KEY `uq_contract_external_active_case` (`active_case_key`),
  KEY `idx_contract_external_session_case` (`case_no`,`id`),
  KEY `idx_contract_external_session_plan` (`matching_plan_id`,`id`),
  KEY `idx_contract_external_session_state` (`session_state`,`updated_at_utc`,`id`),
  KEY `fk_contract_external_session_commitment` (`commitment_id`),
  KEY `fk_contract_external_session_reminder` (`client_reminder_task_id`),
  CONSTRAINT `fk_contract_external_session_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_session_commitment` FOREIGN KEY (`commitment_id`) REFERENCES `precontract_service_commitments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_session_plan` FOREIGN KEY (`matching_plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_external_session_reminder` FOREIGN KEY (`client_reminder_task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_external_session_identity` CHECK ((regexp_like(`external_signing_session_id`,_utf8mb4'^ces_[0-9a-f]{32}$') and regexp_like(`current_document_set_sha256`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`activated_by_actor`)) > 0))),
  CONSTRAINT `chk_contract_external_session_state` CHECK ((((`session_state` = _utf8mb4'staff_reporting') and (`commitment_id` is null)) or ((`session_state` in (_utf8mb4'staff_reports_complete',_utf8mb4'client_reported_final_pdf_pending',_utf8mb4'completed')) and (`commitment_id` is not null)) or (`session_state` = _utf8mb4'superseded')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_final_document_versions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `final_document_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `external_signing_session_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_document_set_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `controlled_file_object_id` bigint unsigned NOT NULL,
  `version_number` bigint unsigned NOT NULL,
  `contract_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type` enum('application/pdf') COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` bigint unsigned NOT NULL,
  `content_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by_actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_final_document_id` (`final_document_id`),
  UNIQUE KEY `uq_contract_final_document_session` (`external_signing_session_id`),
  UNIQUE KEY `uq_contract_final_document_object` (`controlled_file_object_id`),
  UNIQUE KEY `uq_contract_final_document_case_version` (`case_no`,`version_number`),
  KEY `idx_contract_final_document_case` (`case_no`,`id`),
  CONSTRAINT `fk_contract_final_document_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_final_document_object` FOREIGN KEY (`controlled_file_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_final_document_session` FOREIGN KEY (`external_signing_session_id`) REFERENCES `contract_external_signing_sessions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_final_document_identity` CHECK ((regexp_like(`final_document_id`,_utf8mb4'^cfd_[0-9a-f]{32}$') and regexp_like(`source_document_set_sha256`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`content_sha256`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`contract_identity`)) > 0) and (char_length(trim(`created_by_actor`)) > 0) and (`version_number` > 0) and (`size_bytes` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_final_pdf_recovery_tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `recovery_task_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `external_signing_session_id` bigint unsigned NOT NULL,
  `client_report_id` bigint unsigned NOT NULL,
  `task_state` enum('pending','fulfilled','superseded') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by_actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `fulfilled_at_utc` datetime(6) DEFAULT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_final_recovery_id` (`recovery_task_id`),
  UNIQUE KEY `uq_contract_final_recovery_report` (`client_report_id`),
  UNIQUE KEY `uq_contract_final_recovery_idempotency` (`idempotency_key`),
  KEY `idx_contract_final_recovery_session` (`external_signing_session_id`,`id`),
  KEY `idx_contract_final_recovery_state` (`task_state`,`created_at_utc`,`id`),
  CONSTRAINT `fk_contract_final_recovery_report` FOREIGN KEY (`client_report_id`) REFERENCES `contract_external_completion_reports` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_final_recovery_session` FOREIGN KEY (`external_signing_session_id`) REFERENCES `contract_external_signing_sessions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_final_recovery_identity` CHECK ((regexp_like(`recovery_task_id`,_utf8mb4'^cfrt_[0-9a-f]{32}$') and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`created_by_actor`)) > 0))),
  CONSTRAINT `chk_contract_final_recovery_state` CHECK ((((`task_state` = _utf8mb4'fulfilled') and (`fulfilled_at_utc` is not null)) or ((`task_state` in (_utf8mb4'pending',_utf8mb4'superseded')) and (`fulfilled_at_utc` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_signing_command_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `document_version_id` bigint DEFAULT NULL,
  `signing_event_id` bigint DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_signing_receipt_key` (`idempotency_key`),
  KEY `fk_contract_signing_receipt_case` (`case_no`),
  KEY `fk_contract_signing_receipt_document` (`document_version_id`),
  KEY `fk_contract_signing_receipt_event` (`signing_event_id`),
  CONSTRAINT `fk_contract_signing_receipt_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`),
  CONSTRAINT `fk_contract_signing_receipt_document` FOREIGN KEY (`document_version_id`) REFERENCES `contract_document_versions` (`id`),
  CONSTRAINT `fk_contract_signing_receipt_event` FOREIGN KEY (`signing_event_id`) REFERENCES `contract_signing_events` (`id`),
  CONSTRAINT `chk_contract_signing_receipt_payload` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_signing_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `document_version_id` bigint NOT NULL,
  `matching_plan_id` bigint NOT NULL,
  `matching_segment_id` bigint DEFAULT NULL,
  `event_type` enum('sent','signed_received') COLLATE utf8mb4_unicode_ci NOT NULL,
  `delivery_channel` enum('line') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `line_delivery_task_id` bigint unsigned DEFAULT NULL,
  `document_access_grant_id` bigint unsigned DEFAULT NULL,
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_signing_event_key` (`event_key`),
  KEY `idx_contract_signing_event_case` (`case_no`,`occurred_at`),
  KEY `idx_contract_signing_event_document` (`document_version_id`,`occurred_at`),
  KEY `idx_contract_signing_event_segment` (`matching_segment_id`,`occurred_at`),
  KEY `fk_contract_signing_event_plan` (`matching_plan_id`),
  KEY `fk_contract_signing_event_line_delivery_task` (`line_delivery_task_id`),
  KEY `fk_contract_signing_event_document_access_grant` (`document_access_grant_id`),
  CONSTRAINT `fk_contract_signing_event_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_signing_event_document` FOREIGN KEY (`document_version_id`) REFERENCES `contract_document_versions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_signing_event_document_access_grant` FOREIGN KEY (`document_access_grant_id`) REFERENCES `contract_document_access_grants` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_signing_event_line_delivery_task` FOREIGN KEY (`line_delivery_task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_signing_event_plan` FOREIGN KEY (`matching_plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_contract_signing_event_segment` FOREIGN KEY (`matching_segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_contract_signing_event_channel` CHECK ((((`event_type` = _utf8mb4'sent') and (`delivery_channel` = _utf8mb4'line') and (`line_delivery_task_id` is not null) and (`document_access_grant_id` is not null)) or ((`event_type` = _utf8mb4'signed_received') and (`delivery_channel` is null) and (`line_delivery_task_id` is null) and (`document_access_grant_id` is null)))),
  CONSTRAINT `chk_contract_signing_event_payload` CHECK (((json_type(`payload`) = _utf8mb4'OBJECT') and (char_length(trim(`event_key`)) > 0) and (char_length(trim(`actor`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `contract_signing_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `signing_event_id` bigint NOT NULL,
  `intent_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_signing_outbox_key` (`intent_key`),
  KEY `fk_contract_signing_outbox_case` (`case_no`),
  KEY `fk_contract_signing_outbox_event` (`signing_event_id`),
  CONSTRAINT `fk_contract_signing_outbox_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`),
  CONSTRAINT `fk_contract_signing_outbox_event` FOREIGN KEY (`signing_event_id`) REFERENCES `contract_signing_events` (`id`),
  CONSTRAINT `chk_contract_signing_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_apply_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_object_id` bigint unsigned NOT NULL,
  `controlled_object_id` bigint unsigned NOT NULL,
  `command_type` enum('controlled_file_apply') COLLATE utf8mb4_unicode_ci NOT NULL,
  `schema_version` enum('controlled-file-apply-receipt.v1') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_staging_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `outcome_state` enum('created') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'created',
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_receipt_id` (`receipt_id`),
  UNIQUE KEY `uq_controlled_file_receipt_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_controlled_file_receipt_staging` (`staging_object_id`),
  UNIQUE KEY `uq_controlled_file_receipt_object` (`controlled_object_id`),
  CONSTRAINT `fk_controlled_file_receipt_object` FOREIGN KEY (`controlled_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_controlled_file_receipt_staging` FOREIGN KEY (`staging_object_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_controlled_file_receipt_identity` CHECK ((regexp_like(`receipt_id`,_utf8mb4'^cfr_[0-9a-f]{32}$') and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`actor_ref`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (`expected_staging_version` > 0))),
  CONSTRAINT `chk_controlled_file_receipt_result` CHECK (((json_type(`result_snapshot`) = _utf8mb4'OBJECT') and (json_length(`result_snapshot`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_cleanup_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `cleanup_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_object_id` bigint unsigned NOT NULL,
  `event_sequence` tinyint unsigned NOT NULL,
  `event_type` enum('intent','completed','reconciliation_required') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` enum('expired','abandoned') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_staging_version` bigint unsigned NOT NULL,
  `expected_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_cleanup_event` (`event_id`),
  UNIQUE KEY `uq_controlled_file_cleanup_sequence` (`cleanup_id`,`event_sequence`),
  UNIQUE KEY `uq_controlled_file_cleanup_idempotency_sequence` (`idempotency_key`,`event_sequence`),
  KEY `idx_controlled_file_cleanup_staging` (`staging_object_id`,`event_sequence`,`id`),
  KEY `idx_controlled_file_cleanup_terminal` (`event_type`,`occurred_at_utc`,`id`),
  CONSTRAINT `fk_controlled_file_cleanup_staging` FOREIGN KEY (`staging_object_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_cleanup_event` CHECK ((((`event_sequence` = 1) and (`event_type` = _utf8mb4'intent') and (`error_code` is null)) or ((`event_sequence` = 2) and (`event_type` = _utf8mb4'completed') and (`error_code` is null)) or ((`event_sequence` = 2) and (`event_type` = _utf8mb4'reconciliation_required') and (`error_code` is not null) and (char_length(trim(`error_code`)) > 0)))),
  CONSTRAINT `chk_controlled_file_cleanup_identity` CHECK ((regexp_like(`cleanup_id`,_utf8mb4'^cfc_[0-9a-f]{32}$') and regexp_like(`event_id`,_utf8mb4'^cfce_[0-9a-f]{32}$') and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (`expected_staging_version` > 0) and regexp_like(`expected_sha256`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`actor_ref`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_finalize_intents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `finalize_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_object_id` bigint unsigned NOT NULL,
  `controlled_file_object_id` bigint unsigned NOT NULL,
  `expected_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finalize_state` enum('pending','processing','available','reconciliation_required') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `claimed_by` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claim_token` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claimed_at_utc` datetime(6) DEFAULT NULL,
  `observed_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `observed_size_bytes` bigint unsigned DEFAULT NULL,
  `last_error_code` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `available_at_utc` datetime(6) DEFAULT NULL,
  `failed_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_finalize_id` (`finalize_id`),
  UNIQUE KEY `uq_controlled_file_finalize_staging` (`staging_object_id`),
  UNIQUE KEY `uq_controlled_file_finalize_object` (`controlled_file_object_id`),
  KEY `idx_controlled_file_finalize_claim` (`finalize_state`,`claimed_at_utc`,`id`),
  CONSTRAINT `fk_controlled_file_finalize_object` FOREIGN KEY (`controlled_file_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_controlled_file_finalize_staging` FOREIGN KEY (`staging_object_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_finalize_identity` CHECK ((regexp_like(`finalize_id`,_utf8mb4'^cff_[0-9a-f]{32}$') and regexp_like(`expected_sha256`,_utf8mb4'^[0-9a-f]{64}$') and ((`claimed_by` is null) or (char_length(trim(`claimed_by`)) > 0)) and ((`claim_token` is null) or (char_length(trim(`claim_token`)) > 0)) and (`attempt_count` >= 0))),
  CONSTRAINT `chk_controlled_file_finalize_observation` CHECK ((((`observed_sha256` is null) and (`observed_size_bytes` is null)) or (regexp_like(`observed_sha256`,_utf8mb4'^[0-9a-f]{64}$') and (`observed_size_bytes` > 0)))),
  CONSTRAINT `chk_controlled_file_finalize_state` CHECK ((((`finalize_state` = _utf8mb4'pending') and (`claimed_by` is null) and (`claimed_at_utc` is null) and (`available_at_utc` is null) and (`failed_at_utc` is null)) or ((`finalize_state` = _utf8mb4'processing') and (`claimed_by` is not null) and (`claimed_at_utc` is not null) and (`available_at_utc` is null) and (`failed_at_utc` is null)) or ((`finalize_state` = _utf8mb4'available') and (`available_at_utc` is not null) and (`failed_at_utc` is null) and (`observed_sha256` is not null) and (`observed_size_bytes` > 0)) or ((`finalize_state` = _utf8mb4'reconciliation_required') and (`failed_at_utc` is not null) and (`last_error_code` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_leases` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `lease_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_object_id` bigint unsigned NOT NULL,
  `holder` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `lease_state` enum('active','released','expired') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `acquired_at_utc` datetime(6) NOT NULL,
  `expires_at_utc` datetime(6) NOT NULL,
  `released_at_utc` datetime(6) DEFAULT NULL,
  `active_staging_object_id` bigint unsigned GENERATED ALWAYS AS ((case when (`lease_state` = _utf8mb4'active') then `staging_object_id` else NULL end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_lease_id` (`lease_id`),
  UNIQUE KEY `uq_controlled_file_active_staging` (`active_staging_object_id`),
  KEY `idx_controlled_file_lease_expiry` (`lease_state`,`expires_at_utc`,`id`),
  KEY `fk_controlled_file_lease_staging` (`staging_object_id`),
  CONSTRAINT `fk_controlled_file_lease_staging` FOREIGN KEY (`staging_object_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_lease_identity` CHECK ((regexp_like(`lease_id`,_utf8mb4'^cfl_[0-9a-f]{32}$') and (char_length(trim(`holder`)) > 0) and (`expires_at_utc` > `acquired_at_utc`))),
  CONSTRAINT `chk_controlled_file_lease_state` CHECK ((((`lease_state` = _utf8mb4'active') and (`released_at_utc` is null)) or ((`lease_state` in (_utf8mb4'released',_utf8mb4'expired')) and (`released_at_utc` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_objects` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `opaque_object_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_staging_id` bigint unsigned NOT NULL,
  `owner_type` enum('contract_signing','scheduling','orders','staff','line_integration') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `purpose` enum('unsigned_contract','final_signed_contract','service_date_confirmation','baby_log_photo','meal_photo','order_notice','staff_resume','staff_certificate','staff_health_exam','rich_menu_background') COLLATE utf8mb4_unicode_ci NOT NULL,
  `logical_folder` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `storage_locator` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` bigint unsigned NOT NULL,
  `content_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version_number` bigint unsigned NOT NULL,
  `supersedes_object_id` bigint unsigned DEFAULT NULL,
  `supersedes_version_number` bigint unsigned DEFAULT NULL,
  `created_by_actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_object_id` (`opaque_object_id`),
  UNIQUE KEY `uq_controlled_file_object_staging` (`source_staging_id`),
  UNIQUE KEY `uq_controlled_file_object_locator` (`storage_locator`),
  UNIQUE KEY `uq_controlled_file_owner_version` (`owner_type`,`subject_reference`,`object_key`,`version_number`),
  UNIQUE KEY `uq_controlled_file_version_identity` (`id`,`owner_type`,`subject_reference`,`object_key`,`purpose`,`version_number`),
  KEY `idx_controlled_file_object_owner` (`owner_type`,`subject_reference`,`purpose`,`id`),
  KEY `idx_controlled_file_object_supersedes` (`supersedes_object_id`,`id`),
  KEY `fk_controlled_file_object_supersedes` (`supersedes_object_id`,`owner_type`,`subject_reference`,`object_key`,`purpose`,`supersedes_version_number`),
  CONSTRAINT `fk_controlled_file_object_staging` FOREIGN KEY (`source_staging_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_controlled_file_object_supersedes` FOREIGN KEY (`supersedes_object_id`, `owner_type`, `subject_reference`, `object_key`, `purpose`, `supersedes_version_number`) REFERENCES `controlled_file_objects` (`id`, `owner_type`, `subject_reference`, `object_key`, `purpose`, `version_number`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_object_chain` CHECK ((((`supersedes_object_id` is null) and (`supersedes_version_number` is null) and (`version_number` = 1)) or ((`supersedes_object_id` is not null) and (`supersedes_version_number` is not null) and (`version_number` = (`supersedes_version_number` + 1))))),
  CONSTRAINT `chk_controlled_file_object_digest` CHECK (regexp_like(`content_sha256`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_controlled_file_object_identity` CHECK ((regexp_like(`opaque_object_id`,_utf8mb4'^cf_[0-9a-f]{32}$') and (char_length(trim(`subject_reference`)) > 0) and (char_length(trim(`object_key`)) > 0) and (char_length(trim(`purpose`)) > 0) and (char_length(trim(`filename`)) > 0) and (char_length(trim(`storage_locator`)) > 0) and (char_length(trim(`content_type`)) > 0) and (char_length(trim(`created_by_actor`)) > 0) and (`size_bytes` > 0) and (`version_number` > 0))),
  CONSTRAINT `chk_controlled_file_object_owner_purpose` CHECK ((((`owner_type` = _utf8mb4'contract_signing') and (`purpose` in (_utf8mb4'unsigned_contract',_utf8mb4'final_signed_contract'))) or ((`owner_type` = _utf8mb4'scheduling') and (`purpose` in (_utf8mb4'service_date_confirmation',_utf8mb4'baby_log_photo',_utf8mb4'meal_photo'))) or ((`owner_type` = _utf8mb4'orders') and (`purpose` = _utf8mb4'order_notice')) or ((`owner_type` = _utf8mb4'staff') and (`purpose` in (_utf8mb4'staff_resume',_utf8mb4'staff_certificate',_utf8mb4'staff_health_exam'))) or ((`owner_type` = _utf8mb4'line_integration') and (`purpose` = _utf8mb4'rich_menu_background'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_reconciliation_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_object_id` bigint unsigned DEFAULT NULL,
  `controlled_object_id` bigint unsigned DEFAULT NULL,
  `outcome` enum('exact','missing_object','digest_mismatch','orphan_object','still_writing') COLLATE utf8mb4_unicode_ci NOT NULL,
  `observation_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `observed_sha256` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `observed_size_bytes` bigint unsigned DEFAULT NULL,
  `observation_snapshot` json NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `observed_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_reconciliation_event` (`event_id`),
  UNIQUE KEY `uq_controlled_file_reconciliation_fingerprint` (`observation_fingerprint`),
  KEY `idx_controlled_file_reconciliation_staging` (`staging_object_id`,`id`),
  KEY `idx_controlled_file_reconciliation_object` (`controlled_object_id`,`id`),
  KEY `idx_controlled_file_reconciliation_outcome` (`outcome`,`observed_at_utc`,`id`),
  CONSTRAINT `fk_controlled_file_reconciliation_object` FOREIGN KEY (`controlled_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_controlled_file_reconciliation_staging` FOREIGN KEY (`staging_object_id`) REFERENCES `controlled_file_staging_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_reconciliation_identity` CHECK ((regexp_like(`event_id`,_utf8mb4'^cfe_[0-9a-f]{32}$') and regexp_like(`observation_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`actor_ref`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (((`outcome` in (_utf8mb4'exact',_utf8mb4'missing_object',_utf8mb4'digest_mismatch')) and (`controlled_object_id` is not null)) or ((`outcome` in (_utf8mb4'orphan_object',_utf8mb4'still_writing')) and (`staging_object_id` is not null) and (`controlled_object_id` is null))))),
  CONSTRAINT `chk_controlled_file_reconciliation_observation` CHECK ((((`outcome` in (_utf8mb4'exact',_utf8mb4'digest_mismatch')) and regexp_like(`observed_sha256`,_utf8mb4'^[0-9a-f]{64}$') and (`observed_size_bytes` is not null)) or ((`outcome` = _utf8mb4'missing_object') and (`observed_sha256` is null) and (`observed_size_bytes` is null)) or ((`outcome` in (_utf8mb4'orphan_object',_utf8mb4'still_writing')) and ((`observed_sha256` is null) or regexp_like(`observed_sha256`,_utf8mb4'^[0-9a-f]{64}$'))))),
  CONSTRAINT `chk_controlled_file_reconciliation_snapshot` CHECK (((json_type(`observation_snapshot`) = _utf8mb4'OBJECT') and (json_length(`observation_snapshot`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_references` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reference_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `controlled_file_object_id` bigint unsigned NOT NULL,
  `service_day_log_attachment_id` bigint unsigned NOT NULL,
  `reference_kind` enum('scheduling_service_day_log_attachment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_reference_id` (`reference_id`),
  UNIQUE KEY `uq_controlled_file_reference_object` (`controlled_file_object_id`),
  UNIQUE KEY `uq_controlled_file_reference_attachment` (`service_day_log_attachment_id`),
  CONSTRAINT `fk_controlled_file_reference_attachment` FOREIGN KEY (`service_day_log_attachment_id`) REFERENCES `scheduling_service_day_log_attachments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_controlled_file_reference_object` FOREIGN KEY (`controlled_file_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_controlled_file_reference_identity` CHECK (regexp_like(`reference_id`,_utf8mb4'^cfrf_[0-9a-f]{32}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `controlled_file_staging_objects` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `staging_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `storage_locator` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_type` enum('contract_signing','scheduling','orders','staff','line_integration') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `object_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `purpose` enum('unsigned_contract','final_signed_contract','service_date_confirmation','baby_log_photo','meal_photo','order_notice','staff_resume','staff_certificate','staff_health_exam','rich_menu_background') COLLATE utf8mb4_unicode_ci NOT NULL,
  `logical_folder` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` bigint unsigned NOT NULL,
  `content_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staging_state` enum('staged','applied','quarantined','cleaned') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'staged',
  `staging_version` bigint unsigned NOT NULL DEFAULT '1',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by_actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `expires_at_utc` datetime(6) NOT NULL,
  `applied_at_utc` datetime(6) DEFAULT NULL,
  `cleaned_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_controlled_file_staging_id` (`staging_id`),
  UNIQUE KEY `uq_controlled_file_staging_locator` (`storage_locator`),
  UNIQUE KEY `uq_controlled_file_staging_idempotency` (`idempotency_key`),
  KEY `idx_controlled_file_staging_owner` (`owner_type`,`subject_reference`,`purpose`,`staging_state`,`id`),
  KEY `idx_controlled_file_staging_cleanup` (`staging_state`,`expires_at_utc`,`id`),
  CONSTRAINT `chk_controlled_file_staging_digest` CHECK ((regexp_like(`content_sha256`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_controlled_file_staging_identity` CHECK ((regexp_like(`staging_id`,_utf8mb4'^cfs_[0-9a-f]{32}$') and (char_length(trim(`storage_locator`)) > 0) and (char_length(trim(`subject_reference`)) > 0) and (char_length(trim(`object_key`)) > 0) and (char_length(trim(`purpose`)) > 0) and (char_length(trim(`original_filename`)) > 0) and (char_length(trim(`content_type`)) > 0) and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`created_by_actor`)) > 0) and (`size_bytes` > 0) and (`expires_at_utc` > `created_at_utc`))),
  CONSTRAINT `chk_controlled_file_staging_owner_purpose` CHECK ((((`owner_type` = _utf8mb4'contract_signing') and (`purpose` in (_utf8mb4'unsigned_contract',_utf8mb4'final_signed_contract'))) or ((`owner_type` = _utf8mb4'scheduling') and (`purpose` in (_utf8mb4'service_date_confirmation',_utf8mb4'baby_log_photo',_utf8mb4'meal_photo'))) or ((`owner_type` = _utf8mb4'orders') and (`purpose` = _utf8mb4'order_notice')) or ((`owner_type` = _utf8mb4'staff') and (`purpose` in (_utf8mb4'staff_resume',_utf8mb4'staff_certificate',_utf8mb4'staff_health_exam'))) or ((`owner_type` = _utf8mb4'line_integration') and (`purpose` = _utf8mb4'rich_menu_background')))),
  CONSTRAINT `chk_controlled_file_staging_state` CHECK ((((`staging_state` = _utf8mb4'applied') and (`applied_at_utc` is not null) and (`cleaned_at_utc` is null)) or ((`staging_state` = _utf8mb4'cleaned') and (`applied_at_utc` is null) and (`cleaned_at_utc` is not null)) or ((`staging_state` in (_utf8mb4'staged',_utf8mb4'quarantined')) and (`applied_at_utc` is null) and (`cleaned_at_utc` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `current_anomaly_issues` (
  `issue_key` char(67) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `definition_code` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_domain` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `owner_root_type` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `subject_type` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `subject_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_identity` json NOT NULL,
  `owner_snapshot_token` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_version` bigint unsigned NOT NULL,
  `severity` enum('warning','blocking') COLLATE utf8mb4_unicode_ci NOT NULL,
  `blocking` tinyint(1) NOT NULL,
  `details_version` smallint unsigned NOT NULL DEFAULT '1',
  `details` json NOT NULL,
  `episode_started_at` datetime(6) NOT NULL,
  `last_verified_at` datetime(6) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`issue_key`),
  KEY `idx_current_anomaly_owner` (`owner_domain`,`owner_root_type`,`subject_type`,`subject_id`,`issue_key`),
  KEY `idx_current_anomaly_definition` (`definition_code`,`blocking`,`severity`,`episode_started_at`,`issue_key`),
  CONSTRAINT `chk_current_anomaly_boolean` CHECK ((`blocking` in (0,1))),
  CONSTRAINT `chk_current_anomaly_details` CHECK (((`details_version` = 1) and (json_type(`details`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_current_anomaly_issue_key` CHECK (regexp_like(`issue_key`,_utf8mb4'^ci_[0-9a-f]{64}$')),
  CONSTRAINT `chk_current_anomaly_subject_identity` CHECK ((json_type(`subject_identity`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_current_anomaly_text` CHECK (((char_length(trim(`definition_code`)) > 0) and (char_length(trim(`owner_domain`)) > 0) and (char_length(trim(`owner_root_type`)) > 0) and (char_length(trim(`subject_type`)) > 0) and (char_length(trim(`subject_id`)) > 0) and (char_length(trim(`owner_snapshot_token`)) > 0))),
  CONSTRAINT `chk_current_anomaly_time_order` CHECK ((`last_verified_at` >= `episode_started_at`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `customer_service_escalation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `escalation_id` bigint NOT NULL,
  `event_type` enum('created','claimed','handling_started','resolved','hold_released') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_escalation_version` bigint NOT NULL,
  `resulting_escalation_version` bigint NOT NULL,
  `expected_ticket_version` bigint DEFAULT NULL,
  `resulting_ticket_version` bigint DEFAULT NULL,
  `expected_hold_version` bigint NOT NULL,
  `resulting_hold_version` bigint NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_evidence_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `receipt_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_service_escalation_event_receipt` (`receipt_id`),
  UNIQUE KEY `uq_customer_service_escalation_event_idempotency` (`idempotency_key`),
  KEY `idx_customer_service_escalation_event_stream` (`escalation_id`,`id`),
  KEY `idx_customer_service_escalation_event_type_time` (`event_type`,`created_at_utc`),
  CONSTRAINT `fk_customer_service_escalation_event_escalation` FOREIGN KEY (`escalation_id`) REFERENCES `customer_service_escalations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_customer_service_escalation_event_actor` CHECK ((char_length(trim(`actor_ref`)) > 0)),
  CONSTRAINT `chk_customer_service_escalation_event_identities` CHECK (((char_length(trim(`receipt_id`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_customer_service_escalation_event_reason` CHECK (((char_length(trim(`reason_code`)) > 0) and regexp_like(`reason_evidence_digest`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_customer_service_escalation_event_versions` CHECK (((`resulting_escalation_version` >= `expected_escalation_version`) and (`resulting_hold_version` >= `expected_hold_version`) and ((`expected_ticket_version` is null) or (`resulting_ticket_version` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `customer_service_escalations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `trigger_code` enum('explicit_human_request','explicit_wrong_answer','binding_failure_threshold_2','complaint','runtime_critical') COLLATE utf8mb4_unicode_ci NOT NULL,
  `trigger_policy_version` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ticket_id` bigint NOT NULL,
  `ticket_category` enum('service_flow','payment_subsidy','service_progress','profile_update','contact_union','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `urgency` enum('high') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'high',
  `workflow_status` enum('open','claimed','handling','resolved') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `workflow_version` bigint NOT NULL DEFAULT '0',
  `hold_scope_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `automation_hold_state` enum('active','released') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `hold_version` bigint NOT NULL DEFAULT '0',
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `claim_at_utc` datetime(6) DEFAULT NULL,
  `handling_started_at_utc` datetime(6) DEFAULT NULL,
  `resolved_at_utc` datetime(6) DEFAULT NULL,
  `resolution_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolution_evidence_digest` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `context` json NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_intent_ref` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delivery_task_ref` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `delivery_outcome_ref` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `alert_status` enum('pending','queued','sent','failed','unknown') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `active_hold_scope_key` varchar(191) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS ((case when (`automation_hold_state` = _utf8mb4'active') then `hold_scope_ref` else NULL end)) STORED,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_service_escalation_source` (`source_event_identity`),
  UNIQUE KEY `uq_customer_service_escalation_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_customer_service_escalation_active_scope` (`active_hold_scope_key`),
  KEY `idx_customer_service_escalation_ticket` (`ticket_id`,`id`),
  KEY `idx_customer_service_escalation_status_time` (`workflow_status`,`updated_at_utc`),
  KEY `idx_customer_service_escalation_trigger_time` (`trigger_code`,`created_at_utc`),
  CONSTRAINT `fk_customer_service_escalation_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `customer_service_tickets` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_customer_service_escalation_actor` CHECK ((char_length(trim(`actor_ref`)) > 0)),
  CONSTRAINT `chk_customer_service_escalation_hold_state` CHECK ((((`workflow_status` = _utf8mb4'resolved') and (`automation_hold_state` = _utf8mb4'released')) or ((`workflow_status` <> _utf8mb4'resolved') and (`automation_hold_state` = _utf8mb4'active')))),
  CONSTRAINT `chk_customer_service_escalation_identities` CHECK (((char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_customer_service_escalation_policy_version` CHECK ((char_length(trim(`trigger_policy_version`)) > 0)),
  CONSTRAINT `chk_customer_service_escalation_resolution` CHECK (((`workflow_status` <> _utf8mb4'resolved') or ((`resolution_code` is not null) and (`resolution_evidence_digest` is not null) and (char_length(trim(`resolution_code`)) > 0) and regexp_like(`resolution_evidence_digest`,_utf8mb4'^[0-9a-f]{64}$')))),
  CONSTRAINT `chk_customer_service_escalation_scope` CHECK ((char_length(trim(`hold_scope_ref`)) > 0)),
  CONSTRAINT `chk_customer_service_escalation_source_fingerprint` CHECK (regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_customer_service_escalation_source_kind` CHECK ((char_length(trim(`source_kind`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `customer_service_ticket_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ticket_id` bigint NOT NULL,
  `event_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('customer_message','agent_reply','status_changed','internal_note') COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_text` text COLLATE utf8mb4_unicode_ci,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_service_event_key` (`event_key`),
  KEY `idx_customer_service_ticket_events` (`ticket_id`,`id`),
  CONSTRAINT `fk_customer_service_event_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `customer_service_tickets` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `customer_service_tickets` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int DEFAULT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `category` enum('service_flow','payment_subsidy','service_progress','profile_update','contact_union','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('waiting','handling','resolved') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'waiting',
  `assigned_to_admin_user_id` bigint DEFAULT NULL,
  `internal_note` text COLLATE utf8mb4_unicode_ci,
  `version` bigint NOT NULL DEFAULT '0',
  `resolved_at_utc` datetime DEFAULT NULL,
  `created_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at_utc` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `active_marker` tinyint GENERATED ALWAYS AS ((case when (`status` in (_utf8mb4'waiting',_utf8mb4'handling')) then 1 else NULL end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_service_active_category` (`line_user_id`,`category`,`active_marker`),
  KEY `idx_customer_service_status_time` (`status`,`created_at_utc`),
  KEY `idx_customer_service_client` (`client_id`,`created_at_utc`),
  KEY `idx_customer_service_case` (`case_no`,`created_at_utc`),
  KEY `fk_customer_service_admin` (`assigned_to_admin_user_id`),
  CONSTRAINT `fk_customer_service_admin` FOREIGN KEY (`assigned_to_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `fk_customer_service_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `fk_customer_service_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_accounting_dismissals` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `warning_kind` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `difference_ntd` bigint NOT NULL,
  `source_version` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`,`item_identity`,`warning_kind`,`difference_ntd`),
  CONSTRAINT `fk_accounting_dismissal_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_anomaly_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `occurrence_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_code` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `finance_import_batch_id` bigint DEFAULT NULL,
  `source_version` bigint unsigned NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_anomaly_occurrence_fingerprint` (`occurrence_fingerprint`),
  UNIQUE KEY `uq_finance_anomaly_occurrence_source` (`definition_code`,`source_event_identity`),
  KEY `fk_finance_anomaly_occurrence_row` (`finance_import_row_id`),
  KEY `fk_finance_anomaly_occurrence_batch` (`finance_import_batch_id`),
  CONSTRAINT `fk_finance_anomaly_occurrence_batch` FOREIGN KEY (`finance_import_batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_anomaly_occurrence_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_anomaly_occurrence_fingerprint` CHECK (regexp_like(`occurrence_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_anomaly_occurrence_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_finance_anomaly_occurrence_source` CHECK (((`finance_import_row_id` is not null) <> (`finance_import_batch_id` is not null)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_apply_receipt_key` (`idempotency_key`),
  KEY `fk_finance_import_apply_receipt_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_apply_receipt_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_apply_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_finance_import_apply_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_batch_contracts` (
  `batch_id` bigint NOT NULL,
  `batch_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `classifier_version` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `fingerprint_version` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_version` bigint unsigned NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  UNIQUE KEY `uq_finance_import_batch_contract_identity` (`batch_identity`),
  CONSTRAINT `fk_finance_import_batch_contract_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_batch_contract_digest` CHECK (regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_batch_contract_text` CHECK (((char_length(trim(`batch_identity`)) > 0) and (char_length(trim(`classifier_version`)) > 0) and (char_length(trim(`fingerprint_version`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_batches` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `format_id` enum('legacy','taishin','sinopac') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '空批次或過渡期多來源輸入允許 NULL',
  `sheet_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `header_row` int unsigned NOT NULL,
  `row_count` int unsigned NOT NULL DEFAULT '0',
  `status` enum('staged','completed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'staged',
  `failure_message` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_batch_id_status` (`id`,`status`),
  KEY `idx_finance_import_batch_status` (`status`,`created_at`),
  CONSTRAINT `chk_finance_import_batch_header_row` CHECK ((`header_row` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_classification_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `classification_version` bigint unsigned NOT NULL,
  `canonical_fact_version` bigint unsigned NOT NULL,
  `classification_type` enum('client_receipt','client_refund','client_refund_return','client_subsidy_return','government_subsidy','staff_payout','non_business_review') COLLATE utf8mb4_unicode_ci NOT NULL,
  `disposition` enum('create','existing','manual_review','business_pending','blocked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_facts_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_identities` json NOT NULL,
  `evidence` json NOT NULL,
  `available_actions` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_classification_version` (`finance_import_row_id`,`classification_version`),
  KEY `idx_finance_import_classification_batch` (`batch_id`,`finance_import_row_id`,`id`),
  CONSTRAINT `fk_finance_import_classification_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_classification_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_classification_fingerprint` CHECK (regexp_like(`decision_facts_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_classification_json` CHECK (((json_type(`target_identities`) = _utf8mb4'ARRAY') and (json_type(`evidence`) = _utf8mb4'ARRAY') and (json_type(`available_actions`) = _utf8mb4'ARRAY'))),
  CONSTRAINT `chk_finance_import_classification_text` CHECK (((char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_correction_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_correction_receipt_key` (`idempotency_key`),
  KEY `fk_finance_import_correction_receipt_row` (`finance_import_row_id`),
  CONSTRAINT `fk_finance_import_correction_receipt_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_correction_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_finance_import_correction_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_dispatch_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `plan_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outcome` enum('reconciled','existing','pending','rejected','conflict') COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_dispatch_plan_row` (`plan_fingerprint`,`finance_import_row_id`),
  KEY `idx_finance_import_dispatch_batch` (`batch_id`,`id`),
  KEY `fk_finance_import_dispatch_row` (`finance_import_row_id`),
  CONSTRAINT `fk_finance_import_dispatch_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_dispatch_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_dispatch_fingerprint` CHECK (regexp_like(`plan_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_dispatch_reference` CHECK ((((`outcome` in (_utf8mb4'reconciled',_utf8mb4'existing')) and (`result_reference` is not null) and (char_length(trim(`result_reference`)) > 0)) or ((`outcome` in (_utf8mb4'pending',_utf8mb4'rejected',_utf8mb4'conflict')) and (`result_reference` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_historical_reprocess_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint NOT NULL,
  `reprocess_run_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_historical_reprocess_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_finance_import_historical_reprocess_receipt_run` (`reprocess_run_id`),
  KEY `fk_finance_import_historical_reprocess_receipt_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_historical_reprocess_receipt_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_historical_reprocess_receipt_run` FOREIGN KEY (`reprocess_run_id`) REFERENCES `finance_import_reprocess_runs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_historical_reprocess_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_finance_import_historical_reprocess_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_ingestion_attempts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `phase` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `error_code` varchar(96) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `transaction_outcome` enum('committed','rolled_back') COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint DEFAULT NULL,
  `started_at` datetime(6) NOT NULL,
  `completed_at` datetime(6) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_attempt_command` (`idempotency_key`),
  KEY `ix_finance_import_attempt_digest` (`source_content_digest`),
  KEY `fk_finance_import_attempt_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_attempt_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_attempt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_finance_import_attempt_outcome` CHECK ((((`transaction_outcome` = _utf8mb4'committed') and (`error_code` is null) and (`batch_id` is not null)) or ((`transaction_outcome` = _utf8mb4'rolled_back') and (`error_code` is not null) and (`batch_id` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_ingestion_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_ingestion_receipt_key` (`idempotency_key`),
  KEY `fk_finance_import_ingestion_receipt_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_ingestion_receipt_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_ingestion_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_finance_import_ingestion_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_integrity_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `issue_code` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_integrity_source` (`source_event_identity`),
  KEY `idx_finance_import_integrity_current` (`batch_id`,`finance_import_row_id`,`issue_code`,`id`),
  KEY `fk_finance_import_integrity_row` (`finance_import_row_id`),
  CONSTRAINT `fk_finance_import_integrity_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_integrity_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_integrity_active` CHECK ((`active` in (0,1))),
  CONSTRAINT `chk_finance_import_integrity_snapshot` CHECK ((json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_finance_import_integrity_text` CHECK (((char_length(trim(`issue_code`)) > 0) and (char_length(trim(`source_event_identity`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `source_file` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sheet_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_row` int unsigned NOT NULL,
  `warnings` json NOT NULL DEFAULT (json_array()),
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_occurrence_position` (`batch_id`,`sheet_name`,`source_row`),
  KEY `idx_finance_import_occurrence_row` (`finance_import_row_id`,`batch_id`),
  CONSTRAINT `fk_finance_import_occurrence_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_occurrence_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_occurrence_source_row` CHECK ((`source_row` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('dispatch_completed','manual_correction_completed','initial_classification_recorded','historical_reprocess_completed','refund_return_review_recorded') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_outbox_intent` (`intent_key`),
  KEY `idx_finance_import_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_finance_import_outbox_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_outbox_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_reconciliation_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `finance_import_row_id` bigint NOT NULL,
  `candidate_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owning_domain` enum('client_finance','staff_payables') COLLATE utf8mb4_unicode_ci NOT NULL,
  `allocation_count` int unsigned NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_reconciliation_candidate` (`candidate_fingerprint`),
  KEY `fk_finance_import_reconciliation_row` (`finance_import_row_id`),
  CONSTRAINT `fk_finance_import_reconciliation_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_reconciliation_fingerprint` CHECK (regexp_like(`candidate_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_reconciliation_values` CHECK (((`allocation_count` > 0) and (`amount_ntd` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_reprocess_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `batch_status` enum('staged','completed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'completed',
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `classifier_version` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `selected_count` int unsigned NOT NULL,
  `changed_count` int unsigned NOT NULL,
  `dispatch_count` int unsigned NOT NULL,
  `reconciled_count` int unsigned NOT NULL,
  `pending_count` int unsigned NOT NULL,
  `request_summary` json NOT NULL,
  `result_summary` json NOT NULL,
  `status` enum('completed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'completed',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_reprocess_run_plan` (`batch_id`,`plan_fingerprint`),
  KEY `idx_finance_import_reprocess_run_created` (`created_at`,`batch_id`),
  KEY `fk_finance_import_reprocess_run_batch` (`batch_id`,`batch_status`),
  CONSTRAINT `fk_finance_import_reprocess_run_batch` FOREIGN KEY (`batch_id`, `batch_status`) REFERENCES `finance_import_batches` (`id`, `status`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_reprocess_run_actor` CHECK ((char_length(trim(`actor`)) > 0)),
  CONSTRAINT `chk_finance_import_reprocess_run_batch_completed` CHECK ((`batch_status` = _utf8mb4'completed')),
  CONSTRAINT `chk_finance_import_reprocess_run_classifier` CHECK ((char_length(trim(`classifier_version`)) > 0)),
  CONSTRAINT `chk_finance_import_reprocess_run_counts` CHECK (((`changed_count` <= `selected_count`) and (`dispatch_count` <= `changed_count`) and (`reconciled_count` <= `dispatch_count`) and (`pending_count` <= `dispatch_count`) and ((`reconciled_count` + `pending_count`) <= `dispatch_count`))),
  CONSTRAINT `chk_finance_import_reprocess_run_fingerprint` CHECK (regexp_like(`plan_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_rows` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dedup_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint DEFAULT NULL COMMENT '首度建立 canonical row 的相容批次；後續出現以 occurrence 為準',
  `format_id` enum('legacy','taishin','sinopac') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '首度出現來源，相容既有 writer',
  `source_bank_account` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sheet_name` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '首度出現工作表，相容既有 writer',
  `source_row` int unsigned DEFAULT NULL COMMENT '首度出現的一基底列號，相容既有 writer',
  `source_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行原始參考值；不承擔唯一性',
  `transaction_date` date DEFAULT NULL,
  `transaction_time` time DEFAULT NULL,
  `posting_date` date DEFAULT NULL,
  `value_date` date DEFAULT NULL,
  `debit` decimal(18,2) DEFAULT NULL,
  `credit` decimal(18,2) DEFAULT NULL,
  `direction` enum('incoming','outgoing','unknown') COLLATE utf8mb4_unicode_ci NOT NULL,
  `balance` decimal(18,2) DEFAULT NULL,
  `currency` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci,
  `memo` text COLLATE utf8mb4_unicode_ci,
  `counterparty_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `counterparty_account` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_counterparty_account` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cancellation_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bank_references` json NOT NULL,
  `warnings` json NOT NULL,
  `raw_payload` json NOT NULL,
  `matched_identity_ids` json NOT NULL DEFAULT (json_array()),
  `classification_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `classification_reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `classified_at` timestamp NULL DEFAULT NULL,
  `reconciliation_status` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reconciliation_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reconciled_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_row_fingerprint` (`dedup_fingerprint`),
  KEY `idx_finance_import_row_classification` (`classification_type`,`reconciliation_status`),
  KEY `idx_finance_import_row_account_date` (`source_bank_account`,`transaction_date`),
  KEY `fk_finance_import_row_compat_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_row_compat_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_row_amounts` CHECK ((((`debit` is null) or (`debit` >= 0)) and ((`credit` is null) or (`credit` >= 0)))),
  CONSTRAINT `chk_finance_import_row_fingerprint` CHECK (regexp_like(`dedup_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_row_source_row` CHECK (((`source_row` is null) or (`source_row` >= 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_source_review_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `review_id` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_source_review_occurrence` (`batch_id`,`review_id`),
  KEY `idx_finance_source_review_occurrence_review` (`review_id`,`id`),
  CONSTRAINT `fk_finance_source_review_occurrence_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_source_review_occurrence_review` FOREIGN KEY (`review_id`) REFERENCES `finance_import_source_reviews` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_source_review_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `published_at` timestamp NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_source_review_outbox_review` (`review_id`),
  UNIQUE KEY `uq_finance_source_review_outbox_intent` (`intent_key`),
  KEY `idx_finance_source_review_outbox_pending` (`published_at`,`attempts`,`id`),
  CONSTRAINT `fk_finance_source_review_outbox_review` FOREIGN KEY (`review_id`) REFERENCES `finance_import_source_reviews` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_source_review_outbox_attempts` CHECK ((`attempts` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_import_source_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `format_id` enum('legacy','taishin','sinopac') COLLATE utf8mb4_unicode_ci NOT NULL,
  `sheet_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_row` int unsigned NOT NULL,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `issue_codes` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_source_review_identity` (`review_identity`),
  UNIQUE KEY `uq_finance_source_review_source` (`source_content_digest`,`format_id`,`sheet_name`,`source_row`),
  KEY `idx_finance_source_review_location` (`format_id`,`sheet_name`,`source_row`),
  CONSTRAINT `chk_finance_source_review_digest` CHECK (regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_source_review_issues` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_length(`issue_codes`) > 0))),
  CONSTRAINT `chk_finance_source_review_row` CHECK ((`source_row` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_manual_statements` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `fields` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_manual_statement_object` CHECK ((json_type(`fields`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_statement_archive_state` (
  `id` tinyint NOT NULL,
  `version` bigint unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_statement_singleton` CHECK ((`id` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_statement_commands` (
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `command_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `saved_count` int unsigned NOT NULL,
  `excluded_count` int unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `finance_statement_exclusions` (
  `finance_import_row_id` bigint NOT NULL,
  `kept_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`finance_import_row_id`),
  CONSTRAINT `fk_statement_excluded_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `financial_adjustment_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_client_account_version` bigint unsigned NOT NULL,
  `resulting_payroll_version` bigint unsigned DEFAULT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_financial_adjustment_receipt_key` (`idempotency_key`),
  KEY `fk_financial_adjustment_receipt_order` (`case_no`),
  CONSTRAINT `fk_financial_adjustment_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_financial_adjustment_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_financial_adjustment_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `financial_adjustment_staff_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `financial_adjustment_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `amount_delta_ntd` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_financial_adjustment_staff_assignment` (`financial_adjustment_id`,`assignment_id`),
  KEY `idx_financial_adjustment_staff_assignment` (`assignment_id`,`financial_adjustment_id`),
  CONSTRAINT `fk_financial_adjustment_staff_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_financial_adjustment_staff_parent` FOREIGN KEY (`financial_adjustment_id`) REFERENCES `financial_adjustments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_financial_adjustment_staff_amount` CHECK ((`amount_delta_ntd` <> 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `financial_adjustments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `adjustment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_source_type` enum('preview_recalculation','manual_extra') COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_scope` enum('client_only','client_and_staff') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'client_and_staff',
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_delta_ntd` bigint NOT NULL,
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reversal_of_adjustment_id` bigint DEFAULT NULL,
  `cancelled_at` timestamp NULL DEFAULT NULL,
  `apply_idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_financial_adjustment_identity` (`adjustment_identity`),
  UNIQUE KEY `uq_financial_adjustment_apply_key` (`apply_idempotency_key`),
  UNIQUE KEY `uq_financial_adjustment_source` (`case_no`,`source_event_identity`),
  KEY `idx_financial_adjustment_case_created` (`case_no`,`created_at`,`id`),
  KEY `fk_financial_adjustment_reversal` (`reversal_of_adjustment_id`),
  CONSTRAINT `fk_financial_adjustment_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_financial_adjustment_reversal` FOREIGN KEY (`reversal_of_adjustment_id`) REFERENCES `financial_adjustments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_financial_adjustment_amount` CHECK ((`amount_delta_ntd` <> 0)),
  CONSTRAINT `chk_financial_adjustment_reason` CHECK ((((`adjustment_source_type` = _utf8mb4'manual_extra') and (`reason` is not null) and (char_length(trim(`reason`)) > 0)) or ((`adjustment_source_type` = _utf8mb4'preview_recalculation') and (`reason` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_payers` (
  `payer_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payer_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `incoming_memo_match` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`payer_identity`),
  CONSTRAINT `chk_government_payer_identity` CHECK ((`payer_identity` = _utf8mb4'hccg')),
  CONSTRAINT `chk_government_payer_memo` CHECK ((`incoming_memo_match` = _utf8mb4'新竹市政府')),
  CONSTRAINT `chk_government_payer_name` CHECK ((`payer_name` = _utf8mb4'新竹市政府'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `transaction_id` bigint NOT NULL,
  `claim_batch_id` bigint NOT NULL,
  `claim_item_id` bigint NOT NULL,
  `allocation_type` enum('receipt','reversal') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
  `allocated_amount` decimal(18,2) NOT NULL,
  `reversal_of_allocation_id` bigint DEFAULT NULL,
  `reversal_target_type` enum('receipt','reversal') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_allocation_target` (`transaction_id`,`claim_item_id`),
  UNIQUE KEY `uq_government_subsidy_allocation_reversal_target` (`id`,`claim_batch_id`,`allocation_type`),
  KEY `idx_government_subsidy_allocation_batch_item` (`claim_batch_id`,`claim_item_id`),
  KEY `idx_government_subsidy_allocation_reversal` (`reversal_of_allocation_id`),
  KEY `fk_government_subsidy_allocation_transaction_batch` (`transaction_id`,`claim_batch_id`),
  KEY `fk_government_subsidy_allocation_item_batch` (`claim_item_id`,`claim_batch_id`),
  KEY `fk_government_subsidy_allocation_reversal_receipt` (`reversal_of_allocation_id`,`claim_batch_id`,`reversal_target_type`),
  CONSTRAINT `fk_government_subsidy_allocation_batch` FOREIGN KEY (`claim_batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_allocation_item_batch` FOREIGN KEY (`claim_item_id`, `claim_batch_id`) REFERENCES `subsidy_claim_batch_items` (`id`, `batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_allocation_reversal_receipt` FOREIGN KEY (`reversal_of_allocation_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_allocations` (`id`, `claim_batch_id`, `allocation_type`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_allocation_transaction_batch` FOREIGN KEY (`transaction_id`, `claim_batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_allocation_amount` CHECK ((`allocated_amount` > 0)),
  CONSTRAINT `chk_government_subsidy_allocation_original` CHECK ((((`allocation_type` = _utf8mb4'receipt') and (`reversal_of_allocation_id` is null)) or ((`allocation_type` = _utf8mb4'reversal') and (`reversal_of_allocation_id` is not null)))),
  CONSTRAINT `chk_government_subsidy_allocation_reversal_target` CHECK ((`reversal_target_type` = _utf8mb4'receipt'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` enum('receipt','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_id` bigint NOT NULL,
  `batch_id` bigint NOT NULL,
  `batch_version` bigint unsigned NOT NULL,
  `bank_fact_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint unsigned NOT NULL,
  `allocation_count` int unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_receipt_key` (`idempotency_key`),
  KEY `fk_government_subsidy_receipt_transaction` (`transaction_id`,`batch_id`),
  CONSTRAINT `fk_government_subsidy_receipt_transaction` FOREIGN KEY (`transaction_id`, `batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_receipt_amount` CHECK (((`amount_ntd` > 0) and (`allocation_count` > 0))),
  CONSTRAINT `chk_government_subsidy_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_government_subsidy_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_batch_accounts` (
  `batch_id` bigint NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL,
  `requested_total_ntd` bigint unsigned NOT NULL,
  `approved_total_ntd` bigint unsigned NOT NULL,
  `net_allocated_ntd` bigint unsigned NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  CONSTRAINT `fk_government_subsidy_account_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_account_totals` CHECK (((`approved_total_ntd` <= `requested_total_ntd`) and (`net_allocated_ntd` <= `approved_total_ntd`) and (`outstanding_ntd` = (`approved_total_ntd` - `net_allocated_ntd`)))),
  CONSTRAINT `chk_government_subsidy_account_version` CHECK ((`aggregate_version` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_claim_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` enum('plan','submit','approval') COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint NOT NULL,
  `batch_version` bigint unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_count` int unsigned NOT NULL,
  `total_ntd` bigint unsigned NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_claim_receipt_key` (`idempotency_key`),
  KEY `fk_government_subsidy_claim_receipt_batch` (`batch_id`),
  CONSTRAINT `fk_government_subsidy_claim_receipt_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_claim_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_government_subsidy_claim_receipt_items` CHECK ((`item_count` > 0)),
  CONSTRAINT `chk_government_subsidy_claim_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_claim_approval_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `approved_total_ntd` bigint unsigned NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `approved_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_approval_key` (`idempotency_key`),
  UNIQUE KEY `uq_government_subsidy_approval_batch` (`batch_id`),
  UNIQUE KEY `uq_government_subsidy_approval_identity` (`id`,`batch_id`),
  CONSTRAINT `fk_government_subsidy_approval_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_approval_actor` CHECK ((char_length(trim(`actor`)) > 0)),
  CONSTRAINT `chk_government_subsidy_approval_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_government_subsidy_approval_reason` CHECK ((char_length(trim(`reason`)) > 0)),
  CONSTRAINT `chk_government_subsidy_approval_version` CHECK ((`resulting_batch_version` = (`expected_batch_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_claim_approval_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `approval_event_id` bigint NOT NULL,
  `batch_id` bigint NOT NULL,
  `claim_item_id` bigint NOT NULL,
  `approved_amount_ntd` bigint unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_approval_item` (`approval_event_id`,`claim_item_id`),
  KEY `fk_government_subsidy_approval_item_event` (`approval_event_id`,`batch_id`),
  KEY `fk_government_subsidy_approval_item_claim` (`claim_item_id`,`batch_id`),
  CONSTRAINT `fk_government_subsidy_approval_item_claim` FOREIGN KEY (`claim_item_id`, `batch_id`) REFERENCES `subsidy_claim_batch_items` (`id`, `batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_approval_item_event` FOREIGN KEY (`approval_event_id`, `batch_id`) REFERENCES `government_subsidy_claim_approval_events` (`id`, `batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_claim_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('plan','submit','approval') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_claim_outbox_intent` (`intent_key`),
  KEY `idx_government_subsidy_claim_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_government_subsidy_claim_outbox_batch` (`batch_id`),
  CONSTRAINT `fk_government_subsidy_claim_outbox_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_claim_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_claim_submission_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `submitted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_submission_key` (`idempotency_key`),
  UNIQUE KEY `uq_government_subsidy_submission_batch` (`batch_id`),
  CONSTRAINT `fk_government_subsidy_submission_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_submission_actor` CHECK ((char_length(trim(`actor`)) > 0)),
  CONSTRAINT `chk_government_subsidy_submission_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_government_subsidy_submission_reason` CHECK ((char_length(trim(`reason`)) > 0)),
  CONSTRAINT `chk_government_subsidy_submission_version` CHECK ((`resulting_batch_version` = (`expected_batch_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `transaction_id` bigint NOT NULL,
  `projection_event_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('government_subsidy_receipt_applied','government_subsidy_receipt_allocated','government_subsidy_reversal_applied','government_subsidy_anomaly_root_changed','government_subsidy_overpayment_established','government_subsidy_overpayment_offset','government_overpayment_return_payable','government_overpayment_return_payout','government_overpayment_return_excess_recovery') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_outbox_intent` (`intent_key`),
  KEY `idx_government_subsidy_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_government_subsidy_outbox_transaction` (`transaction_id`,`batch_id`),
  KEY `fk_government_subsidy_outbox_projection` (`projection_event_id`,`batch_id`),
  CONSTRAINT `fk_government_subsidy_outbox_projection` FOREIGN KEY (`projection_event_id`, `batch_id`) REFERENCES `government_subsidy_projection_events` (`id`, `batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_outbox_transaction` FOREIGN KEY (`transaction_id`, `batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_overpayment_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` enum('offset','return','return_reconciliation','return_reconciliation_with_excess') COLLATE utf8mb4_unicode_ci NOT NULL,
  `overpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_overpayment_apply_receipt_key` (`idempotency_key`),
  KEY `fk_government_overpayment_apply_receipt_root` (`overpayment_identity`),
  CONSTRAINT `fk_government_overpayment_apply_receipt_root` FOREIGN KEY (`overpayment_identity`) REFERENCES `government_subsidy_overpayments` (`overpayment_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_overpayment_apply_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_overpayment_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('established','offset_applied','return_payable_created','return_paid','return_reconciled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_remaining_ntd` bigint NOT NULL,
  `after_remaining_ntd` bigint NOT NULL,
  `resulting_status` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_overpayment_event_idempotency` (`idempotency_key`),
  KEY `idx_government_subsidy_overpayment_event_root` (`overpayment_identity`,`id`),
  CONSTRAINT `fk_government_subsidy_overpayment_event_root` FOREIGN KEY (`overpayment_identity`) REFERENCES `government_subsidy_overpayments` (`overpayment_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_overpayment_event_amount` CHECK (((`before_remaining_ntd` > 0) and (`after_remaining_ntd` >= 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_overpayment_offsets` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overpayment_event_id` bigint NOT NULL,
  `overpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `claim_batch_id` bigint NOT NULL,
  `claim_item_id` bigint NOT NULL,
  `allocated_amount_ntd` bigint NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_overpayment_offset_target` (`overpayment_identity`,`claim_item_id`),
  KEY `idx_government_subsidy_overpayment_offset_item` (`claim_batch_id`,`claim_item_id`),
  KEY `fk_government_subsidy_overpayment_offset_event` (`overpayment_event_id`),
  KEY `fk_government_subsidy_overpayment_offset_item` (`claim_item_id`,`claim_batch_id`),
  CONSTRAINT `fk_government_subsidy_overpayment_offset_event` FOREIGN KEY (`overpayment_event_id`) REFERENCES `government_subsidy_overpayment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_overpayment_offset_item` FOREIGN KEY (`claim_item_id`, `claim_batch_id`) REFERENCES `subsidy_claim_batch_items` (`id`, `batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_overpayment_offset_root` FOREIGN KEY (`overpayment_identity`) REFERENCES `government_subsidy_overpayments` (`overpayment_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_overpayment_offset_amount` CHECK ((`allocated_amount_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_overpayment_target_projection_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overpayment_event_id` bigint NOT NULL,
  `batch_id` bigint NOT NULL,
  `before_net_allocated_ntd` bigint unsigned NOT NULL,
  `after_net_allocated_ntd` bigint unsigned NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_overpayment_target_projection` (`overpayment_event_id`,`batch_id`),
  KEY `fk_government_overpayment_target_projection_batch` (`batch_id`),
  CONSTRAINT `fk_government_overpayment_target_projection_batch` FOREIGN KEY (`batch_id`) REFERENCES `government_subsidy_batch_accounts` (`batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_overpayment_target_projection_event` FOREIGN KEY (`overpayment_event_id`) REFERENCES `government_subsidy_overpayment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_overpayment_target_projection_amount` CHECK ((`after_net_allocated_ntd` >= `before_net_allocated_ntd`)),
  CONSTRAINT `chk_government_overpayment_target_projection_version` CHECK ((`resulting_batch_version` = (`expected_batch_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_overpayments` (
  `overpayment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_finance_import_row_id` bigint NOT NULL,
  `source_transaction_id` bigint NOT NULL,
  `payer_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_amount_ntd` bigint NOT NULL,
  `remaining_amount_ntd` bigint NOT NULL,
  `status` enum('pending_review','offset_reserved','offset_applied','return_payable','partially_returned','returned') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending_review',
  `projection_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`overpayment_identity`),
  UNIQUE KEY `uq_government_subsidy_overpayment_bank_row` (`source_finance_import_row_id`),
  UNIQUE KEY `uq_government_subsidy_overpayment_transaction` (`source_transaction_id`),
  KEY `idx_government_subsidy_overpayment_status` (`status`,`created_at`),
  CONSTRAINT `fk_government_subsidy_overpayment_bank_row` FOREIGN KEY (`source_finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_overpayment_transaction` FOREIGN KEY (`source_transaction_id`) REFERENCES `government_subsidy_transactions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_overpayment_amount` CHECK (((`original_amount_ntd` > 0) and (`remaining_amount_ntd` >= 0) and (`remaining_amount_ntd` <= `original_amount_ntd`) and ((`remaining_amount_ntd` > 0) or (`status` in (_utf8mb4'offset_applied',_utf8mb4'returned')))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_period_entries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `period_unit` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `period_year` int NOT NULL,
  `period_index` int NOT NULL,
  `period_start` date NOT NULL,
  `period_end` date NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `reversal_of_id` bigint DEFAULT NULL,
  `paid_on` date NOT NULL,
  `idempotency_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_subsidy_period_bank` (`finance_import_row_id`),
  UNIQUE KEY `uq_subsidy_period_key` (`idempotency_key`),
  UNIQUE KEY `uq_subsidy_period_reversal` (`reversal_of_id`),
  KEY `ix_subsidy_period_range` (`period_start`,`period_end`),
  CONSTRAINT `fk_subsidy_period_bank` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`),
  CONSTRAINT `fk_subsidy_period_reversal` FOREIGN KEY (`reversal_of_id`) REFERENCES `government_subsidy_period_entries` (`id`),
  CONSTRAINT `ck_subsidy_period_amount` CHECK ((`amount_ntd` > 0)),
  CONSTRAINT `ck_subsidy_period_range` CHECK ((`period_end` > `period_start`)),
  CONSTRAINT `ck_subsidy_period_unit` CHECK ((`period_unit` in (_utf8mb4'month',_utf8mb4'quarter',_utf8mb4'year')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_period_members` (
  `receipt_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_end_date` date NOT NULL,
  `amount_ntd` bigint NOT NULL,
  PRIMARY KEY (`receipt_id`,`case_no`),
  KEY `ix_subsidy_period_case` (`case_no`),
  CONSTRAINT `fk_subsidy_period_member` FOREIGN KEY (`receipt_id`) REFERENCES `government_subsidy_period_entries` (`id`),
  CONSTRAINT `ck_subsidy_period_member_amount` CHECK ((`amount_ntd` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_period_years` (
  `period_year` int NOT NULL,
  `aggregate_version` bigint NOT NULL DEFAULT '0',
  PRIMARY KEY (`period_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_projection_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `transaction_id` bigint NOT NULL,
  `before_status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_net_allocated_ntd` bigint unsigned NOT NULL,
  `after_net_allocated_ntd` bigint unsigned NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_projection_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_government_subsidy_projection_event_identity` (`id`,`batch_id`),
  KEY `fk_government_subsidy_projection_event_account` (`batch_id`),
  KEY `fk_government_subsidy_projection_event_transaction` (`transaction_id`,`batch_id`),
  CONSTRAINT `fk_government_subsidy_projection_event_account` FOREIGN KEY (`batch_id`) REFERENCES `government_subsidy_batch_accounts` (`batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_projection_event_transaction` FOREIGN KEY (`transaction_id`, `batch_id`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_projection_event_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_government_subsidy_projection_event_version` CHECK ((`resulting_batch_version` = (`expected_batch_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `government_subsidy_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `claim_batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `transaction_type` enum('receipt','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(18,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `reversal_target_type` enum('receipt','reversal') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
  `expected_batch_version` bigint unsigned DEFAULT NULL,
  `resulting_batch_version` bigint unsigned DEFAULT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_transaction_import_row` (`finance_import_row_id`),
  UNIQUE KEY `uq_government_subsidy_transaction_reference` (`external_reference`),
  UNIQUE KEY `uq_government_subsidy_transaction_id_batch` (`id`,`claim_batch_id`),
  UNIQUE KEY `uq_government_subsidy_transaction_reversal_target` (`id`,`claim_batch_id`,`transaction_type`),
  UNIQUE KEY `uq_government_subsidy_transaction_idempotency` (`idempotency_key`),
  KEY `idx_government_subsidy_transaction_batch` (`claim_batch_id`,`occurred_at`),
  KEY `idx_government_subsidy_transaction_reversal` (`reversal_of_transaction_id`),
  KEY `fk_government_subsidy_transaction_reversal_receipt` (`reversal_of_transaction_id`,`claim_batch_id`,`reversal_target_type`),
  CONSTRAINT `fk_government_subsidy_transaction_batch` FOREIGN KEY (`claim_batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_transaction_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_government_subsidy_transaction_reversal_receipt` FOREIGN KEY (`reversal_of_transaction_id`, `claim_batch_id`, `reversal_target_type`) REFERENCES `government_subsidy_transactions` (`id`, `claim_batch_id`, `transaction_type`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_transaction_amount` CHECK ((`amount` > 0)),
  CONSTRAINT `chk_government_subsidy_transaction_new_fingerprint` CHECK (((`preview_fingerprint` is null) or regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_government_subsidy_transaction_new_version` CHECK (((`expected_batch_version` is null) or (`resulting_batch_version` = (`expected_batch_version` + 1)))),
  CONSTRAINT `chk_government_subsidy_transaction_original` CHECK ((((`transaction_type` = _utf8mb4'receipt') and (`reversal_of_transaction_id` is null)) or ((`transaction_type` = _utf8mb4'reversal') and (`reversal_of_transaction_id` is not null)))),
  CONSTRAINT `chk_government_subsidy_transaction_reversal_target` CHECK ((`reversal_target_type` = _utf8mb4'receipt')),
  CONSTRAINT `chk_government_subsidy_transaction_succeeded_date` CHECK (((`transaction_status` <> _utf8mb4'succeeded') or (`occurred_at` is not null)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_client_payment_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('receivable_from_client','payable_to_client') COLLATE utf8mb4_unicode_ci NOT NULL,
  `confirmation_kind` enum('paid','settled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payer_role` enum('client','union') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payee_role` enum('client','union') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payment_date` date DEFAULT NULL,
  `payment_date_unknown_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_availability` enum('missing','ambiguous','unrecoverable') COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `historical_adoption_receipt_id` bigint unsigned NOT NULL,
  `expected_account_version` bigint unsigned NOT NULL,
  `resulting_account_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_client_payment_event_identity` (`event_identity`),
  UNIQUE KEY `uq_historical_client_payment_event_idempotency` (`idempotency_key`),
  KEY `idx_historical_client_payment_case` (`case_no`,`id`),
  KEY `fk_historical_client_payment_adoption` (`historical_adoption_receipt_id`),
  CONSTRAINT `fk_historical_client_payment_adoption` FOREIGN KEY (`historical_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_client_payment_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_client_payment_date` CHECK ((((`payment_date` is not null) and (`payment_date_unknown_reason` is null)) or ((`payment_date` is null) and (char_length(trim(`payment_date_unknown_reason`)) > 0)))),
  CONSTRAINT `chk_historical_client_payment_direction` CHECK ((((`direction` = _utf8mb4'receivable_from_client') and (`payer_role` = _utf8mb4'client') and (`payee_role` = _utf8mb4'union')) or ((`direction` = _utf8mb4'payable_to_client') and (`payer_role` = _utf8mb4'union') and (`payee_role` = _utf8mb4'client')))),
  CONSTRAINT `chk_historical_client_payment_text` CHECK (((char_length(trim(`event_identity`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`actor_id`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_historical_client_payment_version` CHECK ((`resulting_account_version` = (`expected_account_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_client_payment_obligation_links` (
  `event_id` bigint unsigned NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_snapshot_ntd` bigint NOT NULL,
  `obligation_type` enum('deposit','first','second','refund','subsidy_return','adjustment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_direction` enum('receivable_from_client','payable_to_client') COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_projection_version` bigint unsigned NOT NULL,
  `link_ordinal` int unsigned NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`event_id`,`obligation_identity`),
  UNIQUE KEY `uq_historical_client_payment_link_ordinal` (`event_id`,`link_ordinal`),
  KEY `idx_historical_client_payment_link_obligation` (`obligation_identity`,`event_id`),
  CONSTRAINT `fk_historical_client_payment_link_event` FOREIGN KEY (`event_id`) REFERENCES `historical_client_payment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_client_payment_link_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_client_payment_link_amount` CHECK ((`amount_snapshot_ntd` > 0)),
  CONSTRAINT `chk_historical_client_payment_link_ordinal` CHECK ((`link_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_client_payment_projections` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint unsigned NOT NULL,
  `confirmation_kind` enum('paid','settled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_snapshot_ntd` bigint NOT NULL,
  `obligation_projection_version` bigint unsigned NOT NULL,
  `account_version` bigint unsigned NOT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`obligation_identity`),
  KEY `idx_historical_client_payment_projection_case` (`case_no`,`obligation_identity`),
  KEY `fk_historical_client_payment_projection_event` (`current_event_id`),
  CONSTRAINT `fk_historical_client_payment_projection_event` FOREIGN KEY (`current_event_id`) REFERENCES `historical_client_payment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_client_payment_projection_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `client_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_client_payment_projection_amount` CHECK ((`amount_snapshot_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_client_payment_source_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_client_payment_outbox_intent` (`intent_key`),
  KEY `idx_historical_client_payment_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_historical_client_payment_outbox_event` (`event_id`),
  CONSTRAINT `fk_historical_client_payment_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `historical_client_payment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_client_payment_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_adoption_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('historical_order_adopted','historical_order_review_required') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp(6) NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_adoption_outbox_intent` (`intent_key`),
  KEY `idx_historical_order_adoption_outbox_pending` (`published_at`,`attempts`,`id`),
  KEY `fk_historical_order_adoption_outbox_receipt` (`receipt_id`),
  CONSTRAINT `fk_historical_order_adoption_outbox_receipt` FOREIGN KEY (`receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_adoption_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_adoption_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `outcome` enum('adopted','review_required','current_conflict','unmatched_case') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned DEFAULT NULL,
  `resulting_version` bigint unsigned DEFAULT NULL,
  `lifecycle_event_id` bigint unsigned DEFAULT NULL,
  `assignment_count` int unsigned NOT NULL DEFAULT '0',
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_snapshot` json NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_adoption_key` (`idempotency_key`),
  UNIQUE KEY `uq_historical_order_adoption_source` (`source_event_identity`),
  KEY `idx_historical_order_adoption_case` (`case_no`,`created_at`),
  KEY `fk_historical_order_adoption_lifecycle_event` (`lifecycle_event_id`),
  KEY `fk_historical_order_adoption_review` (`review_identity`),
  CONSTRAINT `fk_historical_order_adoption_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_adoption_lifecycle_event` FOREIGN KEY (`lifecycle_event_id`) REFERENCES `order_lifecycle_state_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_adoption_review` FOREIGN KEY (`review_identity`) REFERENCES `historical_order_adoption_reviews` (`review_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_adoption_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`source_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_ascii'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_order_adoption_shape` CHECK ((((`outcome` = _utf8mb4'unmatched_case') and (`lifecycle_event_id` is null) and (`expected_version` is null) and (`resulting_version` is null)) or ((`outcome` = _utf8mb4'adopted') and (`expected_version` is not null) and (`case_no` is not null) and (((`lifecycle_event_id` is null) and (`resulting_version` = `expected_version`)) or ((`lifecycle_event_id` is not null) and (`resulting_version` = (`expected_version` + 1))))) or ((`outcome` in (_utf8mb4'review_required',_utf8mb4'current_conflict')) and (`lifecycle_event_id` is null) and (`expected_version` is not null) and (`resulting_version` = `expected_version`) and (`case_no` is not null)))),
  CONSTRAINT `chk_historical_order_adoption_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_adoption_reviews` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `case_identity` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `issue_codes` json NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_review_identity` (`review_identity`),
  UNIQUE KEY `uq_historical_order_review_source` (`source_event_identity`),
  CONSTRAINT `chk_historical_order_review_fingerprint` CHECK (regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_historical_order_review_payloads` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_operational_baseline_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `baseline_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prior_baseline_event_id` bigint unsigned DEFAULT NULL,
  `order_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `selected_step` tinyint unsigned NOT NULL,
  `expected_orders_version` bigint unsigned NOT NULL,
  `resulting_orders_version` bigint unsigned NOT NULL,
  `owner_binding_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `evidence_mode` enum('retained','historical_evidence_unavailable_accepted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `document_kind` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `affected_steps` json DEFAULT NULL,
  `candidate_snapshot` json NOT NULL,
  `step_projection` json NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_operational_baseline_event_identity` (`baseline_event_identity`),
  UNIQUE KEY `uq_historical_operational_baseline_prior_event` (`prior_baseline_event_id`),
  KEY `idx_historical_operational_baseline_case` (`case_no`,`resulting_orders_version`,`id`),
  KEY `idx_historical_operational_baseline_source` (`source_event_identity`,`source_version`),
  CONSTRAINT `fk_historical_operational_baseline_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_operational_baseline_prior` FOREIGN KEY (`prior_baseline_event_id`) REFERENCES `historical_order_operational_baseline_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_operational_baseline_source` FOREIGN KEY (`source_event_identity`) REFERENCES `historical_order_adoption_receipts` (`source_event_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_operational_baseline_evidence` CHECK ((((`evidence_mode` = _utf8mb4'retained') and (`document_kind` is null) and (`affected_steps` is null)) or ((`evidence_mode` = _utf8mb4'historical_evidence_unavailable_accepted') and (char_length(trim(`document_kind`)) > 0) and (json_type(`affected_steps`) = _utf8mb4'ARRAY') and (json_length(`affected_steps`) > 0)))),
  CONSTRAINT `chk_historical_operational_baseline_fingerprints` CHECK ((regexp_like(`owner_binding_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_operational_baseline_snapshots` CHECK (((json_type(`candidate_snapshot`) = _utf8mb4'OBJECT') and (json_type(`step_projection`) = _utf8mb4'ARRAY') and (json_length(`step_projection`) = `selected_step`))),
  CONSTRAINT `chk_historical_operational_baseline_step` CHECK ((`selected_step` between 1 and 11)),
  CONSTRAINT `chk_historical_operational_baseline_text` CHECK (((char_length(trim(`baseline_event_identity`)) > 0) and (char_length(trim(`order_identity`)) > 0) and (char_length(trim(`source_event_identity`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`evidence_reference`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_historical_operational_baseline_versions` CHECK ((`resulting_orders_version` = `expected_orders_version`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_operational_baseline_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `receipt_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('historical_operational_baseline_confirmed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp(6) NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_operational_baseline_outbox_event` (`event_id`),
  UNIQUE KEY `uq_historical_operational_baseline_outbox_receipt` (`receipt_id`),
  UNIQUE KEY `uq_historical_operational_baseline_outbox_intent` (`intent_key`),
  KEY `idx_historical_operational_baseline_outbox_pending` (`published_at`,`attempts`,`id`),
  CONSTRAINT `fk_historical_operational_baseline_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `historical_order_operational_baseline_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_operational_baseline_outbox_receipt` FOREIGN KEY (`receipt_id`) REFERENCES `historical_order_operational_baseline_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_operational_baseline_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_historical_operational_baseline_outbox_text` CHECK ((char_length(trim(`intent_key`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_operational_baseline_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `resulting_orders_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_operational_baseline_receipt_identity` (`receipt_identity`),
  UNIQUE KEY `uq_historical_operational_baseline_receipt_event` (`event_id`),
  UNIQUE KEY `uq_historical_operational_baseline_receipt_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_historical_operational_baseline_receipt_event` FOREIGN KEY (`event_id`) REFERENCES `historical_order_operational_baseline_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_operational_baseline_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_operational_baseline_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_historical_operational_baseline_receipt_text` CHECK (((char_length(trim(`receipt_identity`)) > 0) and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`actor`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_pairing_evidence` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_id` bigint unsigned NOT NULL,
  `caregiver_ordinal` int unsigned NOT NULL,
  `staff_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int DEFAULT NULL,
  `resolution` enum('blank','staff_missing','staff_ambiguous','evidence_only','assignment_candidate','assignment_reused','assignment_conflict') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_start_date` date DEFAULT NULL,
  `source_end_date` date DEFAULT NULL,
  `assignment_id` bigint DEFAULT NULL,
  `issue_codes` json NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_pairing_ordinal` (`receipt_id`,`caregiver_ordinal`),
  KEY `idx_historical_order_pairing_staff` (`staff_id`,`created_at`),
  KEY `fk_historical_order_pairing_assignment` (`assignment_id`),
  CONSTRAINT `fk_historical_order_pairing_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_pairing_receipt` FOREIGN KEY (`receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_pairing_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_pairing_assignment_shape` CHECK ((((`resolution` = _utf8mb4'assignment_candidate') and (`assignment_id` is not null) and (`staff_id` is not null)) or ((`resolution` <> _utf8mb4'assignment_candidate') and (`assignment_id` is null)))),
  CONSTRAINT `chk_historical_order_pairing_issues` CHECK ((json_type(`issue_codes`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_historical_order_pairing_ordinal` CHECK ((`caregiver_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_review_remediation_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prior_review_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_adoption_receipt_id` bigint unsigned NOT NULL,
  `replacement_adoption_receipt_id` bigint unsigned NOT NULL,
  `disposition` enum('corrected_source_adopted','superseded_by_replacement_review') COLLATE utf8mb4_unicode_ci NOT NULL,
  `successor_review_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_content_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `review_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_review_remediation_event` (`event_identity`),
  UNIQUE KEY `uq_historical_order_review_remediation_prior` (`prior_review_identity`),
  UNIQUE KEY `uq_historical_order_review_remediation_replacement` (`replacement_adoption_receipt_id`),
  KEY `idx_historical_order_review_remediation_successor` (`successor_review_identity`,`id`),
  KEY `fk_historical_order_review_remediation_original_receipt` (`original_adoption_receipt_id`),
  CONSTRAINT `fk_historical_order_review_remediation_original_receipt` FOREIGN KEY (`original_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_review_remediation_prior` FOREIGN KEY (`prior_review_identity`) REFERENCES `historical_order_adoption_reviews` (`review_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_review_remediation_replacement_receipt` FOREIGN KEY (`replacement_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_review_remediation_successor` FOREIGN KEY (`successor_review_identity`) REFERENCES `historical_order_adoption_reviews` (`review_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_review_remediation_disposition` CHECK ((((`disposition` = _utf8mb4'corrected_source_adopted') and (`successor_review_identity` is null)) or ((`disposition` = _utf8mb4'superseded_by_replacement_review') and (`successor_review_identity` is not null)))),
  CONSTRAINT `chk_historical_order_review_remediation_evidence` CHECK ((json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_historical_order_review_remediation_fingerprints` CHECK ((regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`review_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_order_review_remediation_replacement` CHECK ((`replacement_adoption_receipt_id` <> `original_adoption_receipt_id`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_review_remediation_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `remediation_receipt_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('historical_order_review_remediated') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp(6) NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_review_remediation_outbox_intent` (`intent_key`),
  KEY `idx_historical_order_review_remediation_outbox_pending` (`published_at`,`attempts`,`id`),
  KEY `fk_historical_order_review_remediation_outbox_event` (`event_id`),
  KEY `fk_historical_order_review_remediation_outbox_receipt` (`remediation_receipt_id`),
  CONSTRAINT `fk_historical_order_review_remediation_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `historical_order_review_remediation_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_order_review_remediation_outbox_receipt` FOREIGN KEY (`remediation_receipt_id`) REFERENCES `historical_order_review_remediation_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_review_remediation_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_order_review_remediation_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `remediation_receipt_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `expected_remediation_version` bigint unsigned NOT NULL,
  `resulting_remediation_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_order_review_remediation_receipt` (`remediation_receipt_identity`),
  UNIQUE KEY `uq_historical_order_review_remediation_receipt_event` (`event_id`),
  UNIQUE KEY `uq_historical_order_review_remediation_receipt_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_historical_order_review_remediation_receipt_event` FOREIGN KEY (`event_id`) REFERENCES `historical_order_review_remediation_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_order_review_remediation_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_order_review_remediation_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_historical_order_review_remediation_receipt_version` CHECK (((`expected_remediation_version` = 0) and (`resulting_remediation_version` = 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_owner_selection_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `finance_import_row_id` bigint NOT NULL,
  `batch_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_references` json NOT NULL,
  `source_canonical_fact_version` bigint unsigned NOT NULL,
  `resulting_canonical_fact_version` bigint unsigned NOT NULL,
  `batch_version` bigint unsigned NOT NULL,
  `obligation_projection_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_owner_selection_idempotency` (`idempotency_key`,`finance_import_row_id`),
  KEY `idx_historical_owner_selection_row` (`finance_import_row_id`,`created_at`),
  KEY `fk_historical_owner_selection_batch` (`batch_id`),
  KEY `fk_historical_owner_selection_obligation` (`obligation_identity`,`case_no`),
  CONSTRAINT `fk_historical_owner_selection_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_owner_selection_obligation` FOREIGN KEY (`obligation_identity`, `case_no`) REFERENCES `client_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_owner_selection_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_owner_selection_evidence` CHECK (((json_type(`evidence_references`) = _utf8mb4'ARRAY') and (json_length(`evidence_references`) > 0))),
  CONSTRAINT `chk_historical_owner_selection_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_historical_owner_selection_versions` CHECK (((`resulting_canonical_fact_version` = (`source_canonical_fact_version` + 1)) and (`obligation_projection_version` >= 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_service_accounting_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('historical_service_accounting_applied') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_service_accounting_outbox_intent` (`intent_key`),
  KEY `idx_historical_service_accounting_outbox_pending` (`published_at`,`id`),
  KEY `fk_historical_service_accounting_outbox_event` (`event_id`),
  CONSTRAINT `fk_historical_service_accounting_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `historical_service_day_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_service_accounting_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_service_day_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `historical_adoption_receipt_id` bigint unsigned NOT NULL,
  `expected_day_revision` bigint unsigned NOT NULL,
  `resulting_day_revision` bigint unsigned NOT NULL,
  `total_actual_service_days` int unsigned NOT NULL,
  `total_actual_service_hours` decimal(12,2) NOT NULL,
  `historical_floor_fee_ntd` bigint NOT NULL,
  `client_obligation_amount_ntd` bigint NOT NULL,
  `staff_obligation_amount_ntd` bigint NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_service_day_event_identity` (`event_identity`),
  UNIQUE KEY `uq_historical_service_day_idempotency` (`idempotency_key`),
  KEY `idx_historical_service_day_case_revision` (`case_no`,`resulting_day_revision`),
  KEY `fk_historical_service_day_adoption` (`historical_adoption_receipt_id`),
  CONSTRAINT `fk_historical_service_day_adoption` FOREIGN KEY (`historical_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_service_day_fingerprints` CHECK ((regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_historical_service_day_revision` CHECK ((`resulting_day_revision` = (`expected_day_revision` + 1))),
  CONSTRAINT `chk_historical_service_day_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_historical_service_day_values` CHECK (((`total_actual_service_days` > 0) and (`total_actual_service_hours` > 0) and (`historical_floor_fee_ntd` >= 0) and (`client_obligation_amount_ntd` >= 0) and (`staff_obligation_amount_ntd` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_service_day_items` (
  `event_id` bigint unsigned NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `item_ordinal` int unsigned NOT NULL,
  `actual_service_days` int unsigned NOT NULL,
  `actual_service_hours` decimal(12,2) NOT NULL,
  `floor_fee_allocated_ntd` bigint NOT NULL,
  `staff_obligation_amount_ntd` bigint NOT NULL,
  `payroll_policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payroll_policy_kind` enum('citizen','subsidized_citizen','non_citizen') COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`event_id`,`assignment_id`),
  UNIQUE KEY `uq_historical_service_day_item_ordinal` (`event_id`,`item_ordinal`),
  KEY `fk_historical_service_day_item_assignment` (`assignment_id`),
  KEY `fk_historical_service_day_item_staff` (`staff_id`),
  KEY `fk_historical_service_day_item_policy` (`payroll_policy_version`,`payroll_policy_kind`),
  CONSTRAINT `fk_historical_service_day_item_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_item_event` FOREIGN KEY (`event_id`) REFERENCES `historical_service_day_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_item_policy` FOREIGN KEY (`payroll_policy_version`, `payroll_policy_kind`) REFERENCES `payroll_rate_policies` (`policy_version`, `policy_kind`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_item_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_service_day_item_values` CHECK (((`item_ordinal` > 0) and (`actual_service_days` > 0) and (`actual_service_hours` > 0) and (`floor_fee_allocated_ntd` >= 0) and (`staff_obligation_amount_ntd` > 0) and (`hourly_rate_ntd` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_service_day_projections` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint unsigned NOT NULL,
  `historical_adoption_receipt_id` bigint unsigned NOT NULL,
  `day_revision` bigint unsigned NOT NULL,
  `total_actual_service_days` int unsigned NOT NULL,
  `total_actual_service_hours` decimal(12,2) NOT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`case_no`),
  UNIQUE KEY `uq_historical_service_day_projection_event` (`current_event_id`),
  KEY `fk_historical_service_day_projection_adoption` (`historical_adoption_receipt_id`),
  CONSTRAINT `fk_historical_service_day_projection_adoption` FOREIGN KEY (`historical_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_projection_event` FOREIGN KEY (`current_event_id`) REFERENCES `historical_service_day_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_service_day_projection_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_service_day_projection_values` CHECK (((`day_revision` > 0) and (`total_actual_service_days` > 0) and (`total_actual_service_hours` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_staff_payout_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `confirmation_kind` enum('paid','settled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payer_role` enum('union') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payee_role` enum('staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payment_date` date DEFAULT NULL,
  `payment_date_unknown_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_availability` enum('missing','ambiguous','unrecoverable') COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `historical_adoption_receipt_id` bigint unsigned NOT NULL,
  `expected_staff_payables_version` bigint unsigned NOT NULL,
  `resulting_staff_payables_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_staff_payout_event_identity` (`event_identity`),
  UNIQUE KEY `uq_historical_staff_payout_event_idempotency` (`idempotency_key`),
  KEY `idx_historical_staff_payout_case_staff` (`case_no`,`staff_id`,`id`),
  KEY `fk_historical_staff_payout_staff` (`staff_id`),
  KEY `fk_historical_staff_payout_adoption` (`historical_adoption_receipt_id`),
  CONSTRAINT `fk_historical_staff_payout_adoption` FOREIGN KEY (`historical_adoption_receipt_id`) REFERENCES `historical_order_adoption_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_staff_payout_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_staff_payout_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_staff_payout_date` CHECK ((((`payment_date` is not null) and (`payment_date_unknown_reason` is null)) or ((`payment_date` is null) and (char_length(trim(`payment_date_unknown_reason`)) > 0)))),
  CONSTRAINT `chk_historical_staff_payout_text` CHECK (((char_length(trim(`event_identity`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`actor_id`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_historical_staff_payout_version` CHECK ((`resulting_staff_payables_version` = (`expected_staff_payables_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_staff_payout_obligation_links` (
  `event_id` bigint unsigned NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_snapshot_ntd` bigint NOT NULL,
  `obligation_payroll_version` bigint unsigned NOT NULL,
  `link_ordinal` int unsigned NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`event_id`,`obligation_identity`),
  UNIQUE KEY `uq_historical_staff_payout_link_ordinal` (`event_id`,`link_ordinal`),
  KEY `idx_historical_staff_payout_link_obligation` (`obligation_identity`,`event_id`),
  CONSTRAINT `fk_historical_staff_payout_link_event` FOREIGN KEY (`event_id`) REFERENCES `historical_staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_staff_payout_link_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_staff_payout_link_amount` CHECK ((`amount_snapshot_ntd` > 0)),
  CONSTRAINT `chk_historical_staff_payout_link_ordinal` CHECK ((`link_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_staff_payout_projections` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `current_event_id` bigint unsigned NOT NULL,
  `confirmation_kind` enum('paid','settled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_snapshot_ntd` bigint NOT NULL,
  `obligation_payroll_version` bigint unsigned NOT NULL,
  `staff_payables_version` bigint unsigned NOT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`obligation_identity`),
  KEY `idx_historical_staff_payout_projection_case` (`case_no`,`staff_id`,`obligation_identity`),
  KEY `fk_historical_staff_payout_projection_event` (`current_event_id`),
  CONSTRAINT `fk_historical_staff_payout_projection_event` FOREIGN KEY (`current_event_id`) REFERENCES `historical_staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_historical_staff_payout_projection_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_staff_payout_projection_amount` CHECK ((`amount_snapshot_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `historical_staff_payout_source_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_historical_staff_payout_outbox_intent` (`intent_key`),
  KEY `idx_historical_staff_payout_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_historical_staff_payout_outbox_event` (`event_id`),
  CONSTRAINT `fk_historical_staff_payout_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `historical_staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_historical_staff_payout_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `holidays` (
  `holiday_date` date NOT NULL COMMENT '假日日期',
  `holiday_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '假日名稱',
  `is_double_pay_default` tinyint(1) DEFAULT '0' COMMENT '相容欄位；排班不因國定假日自動套用雙倍薪資',
  PRIMARY KEY (`holiday_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `import_warning_current_tasks` (
  `occurrence_id` bigint NOT NULL,
  `tracking_status` enum('open','awaiting_external_confirmation','response_recorded','reimport_requested','closed','auto_resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `tracking_version` bigint unsigned NOT NULL,
  `replacement_occurrence_id` bigint DEFAULT NULL,
  `last_event_id` bigint NOT NULL,
  `last_event_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`occurrence_id`),
  KEY `idx_import_warning_current_active` (`tracking_status`,`last_event_at`),
  KEY `fk_import_warning_current_replacement` (`replacement_occurrence_id`),
  KEY `fk_import_warning_current_event` (`last_event_id`),
  CONSTRAINT `fk_import_warning_current_event` FOREIGN KEY (`last_event_id`) REFERENCES `import_warning_tracking_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_import_warning_current_occurrence` FOREIGN KEY (`occurrence_id`) REFERENCES `import_warning_occurrences` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_import_warning_current_replacement` FOREIGN KEY (`replacement_occurrence_id`) REFERENCES `import_warning_occurrences` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_import_warning_current_version` CHECK ((`tracking_version` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `import_warning_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `occurrence_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owning_lane` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_receipt_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logical_code` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  `field_path` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `issue_codes` json NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_import_warning_occurrence_identity` (`occurrence_identity`),
  UNIQUE KEY `uq_import_warning_occurrence_source` (`owning_lane`,`source_event_identity`,`logical_code`,`field_path`),
  KEY `idx_import_warning_occurrence_lane_subject` (`owning_lane`,`subject`),
  CONSTRAINT `chk_import_warning_occurrence_payload` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `import_warning_tracking_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurrence_id` bigint NOT NULL,
  `action` enum('opened','awaiting_external_confirmation','response_recorded','reimport_requested','closed','auto_resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_status` enum('open','awaiting_external_confirmation','response_recorded','reimport_requested','closed','auto_resolved') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `after_status` enum('open','awaiting_external_confirmation','response_recorded','reimport_requested','closed','auto_resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_kind` enum('union_operator','system') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_identity` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_code` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `evidence_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_import_warning_tracking_event_identity` (`event_identity`),
  UNIQUE KEY `uq_import_warning_tracking_event_key` (`idempotency_key`),
  KEY `idx_import_warning_tracking_event_occurrence` (`occurrence_id`,`resulting_version`),
  CONSTRAINT `fk_import_warning_tracking_event_occurrence` FOREIGN KEY (`occurrence_id`) REFERENCES `import_warning_occurrences` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_import_warning_tracking_event_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_import_warning_tracking_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `import_warning_tracking_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `tracking_event_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` timestamp NULL DEFAULT NULL,
  `attempts` int NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_import_warning_tracking_outbox_intent` (`intent_key`),
  KEY `idx_import_warning_tracking_outbox_pending` (`published_at`,`attempts`,`id`),
  KEY `fk_import_warning_tracking_outbox_event` (`tracking_event_id`),
  CONSTRAINT `fk_import_warning_tracking_outbox_event` FOREIGN KEY (`tracking_event_id`) REFERENCES `import_warning_tracking_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_import_warning_tracking_outbox_attempts` CHECK ((`attempts` >= 0)),
  CONSTRAINT `chk_import_warning_tracking_outbox_snapshot` CHECK ((json_type(`bounded_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `import_warning_tracking_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `occurrence_id` bigint NOT NULL,
  `tracking_event_id` bigint NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_import_warning_tracking_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_import_warning_tracking_receipt_event` (`tracking_event_id`),
  KEY `fk_import_warning_tracking_receipt_occurrence` (`occurrence_id`),
  CONSTRAINT `fk_import_warning_tracking_receipt_event` FOREIGN KEY (`tracking_event_id`) REFERENCES `import_warning_tracking_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_import_warning_tracking_receipt_occurrence` FOREIGN KEY (`occurrence_id`) REFERENCES `import_warning_occurrences` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_import_warning_tracking_receipt_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_import_warning_tracking_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_answer_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `answer_request_id` bigint unsigned NOT NULL,
  `answer_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `index_version` int unsigned NOT NULL,
  `authoritative` tinyint(1) NOT NULL DEFAULT '0',
  `line_delivery_task_id` bigint unsigned DEFAULT NULL,
  `answered_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_answer_receipt_request` (`answer_request_id`),
  KEY `fk_knowledge_answer_delivery` (`line_delivery_task_id`),
  CONSTRAINT `fk_knowledge_answer_delivery` FOREIGN KEY (`line_delivery_task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_knowledge_answer_request` FOREIGN KEY (`answer_request_id`) REFERENCES `knowledge_answer_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_knowledge_answer_non_authoritative` CHECK ((`authoritative` = false))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_answer_requests` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `question` varchar(2000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `requester_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_status` enum('pending','processing','answered','unsupported','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `completed_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_answer_request_key` (`idempotency_key`),
  KEY `idx_knowledge_answer_request_status` (`request_status`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_answer_sources` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `answer_receipt_id` bigint unsigned NOT NULL,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `safe_excerpt` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `citation_order` int unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_answer_source_order` (`answer_receipt_id`,`citation_order`),
  CONSTRAINT `fk_knowledge_answer_source_receipt` FOREIGN KEY (`answer_receipt_id`) REFERENCES `knowledge_answer_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_apply_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `receipt_json` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_indexes` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `index_version` int unsigned NOT NULL,
  `index_status` enum('requested','building','ready','stale','failed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_set_digest` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `built_at_utc` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_index_version` (`index_version`),
  KEY `idx_knowledge_index_ready` (`index_status`,`index_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_item_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `knowledge_item_id` bigint NOT NULL,
  `actor_admin_user_id` bigint NOT NULL,
  `event_type` enum('ingested','reviewed','published','retired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_version` bigint unsigned NOT NULL,
  `after_version` bigint unsigned NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `snapshot_json` json NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_event_idempotency` (`idempotency_key`),
  KEY `idx_knowledge_event_item` (`knowledge_item_id`,`created_at`),
  KEY `fk_knowledge_event_actor` (`actor_admin_user_id`),
  CONSTRAINT `fk_knowledge_event_actor` FOREIGN KEY (`actor_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_knowledge_event_item` FOREIGN KEY (`knowledge_item_id`) REFERENCES `knowledge_items` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_knowledge_event_version` CHECK ((`after_version` = (`before_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_item_versions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `item_id` bigint NOT NULL,
  `item_version` bigint unsigned NOT NULL,
  `content` mediumtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('ingested','reviewed','published','retired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_admin_user_id` bigint NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recorded_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_item_version` (`item_id`,`item_version`),
  UNIQUE KEY `uq_knowledge_version_key` (`idempotency_key`),
  KEY `fk_knowledge_version_actor` (`actor_admin_user_id`),
  CONSTRAINT `fk_knowledge_version_actor` FOREIGN KEY (`actor_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_knowledge_version_item` FOREIGN KEY (`item_id`) REFERENCES `knowledge_items` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_uri` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_trust_tier` enum('internal_policy','government_source','approved_partner') COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `state` enum('draft','reviewed','published','retired') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `version` bigint unsigned NOT NULL DEFAULT '0',
  `created_by_admin_user_id` bigint NOT NULL,
  `reviewed_by_admin_user_id` bigint DEFAULT NULL,
  `published_by_admin_user_id` bigint DEFAULT NULL,
  `retired_by_admin_user_id` bigint DEFAULT NULL,
  `review_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `publication_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `retired_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `published_at` datetime DEFAULT NULL,
  `retired_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_source_digest` (`source_uri`,`content_digest`),
  UNIQUE KEY `uq_knowledge_source_identity` (`source_identity`),
  KEY `idx_knowledge_answer` (`state`,`source_trust_tier`,`published_at`),
  KEY `fk_knowledge_creator` (`created_by_admin_user_id`),
  KEY `fk_knowledge_reviewer` (`reviewed_by_admin_user_id`),
  KEY `fk_knowledge_publisher` (`published_by_admin_user_id`),
  KEY `fk_knowledge_retirer` (`retired_by_admin_user_id`),
  CONSTRAINT `fk_knowledge_creator` FOREIGN KEY (`created_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_knowledge_publisher` FOREIGN KEY (`published_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_knowledge_retirer` FOREIGN KEY (`retired_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_knowledge_reviewer` FOREIGN KEY (`reviewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_knowledge_published_actor` CHECK (((`state` <> _utf8mb4'published') or (`published_by_admin_user_id` is not null)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `knowledge_jobs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `job_type` enum('index_build','answer') COLLATE utf8mb4_unicode_ci NOT NULL,
  `processing_status` enum('pending','processing','completed','retry_pending','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `answer_request_id` bigint unsigned DEFAULT NULL,
  `target_index_version` int unsigned DEFAULT NULL,
  `question` varchar(2000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '3',
  `available_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at_utc` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `completed_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_job_key` (`idempotency_key`),
  KEY `idx_knowledge_job_claim` (`processing_status`,`available_at_utc`,`id`),
  KEY `fk_knowledge_job_answer_request` (`answer_request_id`),
  CONSTRAINT `fk_knowledge_job_answer_request` FOREIGN KEY (`answer_request_id`) REFERENCES `knowledge_answer_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_alert_delivery_intents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `health_event_id` bigint unsigned NOT NULL,
  `target_id` bigint unsigned NOT NULL,
  `delivery_task_id` bigint unsigned DEFAULT NULL,
  `projection_status` enum('queued','skipped','failed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `resolved_line_target_type` enum('user','group') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_line_target_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_alert_delivery_intent` (`health_event_id`,`target_id`),
  KEY `idx_line_alert_delivery_task` (`delivery_task_id`),
  KEY `fk_line_alert_intent_target` (`target_id`),
  CONSTRAINT `fk_line_alert_intent_delivery` FOREIGN KEY (`delivery_task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_alert_intent_event` FOREIGN KEY (`health_event_id`) REFERENCES `runtime_health_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_alert_intent_target` FOREIGN KEY (`target_id`) REFERENCES `line_alert_notification_targets` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_alert_notification_targets` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `target_type` enum('admin_user','group') COLLATE utf8mb4_unicode_ci NOT NULL,
  `admin_user_id` bigint DEFAULT NULL,
  `group_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `minimum_status` enum('warning','critical') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'warning',
  `created_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_alert_admin_target` (`admin_user_id`),
  UNIQUE KEY `uq_line_alert_group_target` (`group_id`),
  CONSTRAINT `fk_line_alert_admin_target` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_alert_target_identity` CHECK ((((`target_type` = _utf8mb4'admin_user') and (`admin_user_id` is not null) and (`group_id` is null)) or ((`target_type` = _utf8mb4'group') and (`admin_user_id` is null) and (`group_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_command_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_command_receipt_key` (`idempotency_key`),
  KEY `idx_line_command_receipt_family` (`command_family`,`created_at_utc`),
  CONSTRAINT `chk_line_command_receipt_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_command_receipt_snapshot` CHECK (((`result_snapshot` is null) or (json_type(`result_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_configuration_current` (
  `configuration_kind` enum('message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules') COLLATE utf8mb4_unicode_ci NOT NULL,
  `revision` bigint unsigned NOT NULL,
  `revision_id` bigint unsigned NOT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`configuration_kind`),
  UNIQUE KEY `uq_line_configuration_current_revision` (`revision_id`),
  CONSTRAINT `fk_line_configuration_current_revision` FOREIGN KEY (`revision_id`) REFERENCES `line_configuration_revisions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_configuration_revisions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `configuration_kind` enum('message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules') COLLATE utf8mb4_unicode_ci NOT NULL,
  `revision` bigint unsigned NOT NULL,
  `definition_snapshot` json NOT NULL,
  `definition_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_configuration_revision` (`configuration_kind`,`revision`),
  UNIQUE KEY `uq_line_configuration_idempotency` (`idempotency_key`),
  CONSTRAINT `chk_line_configuration_fingerprint` CHECK (regexp_like(`definition_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_configuration_snapshot` CHECK ((json_type(`definition_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_confirmation_requests` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_type` enum('staff_verification','client_rebind') COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int DEFAULT NULL,
  `client_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `old_line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `new_line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('pending','approved','rejected','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reviewed_by_admin_user_id` bigint DEFAULT NULL COMMENT 'Web 管理中心處理者；開發終端處理時可為 NULL',
  `reviewed_by_line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `decision_reason` text COLLATE utf8mb4_unicode_ci COMMENT '核准備註或拒絕原因',
  `reviewed_at` datetime DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_confirmation_pending` (`request_type`,`status`,`created_at`),
  KEY `idx_confirmation_status_time` (`status`,`created_at`),
  KEY `idx_confirmation_admin_reviewer` (`reviewed_by_admin_user_id`,`reviewed_at`),
  KEY `idx_confirmation_requester` (`line_user_id`,`request_type`,`status`),
  KEY `fk_confirmation_client` (`client_id`),
  CONSTRAINT `fk_confirmation_admin_reviewer` FOREIGN KEY (`reviewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_confirmation_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_delivery_attempt_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `task_id` bigint unsigned NOT NULL,
  `attempt_number` int unsigned NOT NULL,
  `outcome` enum('success','retryable_failure','terminal_failure','legacy_incomplete') COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_outcome_type` enum('success','rate_limited','rejected','unavailable','timeout','legacy') COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_message_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `retry_after_seconds` int unsigned DEFAULT NULL,
  `started_at_utc` datetime(6) NOT NULL,
  `completed_at_utc` datetime(6) NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_delivery_attempt_number` (`task_id`,`attempt_number`),
  UNIQUE KEY `uq_line_delivery_attempt_idempotency` (`idempotency_key`),
  KEY `idx_line_delivery_attempt_time` (`outcome`,`completed_at_utc`),
  CONSTRAINT `fk_line_delivery_attempt_task` FOREIGN KEY (`task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_delivery_tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `recipient_type` enum('user','group','room') COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `message_kind` enum('text','flex') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scheduled_at_utc` datetime(6) NOT NULL,
  `source_aggregate_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `processing_status` enum('pending','processing','sent','retryable_failed','failed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `completed_attempts` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '3',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_acquired_at_utc` datetime(6) DEFAULT NULL,
  `lease_expires_at_utc` datetime(6) DEFAULT NULL,
  `provider_message_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sent_at_utc` datetime(6) DEFAULT NULL,
  `failed_at_utc` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_delivery_idempotency` (`idempotency_key`),
  KEY `idx_line_delivery_due` (`processing_status`,`scheduled_at_utc`,`next_attempt_at_utc`,`id`),
  KEY `idx_line_delivery_lease` (`processing_status`,`lease_expires_at_utc`),
  KEY `idx_line_delivery_source` (`source_aggregate_type`,`source_aggregate_identity`,`id`),
  CONSTRAINT `chk_line_delivery_lease_pair` CHECK ((((`lease_owner` is null) and (`lease_acquired_at_utc` is null) and (`lease_expires_at_utc` is null)) or ((`lease_owner` is not null) and (`lease_acquired_at_utc` is not null) and (`lease_expires_at_utc` > `lease_acquired_at_utc`)))),
  CONSTRAINT `chk_line_delivery_payload_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_delivery_payload_object` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_domain_audit_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `action` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_line_domain_audit_aggregate` (`aggregate_type`,`aggregate_identity`,`occurred_at_utc`,`id`),
  KEY `idx_line_domain_audit_actor` (`actor_id`,`occurred_at_utc`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_domain_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `aggregate_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `idempotency_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `processing_status` enum('pending','processing','completed','dead') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '3',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at_utc` datetime(6) DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `completed_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_domain_outbox_identity` (`idempotency_identity`),
  KEY `idx_line_domain_outbox_due` (`processing_status`,`next_attempt_at_utc`,`created_at_utc`,`id`),
  CONSTRAINT `chk_line_domain_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_friend_state_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('follow','unfollow','activity') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_status` enum('unknown','active','blocked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('active','blocked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_friend_event_identity` (`event_identity`),
  KEY `idx_line_friend_event_user` (`line_user_id`,`id`),
  CONSTRAINT `fk_line_friend_event_user` FOREIGN KEY (`line_user_id`) REFERENCES `line_platform_users` (`line_user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_friend_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_binding_failure_streaks` (
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `identity_flow_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_subject_type` enum('customer','staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_scope` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `streak_generation` bigint unsigned NOT NULL DEFAULT '0',
  `failure_count` tinyint unsigned NOT NULL DEFAULT '0',
  `last_failure_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `escalation_id` bigint DEFAULT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`line_user_id`),
  KEY `idx_line_identity_failure_flow` (`identity_flow_id`,`candidate_subject_type`,`candidate_scope`),
  KEY `idx_line_identity_failure_escalation` (`escalation_id`),
  CONSTRAINT `fk_line_identity_failure_escalation` FOREIGN KEY (`escalation_id`) REFERENCES `customer_service_escalations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_identity_failure_flow` FOREIGN KEY (`identity_flow_id`) REFERENCES `line_identity_flows` (`flow_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_identity_failure_platform_user` FOREIGN KEY (`line_user_id`) REFERENCES `line_platform_users` (`line_user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_identity_failure_count` CHECK ((`failure_count` between 0 and 2)),
  CONSTRAINT `chk_line_identity_failure_scope` CHECK ((regexp_like(`scope_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`candidate_scope`)) > 0))),
  CONSTRAINT `chk_line_identity_failure_shape` CHECK ((((`failure_count` = 0) and (`last_failure_fingerprint` is null) and (`escalation_id` is null)) or ((`failure_count` = 1) and regexp_like(`last_failure_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (`escalation_id` is null)) or ((`failure_count` = 2) and regexp_like(`last_failure_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (`escalation_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_bindings` (
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `binding_status` enum('unbound','pending_review','bound','revocation_pending','revoked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unbound',
  `subject_type` enum('customer','staff','admin') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `active_subject_key` varchar(400) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS ((case when (`binding_status` in (_utf8mb4'pending_review',_utf8mb4'bound',_utf8mb4'revocation_pending')) then concat(`subject_type`,_utf8mb4':',`subject_reference`) else NULL end)) STORED,
  PRIMARY KEY (`line_user_id`),
  UNIQUE KEY `uq_line_identity_active_subject` (`active_subject_key`),
  KEY `idx_line_identity_status` (`binding_status`,`updated_at_utc`),
  CONSTRAINT `chk_line_identity_subject_pair` CHECK ((((`binding_status` = _utf8mb4'unbound') and (`subject_type` is null) and (`subject_reference` is null)) or ((`binding_status` <> _utf8mb4'unbound') and (`subject_type` is not null) and (`subject_reference` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_flows` (
  `flow_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `flow_purpose` enum('customer_binding','staff_verification','admin_binding','staff_self_service') COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `flow_status` enum('active','used','expired','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `expires_at_utc` datetime(6) NOT NULL,
  `used_at_utc` datetime(6) DEFAULT NULL,
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`flow_id`),
  UNIQUE KEY `uq_line_identity_flow_idempotency` (`idempotency_key`),
  KEY `idx_line_identity_flow_user` (`line_user_id`,`flow_status`,`expires_at_utc`),
  CONSTRAINT `fk_line_identity_flow_user` FOREIGN KEY (`line_user_id`) REFERENCES `line_platform_users` (`line_user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_revocation_requests` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_type` enum('customer','staff','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_status` enum('pending_menu_reset','menu_reset_failed','completed','manual_completed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending_menu_reset',
  `requested_binding_version` bigint unsigned NOT NULL,
  `pending_binding_version` bigint unsigned NOT NULL,
  `completed_binding_version` bigint unsigned DEFAULT NULL,
  `default_menu_publication_id` bigint DEFAULT NULL,
  `canonical_default_menu_publication_id` bigint unsigned DEFAULT NULL,
  `provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `requested_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_reason` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `last_error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `requested_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `menu_reset_at_utc` datetime(6) DEFAULT NULL,
  `completed_at_utc` datetime(6) DEFAULT NULL,
  `completed_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `completion_reason` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `active_marker` tinyint GENERATED ALWAYS AS ((case when (`request_status` in (_utf8mb4'pending_menu_reset',_utf8mb4'menu_reset_failed')) then 1 else NULL end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_identity_revocation_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_line_identity_active_revocation` (`line_user_id`,`active_marker`),
  KEY `idx_line_identity_revocation_status` (`request_status`,`requested_at_utc`),
  KEY `fk_line_identity_revocation_publication` (`default_menu_publication_id`),
  KEY `idx_line_identity_revocation_canonical_publication` (`canonical_default_menu_publication_id`),
  KEY `fk_line_identity_revocation_role_binding` (`line_user_id`,`subject_type`),
  CONSTRAINT `fk_line_identity_revocation_canonical_publication` FOREIGN KEY (`canonical_default_menu_publication_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_identity_revocation_publication` FOREIGN KEY (`default_menu_publication_id`) REFERENCES `line_rich_menu_publications` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_identity_revocation_role_binding` FOREIGN KEY (`line_user_id`, `subject_type`) REFERENCES `line_identity_role_bindings` (`line_user_id`, `subject_type`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_identity_revocation_publication_source` CHECK (((`default_menu_publication_id` is null) <> (`canonical_default_menu_publication_id` is null))),
  CONSTRAINT `chk_line_identity_revocation_version` CHECK (((`pending_binding_version` = (`requested_binding_version` + 1)) and ((`completed_binding_version` is null) or (`completed_binding_version` = (`pending_binding_version` + 1)))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_role_binding_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_type` enum('customer','staff','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('claim_submitted','bound','revocation_requested','revoked','rebound','legacy_imported') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_identity_role_event_idempotency` (`idempotency_key`),
  KEY `idx_line_identity_role_event_stream` (`line_user_id`,`subject_type`,`id`),
  CONSTRAINT `fk_line_identity_role_event_binding` FOREIGN KEY (`line_user_id`, `subject_type`) REFERENCES `line_identity_role_bindings` (`line_user_id`, `subject_type`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_identity_role_event_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_identity_role_event_text` CHECK (((char_length(trim(`subject_reference`)) > 0) and (char_length(trim(`actor_id`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_line_identity_role_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_identity_role_bindings` (
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_type` enum('customer','staff','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `binding_status` enum('pending_review','bound','revocation_pending','revoked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `active_subject_key` varchar(400) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS ((case when (`binding_status` in (_utf8mb4'pending_review',_utf8mb4'bound',_utf8mb4'revocation_pending')) then concat(`subject_type`,_utf8mb4':',`subject_reference`) else NULL end)) STORED,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`line_user_id`,`subject_type`),
  UNIQUE KEY `uq_line_identity_role_active_subject` (`active_subject_key`),
  KEY `idx_line_identity_role_status` (`subject_type`,`binding_status`,`updated_at_utc`,`line_user_id`),
  CONSTRAINT `fk_line_identity_role_platform_user` FOREIGN KEY (`line_user_id`) REFERENCES `line_platform_users` (`line_user_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_identity_role_subject_reference` CHECK ((char_length(trim(`subject_reference`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_inbox_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_event_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `destination_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` enum('user','group','room') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `identity_source` enum('provider','fingerprint','legacy') COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_redelivery` tinyint(1) NOT NULL DEFAULT '0',
  `processing_status` enum('pending','processing','processed','ignored','retryable_failed','terminal_failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '5',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_acquired_at_utc` datetime(6) DEFAULT NULL,
  `lease_expires_at_utc` datetime(6) DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `received_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `processed_at_utc` datetime(6) DEFAULT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_inbox_event_identity` (`event_identity`),
  KEY `idx_line_inbox_due` (`processing_status`,`next_attempt_at_utc`,`received_at_utc`,`id`),
  KEY `idx_line_inbox_lease` (`processing_status`,`lease_expires_at_utc`),
  CONSTRAINT `chk_line_inbox_lease_pair` CHECK ((((`lease_owner` is null) and (`lease_acquired_at_utc` is null) and (`lease_expires_at_utc` is null)) or ((`lease_owner` is not null) and (`lease_acquired_at_utc` is not null) and (`lease_expires_at_utc` > `lease_acquired_at_utc`)))),
  CONSTRAINT `chk_line_inbox_payload_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_inbox_payload_object` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_media_records` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `provider_media_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` enum('user','group','room') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `content_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `size_bytes` bigint unsigned NOT NULL,
  `content_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `received_at_utc` datetime(6) NOT NULL,
  `media_category` enum('user_upload','identity_evidence','order_attachment','rich_menu_image','customer_service_attachment','unclassified') COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_reference` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `object_reference` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `legacy_media_asset_id` bigint DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_media_provider_id` (`provider_media_id`),
  UNIQUE KEY `uq_line_media_idempotency` (`idempotency_key`),
  KEY `idx_line_media_owner` (`media_category`,`owner_type`,`owner_reference`,`received_at_utc`),
  KEY `fk_line_media_legacy_asset` (`legacy_media_asset_id`),
  CONSTRAINT `fk_line_media_legacy_asset` FOREIGN KEY (`legacy_media_asset_id`) REFERENCES `media_assets` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_media_sha256` CHECK (regexp_like(`content_sha256`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_notification_decisions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `source_event_id` bigint unsigned NOT NULL,
  `rule_revision_id` bigint unsigned NOT NULL,
  `rule_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_selector` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_type` enum('user','group','room') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `recipient_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `decision_status` enum('suppressed','intent_created','cancelled_stale') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_snapshot` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_notification_decision` (`source_event_id`,`rule_revision_id`,`rule_id`,`recipient_selector`,`recipient_identity`),
  KEY `idx_line_notification_decision_source` (`source_event_id`,`id`),
  KEY `fk_line_notification_decision_revision` (`rule_revision_id`),
  CONSTRAINT `fk_line_notification_decision_revision` FOREIGN KEY (`rule_revision_id`) REFERENCES `line_configuration_revisions` (`id`),
  CONSTRAINT `fk_line_notification_decision_source` FOREIGN KEY (`source_event_id`) REFERENCES `line_notification_source_events` (`id`),
  CONSTRAINT `chk_line_notification_decision_snapshot` CHECK ((json_type(`decision_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_notification_intents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `decision_id` bigint unsigned NOT NULL,
  `occurrence_number` int unsigned NOT NULL DEFAULT '1',
  `delivery_task_id` bigint unsigned DEFAULT NULL,
  `template_revision_id` bigint unsigned NOT NULL,
  `template_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scheduled_at_utc` datetime(6) NOT NULL,
  `intent_status` enum('scheduled','cancelled','provider_accepted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'scheduled',
  `cancellation_reason` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `cancelled_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_notification_intent_decision_occurrence` (`decision_id`,`occurrence_number`),
  UNIQUE KEY `uq_line_notification_intent_delivery` (`delivery_task_id`),
  KEY `idx_line_notification_intent_status` (`intent_status`,`scheduled_at_utc`,`id`),
  KEY `fk_line_notification_intent_template` (`template_revision_id`),
  CONSTRAINT `fk_line_notification_intent_decision` FOREIGN KEY (`decision_id`) REFERENCES `line_notification_decisions` (`id`),
  CONSTRAINT `fk_line_notification_intent_delivery` FOREIGN KEY (`delivery_task_id`) REFERENCES `line_delivery_tasks` (`id`),
  CONSTRAINT `fk_line_notification_intent_template` FOREIGN KEY (`template_revision_id`) REFERENCES `line_configuration_revisions` (`id`),
  CONSTRAINT `chk_line_notification_intent_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_notification_intent_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_notification_source_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `source_domain` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_aggregate_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `historical_silent` tinyint(1) NOT NULL DEFAULT '0',
  `facts_snapshot` json NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_notification_source_identity` (`source_domain`,`event_code`,`source_event_identity`),
  KEY `idx_line_notification_source_due` (`event_code`,`historical_silent`,`occurred_at_utc`,`id`),
  CONSTRAINT `chk_line_notification_source_facts` CHECK ((json_type(`facts_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_order_group_binding_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('bound','replaced','released','legacy_imported') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_group_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resulting_group_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `binding_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_order_group_event_idempotency` (`idempotency_key`),
  KEY `idx_line_order_group_event_case` (`case_no`,`id`),
  CONSTRAINT `fk_line_order_group_event_binding` FOREIGN KEY (`case_no`) REFERENCES `line_order_group_bindings` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_order_group_event_fingerprint` CHECK (regexp_like(`binding_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_order_group_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_order_group_bindings` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `group_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `binding_status` enum('unbound','bound','inviting','active','attention','replaced','released') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unbound',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `last_invitation_at_utc` datetime(6) DEFAULT NULL,
  `activated_at_utc` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `invitation_url` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`case_no`),
  UNIQUE KEY `uq_line_order_group_id` (`group_id`),
  CONSTRAINT `fk_line_order_group_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_order_group_status` CHECK ((((`binding_status` = _utf8mb4'unbound') and (`group_id` is null)) or ((`binding_status` <> _utf8mb4'unbound') and (`group_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_order_group_participants` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `participant_type` enum('customer','staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `invitation_status` enum('pending','sent','joined','left','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `joined_at_utc` datetime(6) DEFAULT NULL,
  `left_at_utc` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_order_group_participant` (`case_no`,`participant_type`,`line_user_id`),
  KEY `idx_line_order_group_participant_user` (`line_user_id`,`case_no`),
  CONSTRAINT `fk_line_order_group_participant_binding` FOREIGN KEY (`case_no`) REFERENCES `line_order_group_bindings` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_order_group_runtime_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('invitation_relayed','member_joined','member_left','group_left','attention_required') COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `invitation_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_order_group_runtime_idempotency` (`idempotency_key`),
  KEY `idx_line_order_group_runtime_case` (`case_no`,`occurred_at_utc`,`id`),
  CONSTRAINT `fk_line_order_group_runtime_binding` FOREIGN KEY (`case_no`) REFERENCES `line_order_group_bindings` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_order_group_invitation_fingerprint` CHECK (((`invitation_fingerprint` is null) or regexp_like(`invitation_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_platform_users` (
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `friend_status` enum('unknown','active','blocked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `first_followed_at_utc` datetime(6) DEFAULT NULL,
  `last_followed_at_utc` datetime(6) DEFAULT NULL,
  `blocked_at_utc` datetime(6) DEFAULT NULL,
  `last_event_at_utc` datetime(6) DEFAULT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `selected_identity_role` enum('customer','staff') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`line_user_id`),
  KEY `idx_line_platform_friend_state` (`friend_status`,`last_event_at_utc`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_review_decision_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `review_request_id` bigint unsigned NOT NULL,
  `before_status` enum('pending','approved','rejected','cancelled','expired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('approved','rejected','cancelled','expired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_review_decision_idempotency` (`idempotency_key`),
  KEY `idx_line_review_decision_request` (`review_request_id`,`id`),
  CONSTRAINT `fk_line_review_decision_request` FOREIGN KEY (`review_request_id`) REFERENCES `line_review_requests` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_review_decision_fingerprint` CHECK (regexp_like(`decision_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_review_decision_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_review_requests` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `review_type` enum('client_rebind','staff_verification','admin_binding') COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_type` enum('customer','staff','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `subject_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` enum('pending','approved','rejected','cancelled','expired') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `identity_flow_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `assigned_admin_id` bigint DEFAULT NULL,
  `assigned_at_utc` datetime(6) DEFAULT NULL,
  `due_at_utc` datetime(6) DEFAULT NULL,
  `reassignment_count` int unsigned NOT NULL DEFAULT '0',
  `reviewed_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `decision_reason` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reviewed_at_utc` datetime(6) DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_review_identity_flow` (`identity_flow_id`),
  UNIQUE KEY `uq_line_review_request_idempotency` (`request_idempotency_key`),
  KEY `idx_line_review_queue` (`review_status`,`review_type`,`created_at_utc`,`id`),
  KEY `idx_line_review_assignee` (`assigned_admin_id`,`review_status`,`due_at_utc`),
  CONSTRAINT `fk_line_review_assignee` FOREIGN KEY (`assigned_admin_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_review_identity_flow` FOREIGN KEY (`identity_flow_id`) REFERENCES `line_identity_flows` (`flow_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_review_evidence` CHECK ((json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_line_review_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publication_cleanup_anomalies` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `publication_id` bigint unsigned NOT NULL,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_rich_menu_cleanup_anomaly_idempotency` (`idempotency_key`),
  KEY `idx_line_rich_menu_cleanup_anomaly_publication` (`publication_id`,`id`),
  CONSTRAINT `fk_line_rich_menu_cleanup_anomaly_publication` FOREIGN KEY (`publication_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_rich_menu_cleanup_anomaly_error` CHECK ((char_length(trim(`error_code`)) > 0)),
  CONSTRAINT `chk_line_rich_menu_cleanup_anomaly_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publication_step_acknowledgements` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `publication_id` bigint unsigned NOT NULL,
  `step_name` enum('create','upload','link','switch','cleanup') COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `acknowledged_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_rich_menu_step_ack` (`publication_id`,`step_name`),
  UNIQUE KEY `uq_line_rich_menu_step_ack_idempotency` (`idempotency_key`),
  KEY `idx_line_rich_menu_step_ack_publication` (`publication_id`,`id`),
  CONSTRAINT `fk_line_rich_menu_step_ack_publication` FOREIGN KEY (`publication_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_rich_menu_step_ack_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_rich_menu_step_ack_provider_id` CHECK ((char_length(trim(`provider_menu_id`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publication_step_attempt_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `publication_id` bigint unsigned NOT NULL,
  `step_name` enum('create','upload','link','switch','cleanup') COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempt_number` int unsigned NOT NULL,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outcome` enum('success','rate_limited','rejected','unavailable','timeout','lost_ack') COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `attempted_at_utc` datetime(6) NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_rich_menu_step_attempt` (`publication_id`,`step_name`,`attempt_number`),
  UNIQUE KEY `uq_line_rich_menu_step_attempt_idempotency` (`idempotency_key`),
  KEY `idx_line_rich_menu_step_attempt_publication` (`publication_id`,`step_name`,`attempt_number`),
  CONSTRAINT `fk_line_rich_menu_step_attempt_publication` FOREIGN KEY (`publication_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_rich_menu_step_attempt_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_rich_menu_step_attempt_number` CHECK ((`attempt_number` > 0)),
  CONSTRAINT `chk_line_rich_menu_step_attempt_outcome` CHECK ((((`outcome` = _utf8mb4'success') and (`provider_menu_id` is not null) and (char_length(trim(`provider_menu_id`)) > 0) and (`error_code` is null)) or ((`outcome` <> _utf8mb4'success') and (`provider_menu_id` is null) and (`error_code` is not null) and (char_length(trim(`error_code`)) > 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publication_step_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `publication_id` bigint unsigned NOT NULL,
  `step_name` enum('create','upload','switch','cleanup') COLLATE utf8mb4_unicode_ci NOT NULL,
  `provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_rich_menu_step` (`publication_id`,`step_name`),
  UNIQUE KEY `uq_line_rich_menu_step_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_line_rich_menu_step_publication` FOREIGN KEY (`publication_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publication_tasks` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `menu_definition_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `configuration_revision` bigint unsigned NOT NULL,
  `operation` enum('publish','rollback','delete') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'publish',
  `publication_status` enum('draft','queued','publishing','published','publish_retryable_failed','failed','rollback_queued','delete_queued','rollback_retryable_failed','delete_retryable_failed','rolled_back','deleted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_snapshot` json NOT NULL,
  `image_object_reference` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_provider_menu_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `requested_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `max_attempts` int unsigned NOT NULL DEFAULT '3',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `lease_owner` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at_utc` datetime(6) DEFAULT NULL,
  `error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_rich_menu_publication_idempotency` (`idempotency_key`),
  KEY `idx_line_rich_menu_publication_due` (`publication_status`,`next_attempt_at_utc`,`id`),
  KEY `idx_line_rich_menu_definition` (`menu_definition_id`,`configuration_revision`,`id`),
  CONSTRAINT `chk_line_rich_menu_definition` CHECK ((json_type(`definition_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `menu_config_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `audience_role` enum('customer','staff','union_staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_revision` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_snapshot` json NOT NULL,
  `status` enum('pending','processing','published','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `line_rich_menu_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_line_rich_menu_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `image_asset_id` bigint DEFAULT NULL,
  `requested_by_admin_user_id` bigint DEFAULT NULL,
  `retry_count` int NOT NULL DEFAULT '0',
  `max_retries` int NOT NULL DEFAULT '3',
  `next_retry_at` datetime DEFAULT NULL,
  `processing_started_at` datetime DEFAULT NULL,
  `is_current` tinyint(1) NOT NULL DEFAULT '0',
  `error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL,
  `published_at` datetime DEFAULT NULL,
  `failed_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rich_menu_publish_due` (`status`,`next_retry_at`,`id`),
  KEY `idx_rich_menu_current` (`menu_config_id`,`is_current`,`published_at`),
  KEY `idx_rich_menu_role` (`audience_role`,`status`,`published_at`),
  KEY `fk_rich_menu_publish_asset` (`image_asset_id`),
  KEY `fk_rich_menu_publish_admin` (`requested_by_admin_user_id`),
  CONSTRAINT `fk_rich_menu_publish_admin` FOREIGN KEY (`requested_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_rich_menu_publish_asset` FOREIGN KEY (`image_asset_id`) REFERENCES `media_assets` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_rich_menu_publish_previews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `menu_config_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_revision` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `previewed_by_admin_user_id` bigint NOT NULL,
  `publication_id` bigint DEFAULT NULL,
  `canonical_publication_task_id` bigint unsigned DEFAULT NULL,
  `previewed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `confirmed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_menu_preview_snapshot` (`menu_config_id`,`config_revision`,`config_fingerprint`,`previewed_by_admin_user_id`),
  KEY `idx_line_menu_preview_apply` (`menu_config_id`,`previewed_by_admin_user_id`,`publication_id`),
  KEY `fk_line_menu_preview_admin` (`previewed_by_admin_user_id`),
  KEY `fk_line_menu_preview_publication` (`publication_id`),
  KEY `idx_line_menu_preview_canonical_task` (`canonical_publication_task_id`),
  CONSTRAINT `fk_line_menu_preview_admin` FOREIGN KEY (`previewed_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_line_menu_preview_canonical_task` FOREIGN KEY (`canonical_publication_task_id`) REFERENCES `line_rich_menu_publication_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_line_menu_preview_publication` FOREIGN KEY (`publication_id`) REFERENCES `line_rich_menu_publications` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_safe_review_link_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `link_id` bigint unsigned NOT NULL,
  `event_type` enum('issued','redeemed','expired','revoked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_status` enum('issued','redeemed','expired','revoked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_payload` json NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_safe_review_event_idempotency` (`idempotency_key`),
  KEY `idx_line_safe_review_event_link` (`link_id`,`id`),
  CONSTRAINT `fk_line_safe_review_event_link` FOREIGN KEY (`link_id`) REFERENCES `line_safe_review_links` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_safe_review_event_payload` CHECK ((json_type(`event_payload`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_safe_review_link_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `link_id` bigint unsigned NOT NULL,
  `intent_type` enum('safe_review_link_issued') COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_owner` enum('line_integration') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'line_integration',
  `intent_payload` json NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_safe_review_outbox_idempotency` (`idempotency_key`),
  KEY `idx_line_safe_review_outbox_link` (`link_id`,`id`),
  CONSTRAINT `fk_line_safe_review_outbox_link` FOREIGN KEY (`link_id`) REFERENCES `line_safe_review_links` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_safe_review_outbox_payload` CHECK ((json_type(`intent_payload`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_safe_review_link_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `link_id` bigint unsigned NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outcome` enum('issued','redeemed','expired','revoked','rejected') COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`idempotency_key`),
  KEY `fk_line_safe_review_receipt_link` (`link_id`),
  CONSTRAINT `fk_line_safe_review_receipt_link` FOREIGN KEY (`link_id`) REFERENCES `line_safe_review_links` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_line_safe_review_receipt_digest` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_safe_review_receipt_result` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_safe_review_links` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `link_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `token_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `canonical_internal_target` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_version` bigint unsigned NOT NULL,
  `source_alert_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `allowed_actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `required_capability` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('issued','redeemed','expired','revoked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'issued',
  `issued_at_utc` datetime(6) NOT NULL,
  `expires_at_utc` datetime(6) NOT NULL,
  `redeemed_at_utc` datetime(6) DEFAULT NULL,
  `revoked_at_utc` datetime(6) DEFAULT NULL,
  `root_version` bigint unsigned NOT NULL DEFAULT '0',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_line_safe_review_link_id` (`link_id`),
  UNIQUE KEY `uq_line_safe_review_token_digest` (`token_digest`),
  UNIQUE KEY `uq_line_safe_review_idempotency` (`idempotency_key`),
  KEY `idx_line_safe_review_status_expiry` (`status`,`expires_at_utc`),
  KEY `idx_line_safe_review_alert` (`source_alert_identity`,`created_at_utc`),
  CONSTRAINT `chk_line_safe_review_link_digest` CHECK (regexp_like(`token_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_line_safe_review_link_expiry` CHECK ((`expires_at_utc` > `issued_at_utc`)),
  CONSTRAINT `chk_line_safe_review_link_identity` CHECK (((char_length(trim(`link_id`)) > 0) and (char_length(trim(`canonical_internal_target`)) > 0) and (char_length(trim(`source_alert_identity`)) > 0) and (char_length(trim(`allowed_actor_ref`)) > 0) and (char_length(trim(`required_capability`)) > 0))),
  CONSTRAINT `chk_line_safe_review_link_terminal_times` CHECK ((((`status` = _utf8mb4'issued') and (`redeemed_at_utc` is null) and (`revoked_at_utc` is null)) or ((`status` = _utf8mb4'redeemed') and (`redeemed_at_utc` is not null) and (`revoked_at_utc` is null)) or ((`status` = _utf8mb4'expired') and (`redeemed_at_utc` is null) and (`revoked_at_utc` is null)) or ((`status` = _utf8mb4'revoked') and (`revoked_at_utc` is not null) and (`redeemed_at_utc` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_task_attempts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `attempt_no` int NOT NULL,
  `outcome` enum('running','sent','retry_scheduled','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'running',
  `retryable` tinyint(1) DEFAULT NULL,
  `error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `line_request_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `started_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `finished_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_task_attempt_no` (`task_id`,`attempt_no`),
  KEY `idx_line_task_attempt_outcome_time` (`outcome`,`started_at`),
  CONSTRAINT `fk_line_task_attempt_task` FOREIGN KEY (`task_id`) REFERENCES `line_tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `to_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '接收訊息的 LINE 用戶唯一識別碼',
  `task_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'line_push' COMMENT 'line_push/line_push_message/rag_reply/rich_menu_link/rich_menu_unlink',
  `message_content` text COLLATE utf8mb4_unicode_ci COMMENT '文字推播內容',
  `payload_json` json DEFAULT NULL COMMENT '非純文字任務參數',
  `status` enum('pending','processing','sent','failed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `scheduled_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '預定發送時間；未指定時立即執行',
  `processing_started_at` datetime DEFAULT NULL,
  `retry_count` int NOT NULL DEFAULT '0',
  `max_retries` int NOT NULL DEFAULT '3',
  `next_retry_at` datetime DEFAULT NULL,
  `sent_at` datetime DEFAULT NULL,
  `failed_at` datetime DEFAULT NULL,
  `error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  `line_request_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_event_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_task_idempotency` (`idempotency_key`),
  KEY `idx_line_tasks_due` (`status`,`scheduled_at`,`next_retry_at`,`id`),
  KEY `idx_line_tasks_processing` (`status`,`processing_started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('customer','staff','union_staff') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'customer',
  `status` enum('active','blocked','unknown') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `followed_at` datetime DEFAULT NULL,
  `blocked_at` datetime DEFAULT NULL,
  `last_event_at` datetime DEFAULT NULL,
  `onboarding_started_at` datetime DEFAULT NULL,
  `onboarding_completed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_user_id` (`line_user_id`),
  KEY `idx_line_user_role_status` (`role`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_webhook_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `webhook_event_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_group_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_timestamp` bigint DEFAULT NULL,
  `is_redelivery` tinyint(1) NOT NULL DEFAULT '0',
  `processing_status` enum('received','processing','completed','failed','ignored') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'received',
  `payload_json` json NOT NULL,
  `received_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `processed_at` datetime DEFAULT NULL,
  `error_message` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_webhook_event_id` (`webhook_event_id`),
  KEY `idx_line_webhook_status` (`processing_status`,`received_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_webhook_security_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `signature_present` tinyint(1) NOT NULL,
  `verification_outcome` enum('verified','invalid_signature','invalid_payload','storage_failed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_count` int unsigned NOT NULL DEFAULT '0',
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_line_webhook_security_outcome` (`verification_outcome`,`occurred_at_utc`,`id`),
  KEY `idx_line_webhook_security_fingerprint` (`request_fingerprint`,`id`),
  CONSTRAINT `chk_line_webhook_security_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `line_worker_heartbeats` (
  `worker_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `process_id` int unsigned NOT NULL,
  `host_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `runtime_mode` enum('legacy','canonical','compatibility') COLLATE utf8mb4_unicode_ci NOT NULL,
  `component_status_snapshot` json NOT NULL,
  `last_cycle_at_utc` datetime(6) DEFAULT NULL,
  `heartbeat_at_utc` datetime(6) NOT NULL,
  `stopped_at_utc` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `last_error_message` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`worker_identity`),
  KEY `idx_line_worker_heartbeat` (`heartbeat_at_utc`,`stopped_at_utc`),
  CONSTRAINT `chk_line_worker_components` CHECK ((json_type(`component_status_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_coordination_apply_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` bigint unsigned NOT NULL,
  `criteria_snapshot_id` bigint unsigned NOT NULL,
  `package_lineage_id` bigint unsigned DEFAULT NULL,
  `command_name` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_version_tuple` json NOT NULL,
  `result_snapshot` json NOT NULL,
  `outcome_state` enum('applied','replayed','rematch_required','rejected_as_stale','conflict') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_receipt_id` (`receipt_id`),
  UNIQUE KEY `uq_matching_receipt_idempotency` (`idempotency_key`),
  KEY `idx_matching_receipt_event` (`event_id`,`id`),
  KEY `idx_matching_receipt_criteria` (`criteria_snapshot_id`,`id`),
  KEY `idx_matching_receipt_package` (`package_lineage_id`,`id`),
  KEY `idx_matching_receipt_outcome_time` (`outcome_state`,`created_at_utc`),
  CONSTRAINT `fk_matching_receipt_criteria` FOREIGN KEY (`criteria_snapshot_id`) REFERENCES `matching_coordination_criteria_snapshots` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_receipt_event` FOREIGN KEY (`event_id`) REFERENCES `matching_coordination_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_receipt_package` FOREIGN KEY (`package_lineage_id`) REFERENCES `matching_coordination_package_lineage` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and ((`preview_fingerprint` is null) or regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')))),
  CONSTRAINT `chk_matching_receipt_identity` CHECK (((char_length(trim(`receipt_id`)) > 0) and (char_length(trim(`command_name`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`actor_ref`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_matching_receipt_result` CHECK (((json_type(`result_snapshot`) = _utf8mb4'OBJECT') and (json_length(`result_snapshot`) > 0))),
  CONSTRAINT `chk_matching_receipt_sources` CHECK (((json_type(`source_version_tuple`) = _utf8mb4'ARRAY') and (json_length(`source_version_tuple`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_coordination_criteria_snapshots` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `snapshot_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `criteria_version` bigint unsigned NOT NULL,
  `criteria_snapshot` json NOT NULL,
  `source_version_tuple` json NOT NULL,
  `criteria_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_criteria_snapshot_id` (`snapshot_id`),
  UNIQUE KEY `uq_matching_criteria_case_version` (`case_no`,`criteria_version`),
  KEY `idx_matching_criteria_case_time` (`case_no`,`created_at_utc`),
  CONSTRAINT `chk_matching_criteria_actor` CHECK ((char_length(trim(`actor_ref`)) > 0)),
  CONSTRAINT `chk_matching_criteria_digest` CHECK (regexp_like(`criteria_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_criteria_identity` CHECK (((char_length(trim(`snapshot_id`)) > 0) and (char_length(trim(`case_no`)) > 0))),
  CONSTRAINT `chk_matching_criteria_payload` CHECK (((json_type(`criteria_snapshot`) = _utf8mb4'OBJECT') and (json_length(`criteria_snapshot`) > 0))),
  CONSTRAINT `chk_matching_criteria_sources` CHECK (((json_type(`source_version_tuple`) = _utf8mb4'ARRAY') and (json_length(`source_version_tuple`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_coordination_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `criteria_snapshot_id` bigint unsigned NOT NULL,
  `package_lineage_id` bigint unsigned DEFAULT NULL,
  `event_type` enum('criteria_snapshotted','package_proposed','candidate_contacted','caregiver_willingness','customer_decision','criteria_diff','rematch_required','conversion_requested','stale','superseded') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `event_payload` json NOT NULL,
  `source_version_tuple` json NOT NULL,
  `event_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_event_id` (`event_id`),
  UNIQUE KEY `uq_matching_event_idempotency` (`idempotency_key`),
  KEY `idx_matching_event_case_time` (`case_no`,`id`),
  KEY `idx_matching_event_criteria` (`criteria_snapshot_id`,`id`),
  KEY `idx_matching_event_package_time` (`package_lineage_id`,`id`),
  KEY `idx_matching_event_type_time` (`event_type`,`created_at_utc`),
  CONSTRAINT `fk_matching_event_criteria` FOREIGN KEY (`criteria_snapshot_id`) REFERENCES `matching_coordination_criteria_snapshots` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_event_package` FOREIGN KEY (`package_lineage_id`) REFERENCES `matching_coordination_package_lineage` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_event_actor` CHECK ((char_length(trim(`actor_ref`)) > 0)),
  CONSTRAINT `chk_matching_event_digest` CHECK (regexp_like(`event_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_event_identity` CHECK (((char_length(trim(`event_id`)) > 0) and (char_length(trim(`case_no`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_matching_event_payload` CHECK (((json_type(`event_payload`) = _utf8mb4'OBJECT') and (json_length(`event_payload`) > 0))),
  CONSTRAINT `chk_matching_event_sources` CHECK (((json_type(`source_version_tuple`) = _utf8mb4'ARRAY') and (json_length(`source_version_tuple`) > 0))),
  CONSTRAINT `chk_matching_event_versions` CHECK ((`resulting_version` >= `expected_version`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_coordination_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `reference_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_id` bigint unsigned NOT NULL,
  `receipt_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('line_matching_interaction','line_criteria_diff_resend','assignment_conversion_requested','rematch_requested','orders_terms_update_requested','line_bilateral_notification','line_client_decision','customer_service_ticket') COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_owner` enum('line_integration','assignment_workflow','orders_workflow','customer_service') COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_payload` json NOT NULL,
  `source_version_tuple` json NOT NULL,
  `reference_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_outbox_reference_id` (`reference_id`),
  UNIQUE KEY `uq_matching_outbox_idempotency` (`idempotency_key`),
  KEY `idx_matching_outbox_event` (`event_id`,`id`),
  KEY `idx_matching_outbox_receipt` (`receipt_id`,`id`),
  KEY `idx_matching_outbox_created_time` (`created_at_utc`,`id`),
  KEY `idx_matching_outbox_case` (`case_no`,`id`),
  CONSTRAINT `fk_matching_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `matching_coordination_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_outbox_receipt` FOREIGN KEY (`receipt_id`) REFERENCES `matching_coordination_apply_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_outbox_digest` CHECK (regexp_like(`reference_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_outbox_identity` CHECK (((char_length(trim(`reference_id`)) > 0) and (char_length(trim(`case_no`)) > 0) and (char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_matching_outbox_payload` CHECK (((json_type(`intent_payload`) = _utf8mb4'OBJECT') and (json_length(`intent_payload`) > 0))),
  CONSTRAINT `chk_matching_outbox_sources` CHECK (((json_type(`source_version_tuple`) = _utf8mb4'ARRAY') and (json_length(`source_version_tuple`) > 0))),
  CONSTRAINT `chk_matching_outbox_target` CHECK ((((`intent_type` in (_utf8mb4'line_matching_interaction',_utf8mb4'line_criteria_diff_resend',_utf8mb4'line_bilateral_notification',_utf8mb4'line_client_decision')) and (`target_owner` = _utf8mb4'line_integration')) or ((`intent_type` in (_utf8mb4'assignment_conversion_requested',_utf8mb4'rematch_requested')) and (`target_owner` = _utf8mb4'assignment_workflow')) or ((`intent_type` = _utf8mb4'orders_terms_update_requested') and (`target_owner` = _utf8mb4'orders_workflow')) or ((`intent_type` = _utf8mb4'customer_service_ticket') and (`target_owner` = _utf8mb4'customer_service'))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_coordination_package_lineage` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `package_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `criteria_snapshot_id` bigint unsigned NOT NULL,
  `parent_package_id` bigint unsigned DEFAULT NULL,
  `package_version` bigint unsigned NOT NULL,
  `lineage_kind` enum('initial','criteria_diff','rematch','alternative') COLLATE utf8mb4_unicode_ci NOT NULL,
  `package_state` enum('candidate_pool_open','proposed','awaiting_caregiver_willingness','awaiting_customer_decision','no_candidate','alternative_previewed','alternative_applied','no_candidate_terminal','accepted','declined','expired','rematch_required','superseded') COLLATE utf8mb4_unicode_ci NOT NULL,
  `package_snapshot` json NOT NULL,
  `source_version_tuple` json NOT NULL,
  `package_digest` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_ref` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_package_id` (`package_id`),
  UNIQUE KEY `uq_matching_package_case_version` (`case_no`,`package_version`),
  KEY `idx_matching_package_criteria` (`criteria_snapshot_id`,`id`),
  KEY `idx_matching_package_parent` (`parent_package_id`,`id`),
  KEY `idx_matching_package_state_time` (`package_state`,`created_at_utc`),
  CONSTRAINT `fk_matching_package_criteria` FOREIGN KEY (`criteria_snapshot_id`) REFERENCES `matching_coordination_criteria_snapshots` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_package_parent` FOREIGN KEY (`parent_package_id`) REFERENCES `matching_coordination_package_lineage` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_package_actor` CHECK ((char_length(trim(`actor_ref`)) > 0)),
  CONSTRAINT `chk_matching_package_digest` CHECK (regexp_like(`package_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_package_identity` CHECK (((char_length(trim(`package_id`)) > 0) and (char_length(trim(`case_no`)) > 0))),
  CONSTRAINT `chk_matching_package_parent` CHECK ((((`lineage_kind` = _utf8mb4'initial') and (`parent_package_id` is null)) or ((`lineage_kind` <> _utf8mb4'initial') and (`parent_package_id` is not null)))),
  CONSTRAINT `chk_matching_package_payload` CHECK (((json_type(`package_snapshot`) = _utf8mb4'OBJECT') and (json_length(`package_snapshot`) > 0))),
  CONSTRAINT `chk_matching_package_sources` CHECK (((json_type(`source_version_tuple`) = _utf8mb4'ARRAY') and (json_length(`source_version_tuple`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_line_interactions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_id` bigint NOT NULL,
  `segment_id` bigint DEFAULT NULL,
  `action_scope` enum('caregiver_willingness','customer_decision') COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `interaction_status` enum('active','consumed','expired','revoked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `expires_at_utc` datetime(6) NOT NULL,
  `consumed_at_utc` datetime(6) DEFAULT NULL,
  `consumed_by_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_line_interaction_token` (`token_hash`),
  KEY `idx_matching_line_interaction_plan` (`plan_id`,`action_scope`,`interaction_status`),
  KEY `fk_matching_line_interaction_segment` (`segment_id`),
  CONSTRAINT `fk_matching_line_interaction_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_line_interaction_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_line_interaction_target` CHECK ((((`action_scope` = _utf8mb4'caregiver_willingness') and (`segment_id` is not null)) or ((`action_scope` = _utf8mb4'customer_decision') and (`segment_id` is null)))),
  CONSTRAINT `chk_matching_line_interaction_token` CHECK (regexp_like(`token_hash`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_notification_intents` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL,
  `segment_id` bigint DEFAULT NULL,
  `notification_kind` enum('caregiver_info_1','caregiver_info_2','customer_profiles') COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `projection_status` enum('pending','projected','failed','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `delivery_task_id` bigint unsigned DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `projected_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_notification_idempotency` (`idempotency_key`),
  KEY `idx_matching_notification_plan` (`plan_id`,`created_at_utc`,`id`),
  KEY `idx_matching_notification_segment` (`segment_id`,`created_at_utc`,`id`),
  KEY `idx_matching_notification_delivery` (`delivery_task_id`),
  CONSTRAINT `fk_matching_notification_delivery` FOREIGN KEY (`delivery_task_id`) REFERENCES `line_delivery_tasks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_notification_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_notification_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_notification_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_notification_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_matching_notification_target` CHECK ((((`notification_kind` in (_utf8mb4'caregiver_info_1',_utf8mb4'caregiver_info_2')) and (`segment_id` is not null)) or ((`notification_kind` = _utf8mb4'customer_profiles') and (`segment_id` is null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_plan_create_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_id` bigint NOT NULL,
  `plan_version` int unsigned NOT NULL,
  `plan_status` enum('proposed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `as_of` date NOT NULL,
  `result_kind` enum('created','existing') COLLATE utf8mb4_unicode_ci NOT NULL,
  `ordered_segments` json NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_plan_create_receipt_key` (`idempotency_key`),
  KEY `idx_matching_plan_create_receipt_case` (`case_no`,`plan_id`),
  KEY `fk_matching_plan_create_receipt_plan` (`plan_id`),
  CONSTRAINT `fk_matching_plan_create_receipt_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_plan_create_receipt_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_plan_create_receipt_actor` CHECK ((char_length(trim(`actor`)) > 0)),
  CONSTRAINT `chk_matching_plan_create_receipt_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '對應 orders.case_no',
  `staff_id` int NOT NULL COMMENT '對應 staff.id',
  `caregiver_accepted` tinyint DEFAULT NULL COMMENT '是否接受媒合 (NULL: 待回覆, 1: 願意, 0: 無意願)',
  `sent_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '詢問發送時間',
  `replied_at` timestamp NULL DEFAULT NULL COMMENT '回覆時間',
  `sent_info_1_at` datetime DEFAULT NULL COMMENT '給服務人員的訂單資訊-1 發送時間',
  `sent_info_2_at` datetime DEFAULT NULL COMMENT '給服務人員的訂單資訊-2 發送時間',
  `sent_resume_at` datetime DEFAULT NULL COMMENT '履歷發送給客戶的時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_case_staff` (`case_no`,`staff_id`),
  KEY `staff_id` (`staff_id`),
  CONSTRAINT `fk_matching_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `matching_records_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_response_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL,
  `segment_id` bigint DEFAULT NULL,
  `response_type` enum('caregiver_willingness','customer_decision') COLLATE utf8mb4_unicode_ci NOT NULL,
  `response_value` enum('willing','unwilling','accepted','declined','contact_requested') COLLATE utf8mb4_unicode_ci NOT NULL,
  `response_source` enum('line','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_response_idempotency` (`idempotency_key`),
  KEY `idx_matching_response_plan` (`plan_id`,`occurred_at_utc`,`id`),
  KEY `idx_matching_response_segment` (`segment_id`,`occurred_at_utc`,`id`),
  CONSTRAINT `fk_matching_response_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_matching_response_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_matching_response_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_matching_response_target` CHECK ((((`response_type` = _utf8mb4'caregiver_willingness') and (`segment_id` is not null) and (`response_value` in (_utf8mb4'willing',_utf8mb4'unwilling'))) or ((`response_type` = _utf8mb4'customer_decision') and (`segment_id` is null) and (`response_value` in (_utf8mb4'accepted',_utf8mb4'declined',_utf8mb4'contact_requested')))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_schedule_confirmation_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `recipient_snapshot_id` bigint unsigned NOT NULL,
  `confirmation_value` enum('confirmed','rejected','manually_confirmed','manually_revoked') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` enum('line','admin') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_schedule_confirmation_key` (`idempotency_key`),
  KEY `fk_matching_schedule_confirmation_recipient` (`recipient_snapshot_id`),
  CONSTRAINT `fk_matching_schedule_confirmation_recipient` FOREIGN KEY (`recipient_snapshot_id`) REFERENCES `matching_schedule_recipient_snapshots` (`id`),
  CONSTRAINT `chk_matching_schedule_rejection_reason` CHECK (((`confirmation_value` <> _utf8mb4'rejected') or (char_length(trim(`reason`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_schedule_line_interactions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `recipient_snapshot_id` bigint unsigned NOT NULL,
  `token_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `interaction_status` enum('active','awaiting_rejection_reason','consumed','invalidated') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `consumed_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_schedule_line_token` (`token_hash`),
  UNIQUE KEY `uq_matching_schedule_recipient_interaction` (`recipient_snapshot_id`),
  CONSTRAINT `fk_matching_schedule_interaction_recipient` FOREIGN KEY (`recipient_snapshot_id`) REFERENCES `matching_schedule_recipient_snapshots` (`id`),
  CONSTRAINT `chk_matching_schedule_line_token` CHECK (regexp_like(`token_hash`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_schedule_recipient_snapshots` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `parent_snapshot_id` bigint unsigned NOT NULL,
  `audience_type` enum('customer','caregiver') COLLATE utf8mb4_unicode_ci NOT NULL,
  `recipient_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `segment_id` bigint DEFAULT NULL,
  `recipient_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload_snapshot` json NOT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `delivery_status` enum('pending','queued','sent','failed','blocked') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_schedule_recipient` (`parent_snapshot_id`,`recipient_key`),
  KEY `fk_matching_schedule_recipient_segment` (`segment_id`),
  CONSTRAINT `fk_matching_schedule_recipient_parent` FOREIGN KEY (`parent_snapshot_id`) REFERENCES `matching_schedule_snapshots` (`id`),
  CONSTRAINT `fk_matching_schedule_recipient_segment` FOREIGN KEY (`segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`),
  CONSTRAINT `chk_matching_schedule_recipient_target` CHECK ((((`audience_type` = _utf8mb4'customer') and (`segment_id` is null)) or ((`audience_type` = _utf8mb4'caregiver') and (`segment_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `matching_schedule_snapshots` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_id` bigint NOT NULL,
  `confirmed_version_id` bigint unsigned NOT NULL,
  `snapshot_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('draft','sent','invalidated') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `current_marker` tinyint DEFAULT NULL,
  `created_by_actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `invalidated_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_schedule_current` (`case_no`,`current_marker`),
  KEY `fk_matching_schedule_plan` (`plan_id`),
  KEY `fk_matching_schedule_version` (`confirmed_version_id`),
  CONSTRAINT `fk_matching_schedule_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`),
  CONSTRAINT `fk_matching_schedule_plan` FOREIGN KEY (`plan_id`) REFERENCES `caregiver_matching_plans` (`id`),
  CONSTRAINT `fk_matching_schedule_version` FOREIGN KEY (`confirmed_version_id`) REFERENCES `confirmed_service_date_versions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `media_assets` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `category` enum('rich_menu','line_user_upload','contract','other') COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `storage_provider` enum('local','nas','s3') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'local',
  `storage_key` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mime_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` bigint NOT NULL,
  `sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `width` int DEFAULT NULL,
  `height` int DEFAULT NULL,
  `created_by_admin_user_id` bigint DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_media_storage_key` (`storage_key`),
  KEY `idx_media_owner` (`category`,`owner_type`,`owner_id`,`deleted_at`),
  KEY `idx_media_sha256` (`sha256`),
  KEY `fk_media_created_by` (`created_by_admin_user_id`),
  CONSTRAINT `fk_media_created_by` FOREIGN KEY (`created_by_admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `non_citizen_case_sequences` (
  `roc_year` smallint unsigned NOT NULL,
  `next_sequence` int unsigned NOT NULL DEFAULT '1',
  PRIMARY KEY (`roc_year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_actual_start_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_start_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `reconfirmation_control_event_id` bigint unsigned DEFAULT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_start_date` date NOT NULL,
  `actual_end_date` date NOT NULL,
  `service_data_lock_formed` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_actual_start_receipt_key` (`idempotency_key`),
  KEY `fk_order_actual_start_receipt_order` (`case_no`),
  KEY `fk_order_actual_start_receipt_event` (`actual_start_event_id`,`case_no`),
  KEY `fk_order_actual_start_receipt_scheduling` (`scheduling_command_receipt_id`),
  KEY `fk_order_actual_start_receipt_lifecycle` (`lifecycle_event_id`,`case_no`),
  KEY `fk_order_actual_start_receipt_control` (`reconfirmation_control_event_id`),
  CONSTRAINT `fk_order_actual_start_receipt_control` FOREIGN KEY (`reconfirmation_control_event_id`) REFERENCES `order_lifecycle_control_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_actual_start_receipt_event` FOREIGN KEY (`actual_start_event_id`, `case_no`) REFERENCES `order_actual_start_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_actual_start_receipt_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_actual_start_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_actual_start_receipt_scheduling` FOREIGN KEY (`scheduling_command_receipt_id`) REFERENCES `scheduling_command_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_actual_start_receipt_dates` CHECK ((`actual_end_date` >= `actual_start_date`)),
  CONSTRAINT `chk_order_actual_start_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_actual_start_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_actual_start_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('confirmed','corrected','reconfirmed_after_delayed_settlement') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_actual_start_date` date DEFAULT NULL,
  `after_actual_start_date` date NOT NULL,
  `deposit_settlement_identity` char(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_actual_start_event_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_order_actual_start_event_case_identity` (`id`,`case_no`),
  KEY `fk_order_actual_start_event_order` (`case_no`),
  CONSTRAINT `fk_order_actual_start_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_actual_start_event_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_order_actual_start_event_settlement` CHECK (((`deposit_settlement_identity` is null) or regexp_like(`deposit_settlement_identity`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_actual_start_event_shape` CHECK ((((`event_type` = _utf8mb4'confirmed') and (`before_actual_start_date` is null) and (`deposit_settlement_identity` is null)) or ((`event_type` = _utf8mb4'corrected') and (`before_actual_start_date` is not null) and (`deposit_settlement_identity` is null)) or ((`event_type` = _utf8mb4'reconfirmed_after_delayed_settlement') and (`before_actual_start_date` is not null) and (`deposit_settlement_identity` is not null)))),
  CONSTRAINT `chk_order_actual_start_event_version` CHECK ((`resulting_order_version` = (`expected_order_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_auto_completion_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `completion_instant` datetime NOT NULL,
  `evaluation_at` datetime NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_auto_completion_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_order_auto_completion_lifecycle_event` (`lifecycle_event_id`),
  KEY `fk_order_auto_completion_receipt_order` (`case_no`),
  KEY `fk_order_auto_completion_receipt_lifecycle_event` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_auto_completion_receipt_lifecycle_event` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_auto_completion_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_auto_completion_receipt_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_order_auto_completion_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_cancellation_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint DEFAULT NULL,
  `cancellation_control_event_id` bigint unsigned NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned DEFAULT NULL,
  `scheduling_generation` int unsigned DEFAULT NULL,
  `client_finance_version` bigint unsigned DEFAULT NULL,
  `payroll_version` bigint unsigned DEFAULT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_end_date` date DEFAULT NULL,
  `official_service_day_count` int unsigned NOT NULL,
  `official_service_hours` int unsigned NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_cancellation_receipt_key` (`idempotency_key`),
  KEY `fk_order_cancellation_receipt_order` (`case_no`),
  KEY `fk_order_cancellation_receipt_event` (`cancellation_event_id`,`case_no`),
  KEY `fk_order_cancellation_receipt_scheduling` (`scheduling_command_receipt_id`),
  KEY `fk_order_cancellation_receipt_control` (`cancellation_control_event_id`),
  KEY `fk_order_cancellation_receipt_lifecycle` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_cancellation_receipt_control` FOREIGN KEY (`cancellation_control_event_id`) REFERENCES `order_lifecycle_control_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_cancellation_receipt_event` FOREIGN KEY (`cancellation_event_id`, `case_no`) REFERENCES `order_cancellation_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_cancellation_receipt_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_cancellation_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_cancellation_receipt_scheduling` FOREIGN KEY (`scheduling_command_receipt_id`) REFERENCES `scheduling_command_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_cancellation_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_cancellation_receipt_service` CHECK ((((`official_service_day_count` = 0) and (`official_service_hours` = 0) and (`actual_end_date` is null)) or ((`official_service_day_count` > 0) and (`official_service_hours` > 0) and (`actual_end_date` is not null)))),
  CONSTRAINT `chk_order_cancellation_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_cancellation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_date` date NOT NULL,
  `actual_end_date` date DEFAULT NULL,
  `official_service_day_count` int unsigned NOT NULL,
  `official_service_hours` int unsigned NOT NULL,
  `confirmed_service_days` json NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_cancellation_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_order_cancellation_event_owner` (`id`,`case_no`),
  KEY `fk_order_cancellation_event_order` (`case_no`),
  CONSTRAINT `fk_order_cancellation_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_cancellation_event_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_order_cancellation_event_service` CHECK ((((`official_service_day_count` = 0) and (`official_service_hours` = 0) and (`actual_end_date` is null)) or ((`official_service_day_count` > 0) and (`official_service_hours` > 0) and (`actual_end_date` is not null)))),
  CONSTRAINT `chk_order_cancellation_event_snapshot` CHECK ((json_type(`confirmed_service_days`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_order_cancellation_event_version` CHECK ((`resulting_order_version` = (`expected_order_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_contract_completion_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_event_id` bigint NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_contract_completion_receipt_key` (`idempotency_key`),
  KEY `fk_order_contract_completion_receipt_order` (`case_no`),
  KEY `fk_order_contract_completion_receipt_contract_event` (`contract_event_id`),
  KEY `fk_order_contract_completion_receipt_lifecycle` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_contract_completion_receipt_contract_event` FOREIGN KEY (`contract_event_id`) REFERENCES `order_contract_flow_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_contract_completion_receipt_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_contract_completion_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_contract_completion_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_contract_completion_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_order_contract_completion_receipt_text` CHECK (((char_length(trim(`contract_identity`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_contract_flow_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('contract_completed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_contract_completed_case` (`case_no`,`event_type`),
  UNIQUE KEY `uq_order_contract_event_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_order_contract_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_contract_event_text` CHECK (((char_length(trim(`contract_identity`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_lifecycle_control_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_type` enum('cancellation','actual_start_reconfirmation','human_hold') COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope` enum('order','enter_service','auto_complete') COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('activate','clear') COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_hash` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_snapshot` json NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_lifecycle_control_event_idempotency` (`case_no`,`idempotency_key`),
  UNIQUE KEY `uq_order_lifecycle_control_event_identity` (`id`,`case_no`,`control_type`,`control_key`),
  KEY `idx_order_lifecycle_control_event_case_type_time` (`case_no`,`control_type`,`control_key`,`created_at`),
  CONSTRAINT `fk_order_lifecycle_control_event_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_lifecycle_control_event_payload` CHECK ((regexp_like(`payload_hash`,_utf8mb4'^[0-9a-f]{64}$') and (json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_order_lifecycle_control_event_shape` CHECK ((((`control_type` = _utf8mb4'cancellation') and (`control_key` = _utf8mb4'order_cancelled') and (`scope` = _utf8mb4'order')) or ((`control_type` = _utf8mb4'actual_start_reconfirmation') and (`control_key` = _utf8mb4'actual_start_reconfirmation') and (`scope` = _utf8mb4'enter_service')) or ((`control_type` = _utf8mb4'human_hold') and (`scope` in (_utf8mb4'enter_service',_utf8mb4'auto_complete'))))),
  CONSTRAINT `chk_order_lifecycle_control_event_text` CHECK (((char_length(trim(`control_key`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_lifecycle_control_state` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_type` enum('cancellation','actual_start_reconfirmation','human_hold') COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope` enum('order','enter_service','auto_complete') COLLATE utf8mb4_unicode_ci NOT NULL,
  `state` enum('active','cleared') COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint unsigned NOT NULL,
  `release_policy` enum('manual','expires_at') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expires_at_utc` datetime(6) DEFAULT NULL,
  `confirmed_start_date` date DEFAULT NULL,
  `deposit_settlement_identity_hash` char(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`case_no`,`control_type`,`control_key`),
  KEY `idx_order_lifecycle_control_state_case_status_type` (`case_no`,`state`,`control_type`),
  KEY `fk_order_lifecycle_control_state_event` (`current_event_id`,`case_no`,`control_type`,`control_key`),
  CONSTRAINT `fk_order_lifecycle_control_state_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_lifecycle_control_state_event` FOREIGN KEY (`current_event_id`, `case_no`, `control_type`, `control_key`) REFERENCES `order_lifecycle_control_events` (`id`, `case_no`, `control_type`, `control_key`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_lifecycle_control_state_confirmation_hash` CHECK (((`deposit_settlement_identity_hash` is null) or regexp_like(`deposit_settlement_identity_hash`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_lifecycle_control_state_shape` CHECK ((((`control_type` = _utf8mb4'cancellation') and (`control_key` = _utf8mb4'order_cancelled') and (`scope` = _utf8mb4'order') and (`release_policy` is null) and (`expires_at_utc` is null) and (`confirmed_start_date` is null) and (`deposit_settlement_identity_hash` is null)) or ((`control_type` = _utf8mb4'actual_start_reconfirmation') and (`control_key` = _utf8mb4'actual_start_reconfirmation') and (`scope` = _utf8mb4'enter_service') and (`release_policy` is null) and (`expires_at_utc` is null) and (((`state` = _utf8mb4'active') and (`confirmed_start_date` is null) and (`deposit_settlement_identity_hash` is null)) or ((`state` = _utf8mb4'cleared') and (`confirmed_start_date` is not null) and (`deposit_settlement_identity_hash` is not null)))) or ((`control_type` = _utf8mb4'human_hold') and (`scope` in (_utf8mb4'enter_service',_utf8mb4'auto_complete')) and (`confirmed_start_date` is null) and (`deposit_settlement_identity_hash` is null) and (((`release_policy` = _utf8mb4'manual') and (`expires_at_utc` is null)) or ((`release_policy` = _utf8mb4'expires_at') and (`expires_at_utc` is not null)))))),
  CONSTRAINT `chk_order_lifecycle_control_state_text` CHECK (((char_length(trim(`control_key`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`changed_by`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_lifecycle_state_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬訂單（對應 orders.case_no）',
  `trigger_event` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '觸發本次狀態評估的事件名稱',
  `before_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '狀態評估前的 canonical 訂單狀態',
  `after_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '狀態評估後的 canonical 訂單狀態；維持或阻擋時可與 before_status 相同',
  `actor` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '觸發事件的操作者或系統身分',
  `business_date` date NOT NULL COMMENT '狀態評估採用的業務日期',
  `expected_version` bigint unsigned NOT NULL COMMENT '呼叫端進行樂觀鎖定時讀取的訂單版本',
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '同一訂單內唯一的呼叫端冪等鍵',
  `facts_snapshot` json NOT NULL COMMENT '狀態評估當下的權威事實與決策摘要',
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '事件建立時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_lifecycle_state_event_idempotency` (`case_no`,`idempotency_key`),
  UNIQUE KEY `uq_order_lifecycle_state_event_case_identity` (`id`,`case_no`),
  KEY `idx_order_lifecycle_state_event_case_time` (`case_no`,`created_at`),
  CONSTRAINT `fk_order_lifecycle_state_event_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_lifecycle_state_event_after_status` CHECK ((`after_status` in (_utf8mb4'待補件',_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中',_utf8mb4'訂單完成',_utf8mb4'訂單取消',_utf8mb4'歷史訂單－未服務',_utf8mb4'歷史訂單－服務中',_utf8mb4'歷史訂單－服務完成',_utf8mb4'歷史訂單－帳務完成'))),
  CONSTRAINT `chk_order_lifecycle_state_event_before_status` CHECK ((`before_status` in (_utf8mb4'待補件',_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中',_utf8mb4'訂單完成',_utf8mb4'訂單取消',_utf8mb4'歷史訂單－未服務',_utf8mb4'歷史訂單－服務中',_utf8mb4'歷史訂單－服務完成',_utf8mb4'歷史訂單－帳務完成'))),
  CONSTRAINT `chk_order_lifecycle_state_event_facts_snapshot` CHECK ((json_type(`facts_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_order_lifecycle_state_event_required_text` CHECK (((char_length(trim(`trigger_event`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_reopen_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reopen_event_id` bigint NOT NULL,
  `cancellation_control_event_id` bigint unsigned NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `requires_fresh_scheduling_preview` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_reopen_receipt_key` (`idempotency_key`),
  KEY `fk_order_reopen_receipt_order` (`case_no`),
  KEY `fk_order_reopen_receipt_event` (`reopen_event_id`,`case_no`),
  KEY `fk_order_reopen_receipt_control` (`cancellation_control_event_id`),
  KEY `fk_order_reopen_receipt_lifecycle` (`lifecycle_event_id`,`case_no`),
  KEY `fk_order_reopen_receipt_cancellation` (`cancellation_event_id`,`case_no`),
  CONSTRAINT `fk_order_reopen_receipt_cancellation` FOREIGN KEY (`cancellation_event_id`, `case_no`) REFERENCES `order_cancellation_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_reopen_receipt_control` FOREIGN KEY (`cancellation_control_event_id`) REFERENCES `order_lifecycle_control_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_reopen_receipt_event` FOREIGN KEY (`reopen_event_id`, `case_no`) REFERENCES `order_reopen_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_reopen_receipt_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_reopen_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_reopen_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_reopen_receipt_result` CHECK (((`lifecycle_status` in (_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中')) and (`requires_fresh_scheduling_preview` = 1) and (json_type(`result_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_reopen_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `before_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_reopen_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_order_reopen_event_owner` (`id`,`case_no`),
  KEY `idx_order_reopen_cancellation` (`cancellation_event_id`,`case_no`),
  KEY `fk_order_reopen_event_order` (`case_no`),
  CONSTRAINT `fk_order_reopen_event_cancellation` FOREIGN KEY (`cancellation_event_id`, `case_no`) REFERENCES `order_cancellation_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_reopen_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_reopen_event_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_order_reopen_event_status` CHECK (((`before_status` = _utf8mb4'訂單取消') and (`after_status` in (_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中')))),
  CONSTRAINT `chk_order_reopen_event_text` CHECK (((char_length(trim(`idempotency_key`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_order_reopen_event_version` CHECK ((`resulting_order_version` = (`expected_order_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_service_data_locks` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `client_settlement_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  KEY `fk_order_service_data_lock_lifecycle_event` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_service_data_lock_lifecycle_event` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_service_data_lock_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_service_data_lock_actor` CHECK ((char_length(trim(`created_by`)) > 0)),
  CONSTRAINT `chk_order_service_data_lock_fingerprint` CHECK (regexp_like(`client_settlement_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_terms_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_terms_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint DEFAULT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `client_finance_version` bigint unsigned DEFAULT NULL,
  `payroll_version` bigint unsigned DEFAULT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_data_lock_formed` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_terms_receipt_key` (`idempotency_key`),
  KEY `fk_order_terms_receipt_order` (`case_no`),
  KEY `fk_order_terms_receipt_event` (`order_terms_event_id`),
  KEY `fk_order_terms_receipt_scheduling` (`scheduling_command_receipt_id`),
  KEY `fk_order_terms_receipt_lifecycle` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_terms_receipt_event` FOREIGN KEY (`order_terms_event_id`) REFERENCES `order_terms_change_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_terms_receipt_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_terms_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_terms_receipt_scheduling` FOREIGN KEY (`scheduling_command_receipt_id`) REFERENCES `scheduling_command_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_terms_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_order_terms_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `order_terms_change_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_terms` json NOT NULL,
  `after_terms` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_terms_change_idempotency` (`idempotency_key`),
  KEY `fk_order_terms_change_order` (`case_no`),
  CONSTRAINT `fk_order_terms_change_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_terms_change_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_order_terms_change_snapshots` CHECK (((json_type(`before_terms`) = _utf8mb4'OBJECT') and (json_type(`after_terms`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_order_terms_change_version` CHECK ((`resulting_order_version` = (`expected_order_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `orders` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '案件唯一識別碼；對應 clients.case_no',
  `client_id` int NOT NULL COMMENT '對應 clients.id',
  `staff_id` int DEFAULT NULL COMMENT '對應 staff.id (可為 NULL，代表尚未配對成功)',
  `status` enum('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消','歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成','歷史訂單－帳務完成') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '洽談中',
  `lifecycle_version` bigint unsigned NOT NULL DEFAULT '0' COMMENT 'ORD-01 aggregate revision；每個非 replay command 恰遞增一次',
  `cancel_reason` text COLLATE utf8mb4_unicode_ci COMMENT '當狀態變更為 訂單取消 時的取消原因說明',
  `line_group_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '三方服務 LINE 群組 ID',
  `actual_start_date` date DEFAULT NULL COMMENT '實際生產服務開始日',
  `actual_end_date` date DEFAULT NULL COMMENT '實際生產服務結束日',
  `staff_payment_due_date` date DEFAULT NULL,
  `service_start_time` time DEFAULT NULL COMMENT '案件統一每日服務開始時間；既有案件待明確補登',
  `service_end_time` time DEFAULT NULL COMMENT '案件統一每日服務結束時間；既有案件待明確補登',
  `service_end_day_offset` tinyint unsigned DEFAULT NULL COMMENT '0=服務日當日結束，1=次日結束；不得由時間大小推測',
  `contract_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '訂單契約識別；不得綁定特定簽署平台',
  `service_days` int DEFAULT '0' COMMENT '服務天數 (N)',
  `service_hours_per_day` decimal(4,1) DEFAULT '0.0' COMMENT '每日服務時數 (J)，以 0.5 小時為單位',
  `floor_fee` decimal(10,2) DEFAULT '0.00' COMMENT '樓層費用 (O)',
  `deposit_date` date DEFAULT NULL COMMENT '訂金收取日期',
  `deposit_service_days` int DEFAULT NULL COMMENT '訂金服務天數；NULL 表示歷史案件待人工補登',
  `start_date` date DEFAULT NULL COMMENT '預計/實際服務開始日 (AK)',
  `end_date` date DEFAULT NULL COMMENT '預計/實際服務結束日 (AL)',
  `custom_rest_dates` json DEFAULT NULL COMMENT '排定/自訂休假日期 JSON 陣列 (如 ["2026-07-05", "2026-07-12"])',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `requires_cooking` tinyint(1) DEFAULT NULL COMMENT '是否需要月嫂下廚；NULL 只允許 legacy/待人工補正',
  `pricing_policy_id` bigint DEFAULT NULL,
  `pricing_override_event_id` bigint DEFAULT NULL,
  `pricing_revision` bigint NOT NULL DEFAULT '0',
  PRIMARY KEY (`case_no`),
  KEY `client_id` (`client_id`),
  KEY `staff_id` (`staff_id`),
  KEY `idx_order_status` (`status`),
  KEY `ix_orders_pricing_policy` (`pricing_policy_id`),
  KEY `ix_orders_pricing_override` (`pricing_override_event_id`),
  CONSTRAINT `fk_order_pricing_override` FOREIGN KEY (`pricing_override_event_id`) REFERENCES `case_pricing_events` (`id`),
  CONSTRAINT `fk_order_pricing_policy` FOREIGN KEY (`pricing_policy_id`) REFERENCES `accounting_pricing_policies` (`id`),
  CONSTRAINT `fk_orders_case_no` FOREIGN KEY (`case_no`) REFERENCES `clients` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE,
  CONSTRAINT `orders_ibfk_2` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE SET NULL,
  CONSTRAINT `chk_orders_deposit_service_days_nonnegative` CHECK (((`deposit_service_days` is null) or (`deposit_service_days` >= 0))),
  CONSTRAINT `chk_orders_requires_cooking` CHECK (((`requires_cooking` is null) or (`requires_cooking` in (0,1)))),
  CONSTRAINT `chk_orders_service_end_day_offset` CHECK (((`service_end_day_offset` is null) or (`service_end_day_offset` in (0,1)))),
  CONSTRAINT `chk_orders_service_hours_half_hour` CHECK (((`service_hours_per_day` >= 0) and (`service_hours_per_day` <= 24) and (((`service_hours_per_day` * 2) % 1) = 0))),
  CONSTRAINT `chk_orders_service_time_terms_complete` CHECK ((((`service_start_time` is null) and (`service_end_time` is null) and (`service_end_day_offset` is null)) or ((`service_start_time` is not null) and (`service_end_time` is not null) and (`service_end_day_offset` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `orders_domain_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('lifecycle_projection_changed','service_data_locked','anomaly_root_changed') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_orders_domain_outbox_intent` (`intent_key`),
  KEY `idx_orders_domain_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_orders_domain_outbox_order` (`case_no`),
  KEY `fk_orders_domain_outbox_lifecycle` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_orders_domain_outbox_lifecycle` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_orders_domain_outbox_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_orders_domain_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payment_migration_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `legacy_payment_id` int NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `legacy_caregiver_fee` decimal(12,2) NOT NULL,
  `legacy_caregiver_paid_at` date DEFAULT NULL,
  `reason` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` enum('pending','resolved','dismissed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `resolved_at` timestamp NULL DEFAULT NULL,
  `resolution_notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payment_migration_review_legacy` (`legacy_payment_id`),
  KEY `idx_payment_migration_review_case` (`case_no`,`review_status`),
  CONSTRAINT `fk_payment_migration_review_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_adjustment_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `adjustment_event_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `allocation_ordinal` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_adjustment_assignment` (`adjustment_event_id`,`assignment_id`),
  UNIQUE KEY `uq_payroll_adjustment_ordinal` (`adjustment_event_id`,`allocation_ordinal`),
  KEY `fk_payroll_adjustment_allocation_assignment` (`assignment_id`),
  CONSTRAINT `fk_payroll_adjustment_allocation_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_payroll_adjustment_allocation_event` FOREIGN KEY (`adjustment_event_id`) REFERENCES `payroll_adjustment_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_adjustment_allocation_nonzero` CHECK ((`amount_ntd` <> 0)),
  CONSTRAINT `chk_payroll_adjustment_allocation_ordinal` CHECK ((`allocation_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_adjustment_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_adjustment_identity` (`adjustment_identity`),
  UNIQUE KEY `uq_payroll_adjustment_idempotency` (`idempotency_key`),
  KEY `fk_payroll_adjustment_order` (`case_no`),
  CONSTRAINT `fk_payroll_adjustment_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_adjustment_nonzero` CHECK ((`amount_ntd` <> 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_payroll_version` bigint unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_receipt_idempotency` (`idempotency_key`),
  KEY `fk_payroll_receipt_order` (`case_no`),
  CONSTRAINT `fk_payroll_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_payroll_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_case_accounts` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  CONSTRAINT `fk_payroll_case_account_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('staff_obligation_changed','payroll_anomaly_required') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_outbox_intent` (`intent_key`),
  KEY `idx_payroll_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_payroll_outbox_order` (`case_no`),
  CONSTRAINT `fk_payroll_outbox_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_rate_policies` (
  `policy_version` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen','twins') COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `effective_from` date NOT NULL,
  `effective_until` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`policy_version`,`policy_kind`),
  CONSTRAINT `chk_payroll_rate_policy_amount` CHECK ((`hourly_rate_ntd` > 0)),
  CONSTRAINT `chk_payroll_rate_policy_interval` CHECK (((`effective_until` is null) or (`effective_until` >= `effective_from`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `payroll_special_pay_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `service_date` date NOT NULL,
  `event_type` enum('double_pay') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_special_pay_assignment_date` (`assignment_id`,`service_date`,`event_type`),
  UNIQUE KEY `uq_payroll_special_pay_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_payroll_special_pay_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `precontract_service_commitment_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `commitment_id` bigint NOT NULL,
  `matching_segment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `service_date` date NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_precontract_commitment_segment_date` (`commitment_id`,`matching_segment_id`,`service_date`),
  KEY `idx_precontract_commitment_staff_date` (`staff_id`,`service_date`),
  KEY `fk_precontract_commitment_day_segment` (`matching_segment_id`),
  CONSTRAINT `fk_precontract_commitment_day_header` FOREIGN KEY (`commitment_id`) REFERENCES `precontract_service_commitments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_precontract_commitment_day_segment` FOREIGN KEY (`matching_segment_id`) REFERENCES `caregiver_matching_plan_segments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_precontract_commitment_day_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `precontract_service_commitment_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `commitment_id` bigint NOT NULL,
  `event_type` enum('cancelled','converted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_precontract_commitment_event_key` (`event_key`),
  UNIQUE KEY `uq_precontract_commitment_terminal` (`commitment_id`),
  CONSTRAINT `fk_precontract_commitment_event_header` FOREIGN KEY (`commitment_id`) REFERENCES `precontract_service_commitments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_precontract_commitment_event_payload` CHECK (((json_type(`payload`) = _utf8mb4'OBJECT') and (char_length(trim(`event_key`)) > 0) and (char_length(trim(`actor`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `precontract_service_commitments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_plan_id` bigint NOT NULL,
  `commitment_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_snapshot_sha256` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_precontract_commitment_key` (`commitment_key`),
  UNIQUE KEY `uq_precontract_commitment_plan` (`matching_plan_id`),
  KEY `idx_precontract_commitment_case` (`case_no`,`created_at`),
  CONSTRAINT `fk_precontract_commitment_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_precontract_commitment_plan` FOREIGN KEY (`matching_plan_id`) REFERENCES `caregiver_matching_plans` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_precontract_commitment_nonempty` CHECK (((char_length(trim(`commitment_key`)) > 0) and (char_length(trim(`created_by`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `provisional_client_registrations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `active_line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('submitted','case_issued') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'submitted',
  `client_id` int DEFAULT NULL,
  `beclass_record_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `application_payload` json DEFAULT NULL,
  `application_version` bigint unsigned NOT NULL DEFAULT '1',
  `approved_by_actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `approved_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_provisional_registration_active_line_user` (`active_line_user_id`),
  KEY `idx_provisional_registration_line_status` (`line_user_id`,`status`),
  KEY `fk_provisional_registration_client` (`client_id`),
  KEY `fk_provisional_registration_beclass` (`beclass_record_id`),
  CONSTRAINT `fk_provisional_registration_beclass` FOREIGN KEY (`beclass_record_id`) REFERENCES `beclass_records` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_provisional_registration_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_provisional_registration_fingerprint` CHECK (regexp_like(`payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `provisional_registration_case_issue_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `registration_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `beclass_record_id` int NOT NULL,
  `case_import_event_id` bigint NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_provisional_case_issue_registration` (`registration_id`),
  UNIQUE KEY `uq_provisional_case_issue_case` (`case_no`),
  UNIQUE KEY `uq_provisional_case_issue_idempotency` (`idempotency_key`),
  KEY `fk_provisional_case_issue_client` (`client_id`),
  KEY `fk_provisional_case_issue_beclass` (`beclass_record_id`),
  KEY `fk_provisional_case_issue_import_event` (`case_import_event_id`),
  CONSTRAINT `fk_provisional_case_issue_beclass` FOREIGN KEY (`beclass_record_id`) REFERENCES `beclass_records` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_provisional_case_issue_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_provisional_case_issue_import_event` FOREIGN KEY (`case_import_event_id`) REFERENCES `case_import_events` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_provisional_case_issue_registration` FOREIGN KEY (`registration_id`) REFERENCES `provisional_client_registrations` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `provisional_registration_conflicts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `registration_id` bigint NOT NULL,
  `proposed_payload_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `proposed_payload` json NOT NULL,
  `status` enum('open','resolved') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_provisional_registration_conflict` (`registration_id`,`proposed_payload_fingerprint`),
  KEY `idx_provisional_registration_conflict_status` (`status`,`created_at`),
  CONSTRAINT `fk_provisional_registration_conflict_registration` FOREIGN KEY (`registration_id`) REFERENCES `provisional_client_registrations` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_provisional_registration_conflict_fingerprint` CHECK (regexp_like(`proposed_payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `runtime_health_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `check_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `component` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `transition_type` enum('opened','escalated','reminder','recovered','test') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_status` enum('healthy','warning','critical','unknown','maintenance') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resulting_status` enum('healthy','warning','critical','unknown','maintenance') COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `details_snapshot` json NOT NULL,
  `event_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_runtime_health_event_fingerprint` (`event_fingerprint`),
  KEY `idx_runtime_health_event_check` (`check_name`,`occurred_at_utc`,`id`),
  CONSTRAINT `chk_runtime_health_event_details` CHECK ((json_type(`details_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_runtime_health_event_fingerprint` CHECK (regexp_like(`event_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `runtime_health_status` (
  `check_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `component` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `health_status` enum('healthy','warning','critical','unknown','maintenance') COLLATE utf8mb4_unicode_ci NOT NULL,
  `raw_status` enum('healthy','warning','critical','unknown','maintenance') COLLATE utf8mb4_unicode_ci NOT NULL,
  `message` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `details_snapshot` json NOT NULL,
  `response_ms` int unsigned DEFAULT NULL,
  `consecutive_failures` int unsigned NOT NULL DEFAULT '0',
  `consecutive_successes` int unsigned NOT NULL DEFAULT '0',
  `checked_at_utc` datetime(6) NOT NULL,
  `last_success_at_utc` datetime(6) DEFAULT NULL,
  `status_changed_at_utc` datetime(6) NOT NULL,
  PRIMARY KEY (`check_name`),
  CONSTRAINT `chk_runtime_health_details` CHECK ((json_type(`details_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `runtime_service_heartbeats` (
  `service_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `instance_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `process_id` bigint DEFAULT NULL,
  `host_name` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_status` enum('starting','running','degraded','stopped') COLLATE utf8mb4_unicode_ci NOT NULL,
  `details_snapshot` json NOT NULL,
  `started_at_utc` datetime(6) NOT NULL,
  `last_seen_at_utc` datetime(6) NOT NULL,
  `stopped_at_utc` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`service_name`,`instance_id`),
  KEY `idx_runtime_service_latest` (`service_name`,`last_seen_at_utc`),
  CONSTRAINT `chk_runtime_service_details` CHECK ((json_type(`details_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_aggregates` (
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `generation_counter` int unsigned NOT NULL DEFAULT '0',
  `effective_generation_id` bigint DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  KEY `fk_scheduling_aggregate_effective_generation` (`effective_generation_id`,`case_no`),
  CONSTRAINT `fk_scheduling_aggregate_effective_generation` FOREIGN KEY (`effective_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_aggregate_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_bootstrap_review_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `issue_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `migration_identity` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_bootstrap_review_issue` (`case_no`,`issue_code`,`migration_identity`),
  CONSTRAINT `fk_scheduling_bootstrap_review_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_bootstrap_review_code` CHECK (regexp_like(`issue_code`,_utf8mb4'^SCHED-BOOT-[0-9]{3}$')),
  CONSTRAINT `chk_scheduling_bootstrap_review_evidence` CHECK ((json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_scheduling_bootstrap_review_migration` CHECK ((char_length(trim(`migration_identity`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_buffer_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `generation_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `buffer_date` date NOT NULL,
  `status` enum('active','released','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `active_marker` tinyint(1) DEFAULT '1',
  `released_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `released_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_buffer_assignment_date` (`assignment_id`,`buffer_date`),
  KEY `fk_scheduling_buffer_generation` (`generation_id`),
  KEY `fk_scheduling_buffer_assignment` (`assignment_id`,`generation_id`,`staff_id`),
  KEY `uq_scheduling_buffer_staff_date_active` (`staff_id`,`buffer_date`,`active_marker`),
  CONSTRAINT `fk_scheduling_buffer_assignment` FOREIGN KEY (`assignment_id`, `generation_id`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `generation_id`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_buffer_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_buffer_state` CHECK ((((`status` = _utf8mb4'active') and (`active_marker` = 1) and (`released_by` is null) and (`released_at` is null)) or ((`status` in (_utf8mb4'released',_utf8mb4'cancelled')) and (`active_marker` is null) and (char_length(trim(`released_by`)) > 0) and (`released_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_command_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `resulting_generation_id` bigint NOT NULL,
  `rebuild_event_id` bigint NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_command_receipt_key` (`idempotency_key`),
  KEY `fk_scheduling_receipt_order` (`case_no`),
  KEY `fk_scheduling_receipt_generation` (`resulting_generation_id`,`case_no`),
  KEY `fk_scheduling_receipt_rebuild` (`rebuild_event_id`),
  CONSTRAINT `fk_scheduling_receipt_generation` FOREIGN KEY (`resulting_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_receipt_rebuild` FOREIGN KEY (`rebuild_event_id`) REFERENCES `scheduling_rebuild_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_scheduling_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_scheduling_receipt_version` CHECK ((`resulting_scheduling_version` = (`expected_scheduling_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_effective_occupancy` (
  `staff_id` int NOT NULL,
  `occupancy_date` date NOT NULL,
  `generation_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `occupancy_type` enum('assignment_interval','buffer') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`staff_id`,`occupancy_date`,`occupancy_type`),
  KEY `idx_scheduling_effective_occupancy_generation` (`generation_id`),
  KEY `fk_scheduling_occupancy_assignment` (`assignment_id`,`generation_id`,`staff_id`),
  CONSTRAINT `fk_scheduling_occupancy_assignment` FOREIGN KEY (`assignment_id`, `generation_id`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `generation_id`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_occupancy_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_generations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `generation_number` int unsigned NOT NULL,
  `resulting_aggregate_version` bigint unsigned NOT NULL,
  `status` enum('preparing','effective','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `effective_marker` tinyint(1) DEFAULT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `change_reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `cancelled_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_generation_identity` (`id`,`case_no`),
  UNIQUE KEY `uq_scheduling_generation_number` (`case_no`,`generation_number`),
  UNIQUE KEY `uq_scheduling_generation_version` (`case_no`,`resulting_aggregate_version`),
  UNIQUE KEY `uq_scheduling_generation_effective` (`case_no`,`effective_marker`),
  CONSTRAINT `fk_scheduling_generation_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_generation_actor` CHECK ((char_length(trim(`created_by`)) > 0)),
  CONSTRAINT `chk_scheduling_generation_number` CHECK ((`generation_number` > 0)),
  CONSTRAINT `chk_scheduling_generation_reason` CHECK ((char_length(trim(`change_reason`)) > 0)),
  CONSTRAINT `chk_scheduling_generation_state` CHECK ((((`status` = _utf8mb4'effective') and (`effective_marker` = 1) and (`cancelled_at` is null)) or ((`status` = _utf8mb4'preparing') and (`effective_marker` is null) and (`cancelled_at` is null)) or ((`status` = _utf8mb4'cancelled') and (`effective_marker` is null) and (`cancelled_at` is not null)))),
  CONSTRAINT `chk_scheduling_generation_version` CHECK ((`resulting_aggregate_version` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_leave_occupancy_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_index` int unsigned NOT NULL,
  `outcome_id` bigint NOT NULL,
  `generation_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `occupancy_date` date NOT NULL,
  `status` enum('active','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `active_marker` tinyint(1) DEFAULT '1',
  `cancelled_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cancelled_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_leave_occupancy_outcome` (`outcome_id`),
  UNIQUE KEY `uq_scheduling_leave_occupancy_staff_date` (`staff_id`,`occupancy_date`,`active_marker`),
  KEY `idx_scheduling_leave_occupancy_generation` (`generation_id`,`active_marker`),
  KEY `fk_scheduling_leave_occupancy_outcome` (`outcome_id`,`batch_key`),
  CONSTRAINT `fk_scheduling_leave_occupancy_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_occupancy_outcome` FOREIGN KEY (`outcome_id`, `batch_key`) REFERENCES `scheduling_leave_substitution_outcomes` (`id`, `batch_key`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_occupancy_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_leave_occupancy_state` CHECK ((((`status` = _utf8mb4'active') and (`active_marker` = 1) and (`cancelled_by` is null) and (`cancelled_at` is null)) or ((`status` = _utf8mb4'cancelled') and (`active_marker` is null) and (char_length(trim(`cancelled_by`)) > 0) and (`cancelled_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_leave_substitution_batches` (
  `batch_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_assignment_id` bigint NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `item_count` int unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_snapshot` json NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_key`),
  KEY `idx_scheduling_leave_batch_case_time` (`case_no`,`created_at`),
  KEY `fk_scheduling_leave_batch_original_assignment` (`original_assignment_id`),
  CONSTRAINT `fk_scheduling_leave_batch_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_batch_original_assignment` FOREIGN KEY (`original_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_leave_batch_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_ascii'^[0-9a-f]{64}$') and regexp_like(`request_fingerprint`,_ascii'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_scheduling_leave_batch_identity` CHECK (((`item_count` >= 0) and (char_length(trim(`batch_key`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_leave_substitution_outcomes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_index` int unsigned NOT NULL,
  `event_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_assignment_id` bigint NOT NULL,
  `original_schedule_id` int NOT NULL,
  `original_staff_id` int NOT NULL,
  `original_work_date` date NOT NULL,
  `resolution_type` enum('defer_following_assignments','substitute') COLLATE utf8mb4_unicode_ci NOT NULL,
  `leave_occupancy_date` date NOT NULL,
  `resulting_assignment_id` bigint NOT NULL,
  `resulting_staff_id` int NOT NULL,
  `resulting_service_date` date NOT NULL,
  `is_double_pay` tinyint(1) NOT NULL DEFAULT '0',
  `result_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `outcome_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_leave_outcome_ordinal` (`batch_key`,`item_index`),
  UNIQUE KEY `uq_scheduling_leave_outcome_event_key` (`event_key`),
  UNIQUE KEY `uq_scheduling_leave_outcome_identity` (`id`,`batch_key`),
  KEY `fk_scheduling_leave_outcome_original_assignment` (`original_assignment_id`),
  KEY `fk_scheduling_leave_outcome_original_schedule` (`original_schedule_id`),
  KEY `fk_scheduling_leave_outcome_resulting_assignment` (`resulting_assignment_id`),
  CONSTRAINT `fk_scheduling_leave_outcome_batch` FOREIGN KEY (`batch_key`) REFERENCES `scheduling_leave_substitution_batches` (`batch_key`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_outcome_original_assignment` FOREIGN KEY (`original_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_outcome_original_schedule` FOREIGN KEY (`original_schedule_id`) REFERENCES `staff_schedule` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_outcome_resulting_assignment` FOREIGN KEY (`resulting_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_leave_outcome_result` CHECK ((regexp_like(`result_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (char_length(trim(`event_key`)) > 0) and (json_type(`outcome_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_leave_substitution_receipts` (
  `batch_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `resulting_generation_number` int unsigned NOT NULL,
  `expected_client_finance_version` bigint unsigned NOT NULL,
  `resulting_client_finance_version` bigint unsigned NOT NULL,
  `expected_payroll_version` bigint unsigned NOT NULL,
  `resulting_payroll_version` bigint unsigned NOT NULL,
  `scheduling_receipt_id` bigint NOT NULL,
  `outcome_event_ids` json NOT NULL,
  `result_snapshot` json NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_key`),
  KEY `fk_scheduling_leave_receipt_case` (`case_no`),
  KEY `fk_scheduling_leave_receipt_scheduling` (`scheduling_receipt_id`),
  CONSTRAINT `fk_scheduling_leave_receipt_batch` FOREIGN KEY (`batch_key`) REFERENCES `scheduling_leave_substitution_batches` (`batch_key`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_receipt_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_receipt_scheduling` FOREIGN KEY (`scheduling_receipt_id`) REFERENCES `scheduling_command_receipts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_leave_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_scheduling_leave_receipt_snapshots` CHECK (((json_type(`outcome_event_ids`) = _utf8mb4'ARRAY') and (json_type(`result_snapshot`) = _utf8mb4'OBJECT') and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_scheduling_leave_receipt_versions` CHECK (((`resulting_order_version` = (`expected_order_version` + 1)) and (`resulting_scheduling_version` = (`expected_scheduling_version` + 1)) and (`resulting_client_finance_version` = (`expected_client_finance_version` + 1)) and (`resulting_payroll_version` = (`expected_payroll_version` + 1))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_rebuild_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `previous_generation_id` bigint DEFAULT NULL,
  `new_generation_id` bigint NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_rebuild_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_scheduling_rebuild_generation` (`id`,`new_generation_id`),
  KEY `fk_scheduling_rebuild_order` (`case_no`),
  KEY `fk_scheduling_rebuild_previous_generation` (`previous_generation_id`,`case_no`),
  KEY `fk_scheduling_rebuild_new_generation` (`new_generation_id`,`case_no`),
  CONSTRAINT `fk_scheduling_rebuild_new_generation` FOREIGN KEY (`new_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_rebuild_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_rebuild_previous_generation` FOREIGN KEY (`previous_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_rebuild_fingerprint` CHECK (regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_scheduling_rebuild_version` CHECK ((`resulting_scheduling_version` = (`expected_scheduling_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_rebuild_lineage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `rebuild_event_id` bigint NOT NULL,
  `old_assignment_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `new_assignment_id` bigint NOT NULL,
  `new_generation_id` bigint NOT NULL,
  `lineage_ordinal` int unsigned NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_rebuild_lineage` (`rebuild_event_id`,`old_assignment_identity`,`new_assignment_id`),
  UNIQUE KEY `uq_scheduling_rebuild_lineage_ordinal` (`rebuild_event_id`,`lineage_ordinal`),
  KEY `fk_scheduling_rebuild_lineage_event` (`rebuild_event_id`,`new_generation_id`),
  KEY `fk_scheduling_rebuild_lineage_assignment` (`new_assignment_id`,`new_generation_id`),
  CONSTRAINT `fk_scheduling_rebuild_lineage_assignment` FOREIGN KEY (`new_assignment_id`, `new_generation_id`) REFERENCES `case_staff_assignments` (`id`, `generation_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_rebuild_lineage_event` FOREIGN KEY (`rebuild_event_id`, `new_generation_id`) REFERENCES `scheduling_rebuild_events` (`id`, `new_generation_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_rebuild_notification_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rebuild_event_id` bigint NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `delivery_status` enum('pending','processing','published','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `published_at_utc` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_rebuild_notification_outbox_event` (`rebuild_event_id`),
  UNIQUE KEY `uq_scheduling_rebuild_notification_outbox_intent` (`intent_key`),
  KEY `idx_scheduling_rebuild_notification_outbox_delivery` (`delivery_status`,`next_attempt_at_utc`,`id`),
  CONSTRAINT `fk_scheduling_rebuild_notification_outbox_event` FOREIGN KEY (`rebuild_event_id`) REFERENCES `scheduling_rebuild_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_rebuild_notification_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_before_replacement_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `replacement_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prior_replacement_event_id` bigint unsigned DEFAULT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scenario` enum('R-01','R-02','R-03','R-04','R-07') COLLATE utf8mb4_unicode_ci NOT NULL,
  `prior_generation_id` bigint NOT NULL,
  `replacement_generation_id` bigint NOT NULL,
  `prior_generation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `replacement_generation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prior_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_aggregate_version` bigint unsigned NOT NULL,
  `resulting_aggregate_version` bigint unsigned NOT NULL,
  `expected_generation_version` bigint unsigned NOT NULL,
  `resulting_generation_version` bigint unsigned NOT NULL,
  `expected_event_version` bigint unsigned NOT NULL,
  `resulting_event_version` bigint unsigned NOT NULL,
  `zero_service_proof_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `zero_service_proof_owner` enum('scheduling_official_service_projection') COLLATE utf8mb4_unicode_ci NOT NULL,
  `zero_service_proof_contract_version` smallint unsigned NOT NULL,
  `zero_service_source_projection_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `zero_service_source_projection_version` bigint unsigned NOT NULL,
  `zero_service_proof_version` bigint unsigned NOT NULL,
  `zero_service_proof_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `official_service_day_count` int unsigned NOT NULL,
  `replacement_reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason_evidence_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `capability_atom` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_before_replacement_event_identity` (`replacement_event_identity`),
  UNIQUE KEY `uq_service_before_replacement_event_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_service_before_replacement_event_generation` (`replacement_generation_id`),
  UNIQUE KEY `uq_service_before_replacement_event_owner_binding` (`id`,`case_no`),
  UNIQUE KEY `uq_service_before_replacement_event_successor_binding` (`id`,`case_no`,`replacement_generation_id`,`scenario`,`expected_generation_version`,`expected_event_version`),
  UNIQUE KEY `uq_service_before_replacement_event_version_binding` (`id`,`case_no`,`resulting_aggregate_version`,`resulting_generation_version`,`resulting_event_version`),
  UNIQUE KEY `uq_service_before_replacement_case_event_version` (`case_no`,`resulting_event_version`),
  UNIQUE KEY `uq_service_before_replacement_event_prior` (`prior_replacement_event_id`),
  KEY `idx_service_before_replacement_prior_event` (`prior_replacement_event_id`),
  KEY `idx_service_before_replacement_case_versions` (`case_no`,`resulting_aggregate_version`,`resulting_generation_version`,`id`),
  KEY `fk_service_before_replacement_prior_event` (`prior_replacement_event_id`,`case_no`,`expected_aggregate_version`,`expected_generation_version`,`expected_event_version`),
  KEY `fk_service_before_replacement_prior_generation` (`prior_generation_id`,`case_no`),
  KEY `fk_service_before_replacement_generation` (`replacement_generation_id`,`case_no`),
  CONSTRAINT `fk_service_before_replacement_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_generation` FOREIGN KEY (`replacement_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_prior_event` FOREIGN KEY (`prior_replacement_event_id`, `case_no`, `expected_aggregate_version`, `expected_generation_version`, `expected_event_version`) REFERENCES `scheduling_service_before_replacement_events` (`id`, `case_no`, `resulting_aggregate_version`, `resulting_generation_version`, `resulting_event_version`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_prior_generation` FOREIGN KEY (`prior_generation_id`, `case_no`) REFERENCES `scheduling_generations` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_service_before_replacement_digests` CHECK ((regexp_like(`zero_service_proof_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`reason_evidence_digest`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_service_before_replacement_distinct_generation` CHECK ((`replacement_generation_id` <> `prior_generation_id`)),
  CONSTRAINT `chk_service_before_replacement_strict_versions` CHECK (((`resulting_aggregate_version` > `expected_aggregate_version`) and (`resulting_generation_version` > `expected_generation_version`) and (`resulting_event_version` > `expected_event_version`))),
  CONSTRAINT `chk_service_before_replacement_text` CHECK (((char_length(trim(`replacement_event_identity`)) > 0) and (char_length(trim(`prior_generation_identity`)) > 0) and (char_length(trim(`replacement_generation_identity`)) > 0) and (char_length(trim(`prior_event_identity`)) > 0) and (char_length(trim(`zero_service_proof_identity`)) > 0) and (char_length(trim(`zero_service_source_projection_identity`)) > 0) and (char_length(trim(`replacement_reason`)) > 0) and (char_length(trim(`actor_id`)) > 0) and (char_length(trim(`capability_atom`)) > 0) and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`correlation_id`)) > 0))),
  CONSTRAINT `chk_service_before_replacement_zero_service` CHECK (((`zero_service_proof_contract_version` = 1) and (`zero_service_proof_version` > 0) and (`zero_service_source_projection_version` = `zero_service_proof_version`) and (`official_service_day_count` = 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_before_replacement_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `replacement_event_id` bigint unsigned NOT NULL,
  `receipt_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outbox_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('successor_projection_readback_requested') COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_owner` enum('orders_anomalies_projection') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_payload` json NOT NULL,
  `published_at` timestamp(6) NULL DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_before_replacement_outbox_event` (`replacement_event_id`),
  UNIQUE KEY `uq_service_before_replacement_outbox_receipt` (`receipt_id`),
  UNIQUE KEY `uq_service_before_replacement_outbox_identity` (`outbox_identity`),
  KEY `idx_service_before_replacement_outbox_pending` (`published_at`,`attempts`,`id`),
  KEY `fk_service_before_replacement_outbox_event` (`replacement_event_id`,`case_no`),
  KEY `fk_service_before_replacement_outbox_receipt` (`receipt_id`,`replacement_event_id`,`case_no`),
  CONSTRAINT `fk_service_before_replacement_outbox_event` FOREIGN KEY (`replacement_event_id`, `case_no`) REFERENCES `scheduling_service_before_replacement_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_outbox_receipt` FOREIGN KEY (`receipt_id`, `replacement_event_id`, `case_no`) REFERENCES `scheduling_service_before_replacement_receipts` (`id`, `replacement_event_id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_service_before_replacement_outbox_payload` CHECK ((json_type(`bounded_payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_service_before_replacement_outbox_text` CHECK ((char_length(trim(`outbox_identity`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_before_replacement_receipts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `receipt_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `replacement_event_id` bigint unsigned NOT NULL,
  `successor_binding_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `root_set_digest_contract` enum('sha256_newline_v1') COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `retained_root_set_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `retained_root_count` int unsigned NOT NULL,
  `superseded_root_set_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `superseded_root_count` int unsigned NOT NULL,
  `created_root_set_digest` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_root_count` int unsigned NOT NULL,
  `resulting_aggregate_version` bigint unsigned NOT NULL,
  `resulting_generation_version` bigint unsigned NOT NULL,
  `resulting_event_version` bigint unsigned NOT NULL,
  `outbox_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_state` enum('applied') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_before_replacement_receipt_identity` (`receipt_identity`),
  UNIQUE KEY `uq_service_before_replacement_receipt_event` (`replacement_event_id`),
  UNIQUE KEY `uq_service_before_replacement_receipt_successor` (`successor_binding_id`),
  UNIQUE KEY `uq_service_before_replacement_receipt_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_service_before_replacement_receipt_outbox` (`outbox_identity`),
  UNIQUE KEY `uq_service_before_replacement_receipt_binding` (`id`,`replacement_event_id`,`case_no`),
  KEY `fk_service_before_replacement_receipt_event` (`replacement_event_id`,`case_no`,`resulting_aggregate_version`,`resulting_generation_version`,`resulting_event_version`),
  KEY `fk_service_before_replacement_receipt_successor` (`successor_binding_id`,`replacement_event_id`,`case_no`),
  CONSTRAINT `fk_service_before_replacement_receipt_event` FOREIGN KEY (`replacement_event_id`, `case_no`, `resulting_aggregate_version`, `resulting_generation_version`, `resulting_event_version`) REFERENCES `scheduling_service_before_replacement_events` (`id`, `case_no`, `resulting_aggregate_version`, `resulting_generation_version`, `resulting_event_version`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_receipt_successor` FOREIGN KEY (`successor_binding_id`, `replacement_event_id`, `case_no`) REFERENCES `scheduling_service_before_replacement_successors` (`id`, `replacement_event_id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_service_before_replacement_receipt_digests` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`retained_root_set_digest`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`superseded_root_set_digest`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`created_root_set_digest`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_service_before_replacement_receipt_text` CHECK (((char_length(trim(`receipt_identity`)) > 0) and regexp_like(`idempotency_key`,_utf8mb4'^[a-z0-9][a-z0-9._:-]{0,190}$') and (char_length(trim(`outbox_identity`)) > 0))),
  CONSTRAINT `chk_service_before_replacement_receipt_versions` CHECK (((`resulting_aggregate_version` > 0) and (`resulting_generation_version` > 0) and (`resulting_event_version` > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_before_replacement_roots` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `replacement_event_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `root_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_domain` enum('scheduling','matching') COLLATE utf8mb4_unicode_ci NOT NULL,
  `root_kind` enum('candidate_binding','willingness','matching_plan','matching_segment','matching_reply','recipient_confirmation','waiting_lock','commitment','signback','recipient_binding','effective_generation','assignment','official_schedule','successor_round') COLLATE utf8mb4_unicode_ci NOT NULL,
  `disposition` enum('retained','superseded','created') COLLATE utf8mb4_unicode_ci NOT NULL,
  `canonical_ordinal` int unsigned NOT NULL,
  `owner_descriptor_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_descriptor_version` bigint unsigned NOT NULL,
  `owner_descriptor_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_before_replacement_root_identity` (`replacement_event_id`,`root_identity`),
  UNIQUE KEY `uq_service_before_replacement_root_ordinal` (`replacement_event_id`,`disposition`,`canonical_ordinal`),
  KEY `idx_service_before_replacement_root_case` (`case_no`,`disposition`,`root_kind`,`id`),
  KEY `fk_service_before_replacement_root_event` (`replacement_event_id`,`case_no`),
  CONSTRAINT `fk_service_before_replacement_root_event` FOREIGN KEY (`replacement_event_id`, `case_no`) REFERENCES `scheduling_service_before_replacement_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_service_before_replacement_root_descriptor` CHECK (((char_length(trim(`owner_descriptor_identity`)) > 0) and (`owner_descriptor_version` > 0) and regexp_like(`owner_descriptor_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_service_before_replacement_root_ordinal` CHECK ((`canonical_ordinal` > 0)),
  CONSTRAINT `chk_service_before_replacement_root_owner_kind` CHECK ((((`owner_domain` = _utf8mb4'matching') and (`root_kind` in (_utf8mb4'candidate_binding',_utf8mb4'willingness',_utf8mb4'matching_plan',_utf8mb4'matching_segment',_utf8mb4'matching_reply',_utf8mb4'recipient_confirmation',_utf8mb4'successor_round'))) or ((`owner_domain` = _utf8mb4'scheduling') and (`root_kind` in (_utf8mb4'waiting_lock',_utf8mb4'commitment',_utf8mb4'signback',_utf8mb4'recipient_binding',_utf8mb4'effective_generation',_utf8mb4'assignment',_utf8mb4'official_schedule'))))),
  CONSTRAINT `chk_service_before_replacement_root_text` CHECK (((char_length(trim(`root_identity`)) > 0) and (not(regexp_like(`root_identity`,_utf8mb4'[[:cntrl:]]')))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_before_replacement_successors` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `replacement_event_id` bigint unsigned NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `replacement_generation_id` bigint NOT NULL,
  `matching_package_lineage_id` bigint unsigned NOT NULL,
  `matching_event_id` bigint unsigned NOT NULL,
  `successor_package_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `successor_round_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `successor_matching_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scenario` enum('R-01','R-02','R-03','R-04','R-07') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_generation_version` bigint unsigned NOT NULL,
  `expected_event_version` bigint unsigned NOT NULL,
  `candidate_count` int unsigned NOT NULL,
  `zero_candidate_disposition` enum('blocked_no_candidate') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reuse_proof_variant` enum('not_reused','candidate_pool_reused') COLLATE utf8mb4_unicode_ci NOT NULL,
  `reuse_pool_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reuse_round_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reuse_coverage_version` bigint unsigned DEFAULT NULL,
  `reuse_availability_version` bigint unsigned DEFAULT NULL,
  `reuse_willingness_version` bigint unsigned DEFAULT NULL,
  `reuse_candidate_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reuse_accepted_candidate` tinyint(1) DEFAULT NULL,
  `reuse_proof_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `resume_step` enum('step_2','step_3','step_4') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_before_replacement_successor_event` (`replacement_event_id`),
  UNIQUE KEY `uq_service_before_replacement_successor_round` (`successor_round_identity`),
  UNIQUE KEY `uq_service_before_replacement_successor_binding` (`id`,`replacement_event_id`,`case_no`),
  KEY `idx_service_before_replacement_successor_package` (`matching_package_lineage_id`,`matching_event_id`),
  KEY `fk_service_before_replacement_successor_owner_event` (`replacement_event_id`,`case_no`,`replacement_generation_id`,`scenario`,`expected_generation_version`,`expected_event_version`),
  KEY `fk_service_before_replacement_successor_matching_event` (`matching_event_id`),
  CONSTRAINT `fk_service_before_replacement_successor_matching_event` FOREIGN KEY (`matching_event_id`) REFERENCES `matching_coordination_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_successor_owner_event` FOREIGN KEY (`replacement_event_id`, `case_no`, `replacement_generation_id`, `scenario`, `expected_generation_version`, `expected_event_version`) REFERENCES `scheduling_service_before_replacement_events` (`id`, `case_no`, `replacement_generation_id`, `scenario`, `expected_generation_version`, `expected_event_version`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_service_before_replacement_successor_package` FOREIGN KEY (`matching_package_lineage_id`) REFERENCES `matching_coordination_package_lineage` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_service_before_replacement_successor_r07` CHECK ((((`scenario` = _utf8mb4'R-07') and (`candidate_count` = 0) and (`zero_candidate_disposition` = _utf8mb4'blocked_no_candidate') and (`reuse_proof_variant` = _utf8mb4'not_reused') and (`resume_step` = _utf8mb4'step_2')) or ((`scenario` <> _utf8mb4'R-07') and (`zero_candidate_disposition` is null)))),
  CONSTRAINT `chk_service_before_replacement_successor_reuse` CHECK ((((`reuse_proof_variant` = _utf8mb4'not_reused') and (`reuse_pool_identity` is null) and (`reuse_round_identity` is null) and (`reuse_coverage_version` is null) and (`reuse_availability_version` is null) and (`reuse_willingness_version` is null) and (`reuse_candidate_identity` is null) and (`reuse_accepted_candidate` is null) and (`reuse_proof_fingerprint` is null) and (`resume_step` = _utf8mb4'step_2')) or ((`reuse_proof_variant` = _utf8mb4'candidate_pool_reused') and (`reuse_round_identity` = `successor_round_identity`) and (char_length(trim(`reuse_pool_identity`)) > 0) and (`reuse_coverage_version` is not null) and (`reuse_availability_version` is not null) and (`reuse_willingness_version` is not null) and (char_length(trim(`reuse_candidate_identity`)) > 0) and (`reuse_accepted_candidate` in (0,1)) and regexp_like(`reuse_proof_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and (((`reuse_accepted_candidate` = 0) and (`resume_step` = _utf8mb4'step_3')) or ((`reuse_accepted_candidate` = 1) and (`resume_step` = _utf8mb4'step_4')))))),
  CONSTRAINT `chk_service_before_replacement_successor_text` CHECK (((char_length(trim(`successor_package_identity`)) > 0) and (char_length(trim(`successor_round_identity`)) > 0) and (char_length(trim(`successor_matching_event_identity`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_checkpoint_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `checkpoint_id` bigint unsigned NOT NULL,
  `event_type` enum('service_ended') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_event_root` (`checkpoint_id`,`event_type`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_event_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_scheduling_service_day_checkpoint_event_root` FOREIGN KEY (`checkpoint_id`) REFERENCES `scheduling_service_day_checkpoints` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_checkpoint_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `delivery_status` enum('pending','processing','published','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `published_at_utc` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_outbox_event` (`event_id`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_outbox_intent` (`intent_key`),
  KEY `idx_scheduling_service_day_checkpoint_outbox_delivery` (`delivery_status`,`next_attempt_at_utc`,`id`),
  CONSTRAINT `fk_scheduling_service_day_checkpoint_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `scheduling_service_day_checkpoint_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_service_day_checkpoint_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_checkpoints` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `schedule_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `service_date` date NOT NULL,
  `service_ends_at_utc` datetime(6) NOT NULL,
  `requires_cooking` tinyint(1) NOT NULL,
  `baby_log_completed` tinyint(1) NOT NULL DEFAULT '0',
  `checkpoint_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_assignment_date` (`assignment_id`,`service_date`),
  UNIQUE KEY `uq_scheduling_service_day_checkpoint_key` (`checkpoint_key`),
  KEY `idx_scheduling_service_day_checkpoint_due` (`service_ends_at_utc`,`id`),
  KEY `fk_scheduling_service_day_checkpoint_case` (`case_no`),
  KEY `fk_scheduling_service_day_checkpoint_staff` (`staff_id`),
  CONSTRAINT `fk_scheduling_service_day_checkpoint_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_checkpoint_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_checkpoint_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_service_day_checkpoint_key` CHECK ((char_length(trim(`checkpoint_key`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_log_attachments` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `service_day_log_id` bigint unsigned NOT NULL,
  `provider_media_id` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `attachment_kind` enum('meal_photo','baby_log_photo') COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `controlled_file_object_id` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_log_attachment` (`service_day_log_id`,`provider_media_id`),
  UNIQUE KEY `uq_scheduling_service_day_log_attachment_controlled_file` (`controlled_file_object_id`),
  KEY `fk_scheduling_service_day_log_attachment_media` (`provider_media_id`),
  CONSTRAINT `fk_scheduling_service_day_log_attachment_controlled_file` FOREIGN KEY (`controlled_file_object_id`) REFERENCES `controlled_file_objects` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_attachment_media` FOREIGN KEY (`provider_media_id`) REFERENCES `line_media_records` (`provider_media_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_attachment_root` FOREIGN KEY (`service_day_log_id`) REFERENCES `scheduling_service_day_logs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_service_day_log_attachment_reference_source` CHECK ((((`provider_media_id` is not null) and (`controlled_file_object_id` is null)) or ((`provider_media_id` is null) and (`controlled_file_object_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_log_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `service_day_log_id` bigint unsigned NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `service_date` date NOT NULL,
  `event_type` enum('submitted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_log_event_root` (`service_day_log_id`,`event_type`),
  UNIQUE KEY `uq_scheduling_service_day_log_event_idempotency` (`idempotency_key`),
  KEY `idx_scheduling_service_day_log_event_assignment_date` (`assignment_id`,`service_date`,`id`),
  KEY `fk_scheduling_service_day_log_event_staff` (`staff_id`),
  CONSTRAINT `fk_scheduling_service_day_log_event_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_event_root` FOREIGN KEY (`service_day_log_id`) REFERENCES `scheduling_service_day_logs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_event_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_log_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `delivery_status` enum('pending','processing','published','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `published_at_utc` datetime(6) DEFAULT NULL,
  `last_error_code` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_log_outbox_event` (`event_id`),
  UNIQUE KEY `uq_scheduling_service_day_log_outbox_intent` (`intent_key`),
  KEY `idx_scheduling_service_day_log_outbox_delivery` (`delivery_status`,`created_at_utc`,`id`),
  KEY `idx_scheduling_service_day_log_outbox_retry` (`delivery_status`,`next_attempt_at_utc`,`id`),
  CONSTRAINT `fk_scheduling_service_day_log_outbox_event` FOREIGN KEY (`event_id`) REFERENCES `scheduling_service_day_log_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_service_day_log_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_day_logs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `staff_line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_date` date NOT NULL,
  `baby_log_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `requires_cooking` tinyint(1) NOT NULL,
  `content_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_service_day_log_assignment_date` (`assignment_id`,`service_date`),
  UNIQUE KEY `uq_scheduling_service_day_log_idempotency` (`idempotency_key`),
  KEY `idx_scheduling_service_day_log_case_date` (`case_no`,`service_date`,`id`),
  KEY `fk_scheduling_service_day_log_staff` (`staff_id`),
  CONSTRAINT `fk_scheduling_service_day_log_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_service_day_log_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_service_day_log_fingerprint` CHECK (regexp_like(`content_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_scheduling_service_day_log_text` CHECK ((char_length(trim(`baby_log_text`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_start_candidates` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `proposed_start_date` date NOT NULL,
  `proposed_end_date` date NOT NULL,
  `willingness` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `interaction_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `response_event_key` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `invitation_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_start_interaction` (`interaction_hash`),
  UNIQUE KEY `uq_service_start_response_event` (`response_event_key`),
  KEY `ix_service_start_candidates` (`request_id`,`id`),
  CONSTRAINT `fk_service_start_candidate_request` FOREIGN KEY (`request_id`) REFERENCES `scheduling_service_start_requests` (`id`),
  CONSTRAINT `ck_service_start_period` CHECK ((`proposed_end_date` >= `proposed_start_date`)),
  CONSTRAINT `ck_service_start_willingness` CHECK ((`willingness` in (_utf8mb4'pending',_utf8mb4'willing',_utf8mb4'unwilling')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_service_start_requests` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `plan_id` bigint DEFAULT NULL,
  `segment_id` bigint DEFAULT NULL,
  `assignment_id` bigint DEFAULT NULL,
  `decision` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `requested_start_date` date DEFAULT NULL,
  `source_order_version` bigint NOT NULL,
  `status` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint NOT NULL DEFAULT '1',
  `selected_candidate_id` bigint DEFAULT NULL,
  `execution_dates` json DEFAULT NULL,
  `confirmed_version_id` bigint DEFAULT NULL,
  `result_snapshot` json DEFAULT NULL,
  `submit_key` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `submit_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_service_start_submit` (`submit_key`),
  KEY `ix_service_start_case` (`case_no`,`id`),
  KEY `ix_service_start_pending` (`status`,`id`),
  CONSTRAINT `ck_service_start_decision` CHECK ((`decision` in (_utf8mb4'accepted',_utf8mb4'declined'))),
  CONSTRAINT `ck_service_start_status` CHECK ((`status` in (_utf8mb4'awaiting_peers',_utf8mb4'substitute_required',_utf8mb4'applied')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_availability_aggregates` (
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_scheduling_staff_availability_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_availability_apply_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL,
  `block_id` bigint NOT NULL,
  `action` enum('create_long_leave','create_pause','end_pause','cancel') COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`idempotency_key`),
  KEY `fk_scheduling_staff_availability_receipt_staff` (`staff_id`),
  KEY `fk_scheduling_staff_availability_receipt_block` (`block_id`),
  CONSTRAINT `fk_scheduling_staff_availability_receipt_block` FOREIGN KEY (`block_id`) REFERENCES `scheduling_staff_unavailability_blocks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_staff_availability_receipt_staff` FOREIGN KEY (`staff_id`) REFERENCES `scheduling_staff_availability_aggregates` (`staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_staff_availability_receipt_fingerprints` CHECK ((regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_scheduling_staff_availability_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_availability_events` (
  `event_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL,
  `block_id` bigint NOT NULL,
  `event_type` enum('created','pause_ended','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_snapshot` json NOT NULL,
  `after_snapshot` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `occurred_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`event_key`),
  KEY `fk_scheduling_staff_availability_event_staff` (`staff_id`),
  KEY `fk_scheduling_staff_availability_event_block` (`block_id`),
  CONSTRAINT `fk_scheduling_staff_availability_event_block` FOREIGN KEY (`block_id`) REFERENCES `scheduling_staff_unavailability_blocks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_staff_availability_event_staff` FOREIGN KEY (`staff_id`) REFERENCES `scheduling_staff_availability_aggregates` (`staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_staff_availability_event_snapshots` CHECK (((`aggregate_version` > 0) and (json_type(`before_snapshot`) = _utf8mb4'OBJECT') and (json_type(`after_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_leave_request_aggregates` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `line_user_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `leave_start_date` date NOT NULL,
  `leave_end_date` date NOT NULL,
  `request_reason` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `request_status` enum('pending','accepted_for_processing','rejected','cancelled','resolved') COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` int unsigned NOT NULL DEFAULT '1',
  `request_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_leave_request_fingerprint` (`staff_id`,`request_fingerprint`),
  KEY `idx_staff_leave_request_queue` (`request_status`,`created_at`,`id`),
  CONSTRAINT `fk_staff_leave_request_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`),
  CONSTRAINT `chk_staff_leave_request_dates` CHECK ((`leave_start_date` <= `leave_end_date`)),
  CONSTRAINT `chk_staff_leave_request_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_leave_request_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_id` bigint NOT NULL,
  `aggregate_version` int unsigned NOT NULL,
  `event_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_leave_request_event_version` (`request_id`,`aggregate_version`),
  CONSTRAINT `fk_staff_leave_request_event_root` FOREIGN KEY (`request_id`) REFERENCES `scheduling_staff_leave_request_aggregates` (`id`),
  CONSTRAINT `chk_staff_leave_request_event_text` CHECK (((char_length(trim(`event_type`)) > 0) and (char_length(trim(`actor_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_leave_request_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_id` bigint NOT NULL,
  `request_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_leave_request_receipt_key` (`idempotency_key`),
  KEY `fk_staff_leave_request_receipt_root` (`request_id`),
  CONSTRAINT `fk_staff_leave_request_receipt_root` FOREIGN KEY (`request_id`) REFERENCES `scheduling_staff_leave_request_aggregates` (`id`),
  CONSTRAINT `chk_staff_leave_request_receipt_fingerprint` CHECK (regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_staff_leave_request_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_leave_request_resolution_links` (
  `request_id` bigint NOT NULL,
  `leave_substitution_receipt_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `linked_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`request_id`),
  UNIQUE KEY `uq_staff_leave_resolution_receipt` (`leave_substitution_receipt_key`),
  CONSTRAINT `fk_staff_leave_resolution_root` FOREIGN KEY (`request_id`) REFERENCES `scheduling_staff_leave_request_aggregates` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `scheduling_staff_unavailability_blocks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `block_kind` enum('long_leave','paused_service') COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date DEFAULT NULL,
  `status` enum('effective','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'effective',
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_block_id` bigint DEFAULT NULL,
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `ended_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ended_at` datetime(6) DEFAULT NULL,
  `cancelled_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cancelled_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_scheduling_staff_unavailability_source` (`source_block_id`),
  KEY `idx_scheduling_staff_unavailability_current` (`staff_id`,`status`,`start_date`,`end_date`),
  CONSTRAINT `fk_scheduling_staff_unavailability_source` FOREIGN KEY (`source_block_id`) REFERENCES `scheduling_staff_unavailability_blocks` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_staff_unavailability_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_staff_unavailability_dates` CHECK ((((`block_kind` = _utf8mb4'long_leave') and (`end_date` is not null) and (`end_date` >= `start_date`)) or ((`block_kind` = _utf8mb4'paused_service') and ((`end_date` is null) or (`end_date` >= `start_date`))))),
  CONSTRAINT `chk_scheduling_staff_unavailability_reason` CHECK (((char_length(trim(`reason`)) > 0) and (char_length(trim(`created_by`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff` (
  `id` int NOT NULL AUTO_INCREMENT,
  `registered_at` datetime DEFAULT NULL COMMENT '報名時間',
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '註冊IP',
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '姓名',
  `identity_card` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '身分證字號',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `tel` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '市話',
  `tel_ext` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分機',
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'EMAIL',
  `birthday` date DEFAULT NULL COMMENT '生日 (由民國生日整合)',
  `city` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '居住縣市',
  `zip_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '郵遞區號',
  `address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '詳細地址',
  `education` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '教育程度／最高學歷',
  `emergency_contact_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '緊急聯絡人姓名',
  `emergency_contact_phone` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '緊急聯絡人電話',
  `admin_notes` text COLLATE utf8mb4_unicode_ci COMMENT '月嫂內部行政註記',
  `staff_profile_version` bigint unsigned NOT NULL DEFAULT '0',
  `has_massage_cert` tinyint(1) DEFAULT '0' COMMENT '有嬰幼兒按摩證書嗎',
  `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'active' COMMENT '在職狀態 (active/inactive)',
  `line_user_id` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
  `weekly_rest_days` json DEFAULT NULL COMMENT '固定休假偏好 JSON 陣列 (如 ["Sunday"])',
  `care_babies` int DEFAULT '1' COMMENT '最大可照顧寶寶數量 (1:單胞胎, 2:雙胞胎, 3:三胞胎)',
  `service_regions` json DEFAULT NULL COMMENT '接受服務區域 JSON 陣列',
  `special_skills` json DEFAULT NULL COMMENT '特殊技能與偏好標籤 JSON 陣列',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `union_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL COMMENT '公會自訂編號',
  PRIMARY KEY (`id`),
  UNIQUE KEY `identity_card` (`identity_card`),
  UNIQUE KEY `uq_staff_union_no` (`union_no`),
  KEY `idx_staff_name` (`name`),
  KEY `idx_staff_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_actual_transfers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `settlement_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `payment_phase` enum('normal','first_salary','second_subsidy','unknown') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `transaction_type` enum('transfer','return','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `source_bank` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_account` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `counterparty_account` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `external_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_transfer_id` bigint DEFAULT NULL,
  `raw_import_reference` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `review_status` enum('not_required','pending','confirmed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_actual_transfer_reference` (`external_reference`),
  KEY `idx_staff_actual_transfer_settlement` (`settlement_id`,`occurred_at`),
  KEY `idx_staff_actual_transfer_staff` (`staff_id`,`occurred_at`),
  KEY `idx_staff_actual_transfer_reversal` (`reversal_of_transfer_id`),
  CONSTRAINT `fk_staff_actual_transfer_reversal` FOREIGN KEY (`reversal_of_transfer_id`) REFERENCES `staff_actual_transfers` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_actual_transfer_settlement` FOREIGN KEY (`settlement_id`) REFERENCES `staff_monthly_settlements` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_actual_transfer_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_actual_transfer_amount` CHECK ((`amount` > 0)),
  CONSTRAINT `chk_staff_actual_transfer_original` CHECK ((((`transaction_type` = _utf8mb4'transfer') and (`reversal_of_transfer_id` is null)) or ((`transaction_type` in (_utf8mb4'return',_utf8mb4'reversal')) and (`reversal_of_transfer_id` is not null)))),
  CONSTRAINT `chk_staff_actual_transfer_succeeded_date` CHECK (((`transaction_status` <> _utf8mb4'succeeded') or (`occurred_at` is not null))),
  CONSTRAINT `chk_staff_actual_transfer_unknown_review` CHECK (((`payment_phase` <> _utf8mb4'unknown') or (`review_status` = _utf8mb4'pending')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_baby_types` (
  `staff_id` int NOT NULL,
  `baby_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '胎數類型 (單胞胎/雙胞胎/其他)',
  `custom_baby_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他胎數的補充說明',
  PRIMARY KEY (`staff_id`,`baby_type`),
  CONSTRAINT `staff_baby_types_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_bank_account_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `account_id` int NOT NULL,
  `operation` enum('add','replace','deactivate','set_primary') COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `bank_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `branch_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `account_last4` char(4) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `was_primary` tinyint(1) NOT NULL,
  `is_primary` tinyint(1) NOT NULL,
  `was_active` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_bank_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_staff_bank_event_version` (`staff_id`,`resulting_version`),
  KEY `fk_staff_bank_event_account` (`account_id`),
  CONSTRAINT `fk_staff_bank_event_account` FOREIGN KEY (`account_id`) REFERENCES `staff_bank_accounts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_bank_event_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_bank_event_last4` CHECK (((`account_last4` is null) or regexp_like(`account_last4`,_utf8mb4'^[0-9]{4}$'))),
  CONSTRAINT `chk_staff_bank_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_bank_account_states` (
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_by` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_staff_bank_state_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_bank_accounts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `bank_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行代碼(3碼)',
  `branch_code` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分行代碼(4碼)',
  `account_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '銀行帳號',
  `is_primary` tinyint(1) DEFAULT '1' COMMENT '是否為主要帳戶',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_bank_accounts_account_no` (`account_no`),
  KEY `staff_id` (`staff_id`),
  CONSTRAINT `staff_bank_accounts_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_bookings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `client_id` int NOT NULL COMMENT '對應 clients.id',
  `start_date` date NOT NULL COMMENT '服務開始日期',
  `end_date` date NOT NULL COMMENT '服務結束日期',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `staff_id` (`staff_id`),
  KEY `idx_booking_dates` (`start_date`,`end_date`),
  CONSTRAINT `staff_bookings_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_certifications` (
  `staff_id` int NOT NULL,
  `certification_type` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'BeClass 資格／證明原始選項名稱',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`,`certification_type`),
  CONSTRAINT `fk_staff_certification_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_certification_type` CHECK ((char_length(trim(`certification_type`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_cooking_skills` (
  `staff_id` int NOT NULL,
  `skill_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '料理類型 (葷食/素食/其他)',
  `custom_skill_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他料理的補充說明',
  PRIMARY KEY (`staff_id`,`skill_name`),
  CONSTRAINT `staff_cooking_skills_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_historical_adoption_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `source_event_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `staff_id` int DEFAULT NULL,
  `outcome` enum('created','adopted_existing','blocked_identity','identity_conflict','failed_retryable') COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_fields` json NOT NULL,
  `review_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_historical_adoption_key` (`idempotency_key`),
  UNIQUE KEY `uq_staff_historical_adoption_source` (`source_event_identity`),
  KEY `fk_staff_historical_adoption_staff` (`staff_id`),
  KEY `fk_staff_historical_adoption_review` (`review_identity`),
  CONSTRAINT `fk_staff_historical_adoption_review` FOREIGN KEY (`review_identity`) REFERENCES `beclass_import_review_rows` (`review_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_historical_adoption_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_historical_adoption_changed_fields` CHECK ((json_type(`changed_fields`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_staff_historical_adoption_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_holiday_availability` (
  `staff_id` int NOT NULL,
  `holiday_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '節日名稱 (初一/初二/初三/端午/中秋/國定假日必休/其他)',
  `custom_holiday_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他節日的補充說明',
  PRIMARY KEY (`staff_id`,`holiday_name`),
  CONSTRAINT `staff_holiday_availability_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_lifecycle_apply_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `resulting_state` enum('active','retired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `event_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`idempotency_key`),
  KEY `fk_staff_lifecycle_receipt_staff` (`staff_id`),
  KEY `fk_staff_lifecycle_receipt_event` (`event_id`),
  CONSTRAINT `fk_staff_lifecycle_receipt_event` FOREIGN KEY (`event_id`) REFERENCES `staff_lifecycle_events` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_lifecycle_receipt_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_lifecycle_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `event_type` enum('retired','reactivated') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_state` enum('active','retired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_state` enum('active','retired') COLLATE utf8mb4_unicode_ci NOT NULL,
  `effective_at` datetime(6) NOT NULL,
  `reason_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_lifecycle_event_version` (`staff_id`,`resulting_version`),
  KEY `idx_staff_lifecycle_event_time` (`staff_id`,`effective_at`),
  CONSTRAINT `fk_staff_lifecycle_event_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_staff_lifecycle_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_lifecycle_states` (
  `staff_id` int NOT NULL,
  `lifecycle_state` enum('active','retired') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `effective_at` datetime(6) DEFAULT NULL,
  `reason_code` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_staff_lifecycle_state_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_staff_lifecycle_state_version` CHECK ((`aggregate_version` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_matching_preference_definitions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `preference_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `display_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `value_kind` enum('integer_range','integer_set') COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_filterable` tinyint(1) NOT NULL DEFAULT '0',
  `order_fact_key` enum('service_days','service_hours_per_day') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `comparison_operator` enum('range_with_tolerance','contains_integer') COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('active','inactive') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `version` bigint unsigned NOT NULL DEFAULT '1',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_matching_preference_key` (`preference_key`),
  CONSTRAINT `chk_staff_matching_preference_comparison` CHECK ((((`value_kind` = _utf8mb4'integer_range') and (`comparison_operator` = _utf8mb4'range_with_tolerance')) or ((`value_kind` = _utf8mb4'integer_set') and (`comparison_operator` = _utf8mb4'contains_integer')))),
  CONSTRAINT `chk_staff_matching_preference_definition_text` CHECK (((char_length(trim(`preference_key`)) > 0) and (char_length(trim(`display_name`)) > 0) and (char_length(trim(`created_by`)) > 0) and (char_length(trim(`updated_by`)) > 0))),
  CONSTRAINT `chk_staff_matching_preference_filter_source` CHECK ((((`is_filterable` = 0) and (`order_fact_key` is null)) or ((`is_filterable` = 1) and (`order_fact_key` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_matching_preference_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_type` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_json` json NOT NULL,
  `after_json` json NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_matching_preference_event_key` (`idempotency_key`),
  CONSTRAINT `chk_staff_matching_preference_event_snapshots` CHECK (((`resulting_version` > 0) and (json_type(`before_json`) = _utf8mb4'OBJECT') and (json_type(`after_json`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_matching_preference_profiles` (
  `staff_id` int NOT NULL,
  `version` bigint unsigned NOT NULL DEFAULT '0',
  `created_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_staff_matching_preference_profile_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_matching_preference_profile_actor` CHECK ((char_length(trim(`updated_by`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_matching_preference_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_json` json NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`idempotency_key`),
  CONSTRAINT `chk_staff_matching_preference_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_staff_matching_preference_receipt_snapshot` CHECK ((json_type(`result_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_matching_preference_values` (
  `staff_id` int NOT NULL,
  `definition_id` bigint NOT NULL,
  `value_json` json NOT NULL,
  `profile_version` bigint unsigned NOT NULL,
  `updated_by` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`staff_id`,`definition_id`),
  KEY `fk_staff_matching_preference_value_definition` (`definition_id`),
  CONSTRAINT `fk_staff_matching_preference_value_definition` FOREIGN KEY (`definition_id`) REFERENCES `staff_matching_preference_definitions` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_matching_preference_value_profile` FOREIGN KEY (`staff_id`) REFERENCES `staff_matching_preference_profiles` (`staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_matching_preference_value_actor` CHECK ((char_length(trim(`updated_by`)) > 0)),
  CONSTRAINT `chk_staff_matching_preference_value_json` CHECK ((json_type(`value_json`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_monthly_settlement_details` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `settlement_id` bigint NOT NULL,
  `staff_payment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `service_salary` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '一般服務薪資快照',
  `legacy_subsidy_payable` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '舊制補助應付構成快照',
  `floor_fee_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '樓層費快照',
  `adjustment_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '可正可負的人工調整快照',
  `payable_amount` decimal(12,2) NOT NULL COMMENT '應付構成合計快照',
  `legacy_subsidy_status` enum('not_applicable','confirmed','review_required') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'not_applicable',
  `review_required` tinyint(1) NOT NULL DEFAULT '0',
  `review_note` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_monthly_settlement_detail_payment` (`settlement_id`,`staff_payment_id`),
  KEY `idx_staff_monthly_settlement_detail_staff` (`staff_id`,`settlement_id`),
  KEY `idx_staff_monthly_settlement_detail_case` (`case_no`,`assignment_id`),
  KEY `fk_staff_monthly_settlement_detail_payment` (`staff_payment_id`),
  KEY `fk_staff_monthly_settlement_detail_assignment` (`assignment_id`),
  CONSTRAINT `fk_staff_monthly_settlement_detail_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_monthly_settlement_detail_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_staff_monthly_settlement_detail_payment` FOREIGN KEY (`staff_payment_id`) REFERENCES `staff_payments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_monthly_settlement_detail_settlement` FOREIGN KEY (`settlement_id`) REFERENCES `staff_monthly_settlements` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_monthly_settlement_detail_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_staff_monthly_settlement_detail_components` CHECK (((`service_salary` >= 0) and (`legacy_subsidy_payable` >= 0) and (`floor_fee_amount` >= 0) and (`payable_amount` >= 0) and (`payable_amount` = (((`service_salary` + `legacy_subsidy_payable`) + `floor_fee_amount`) + `adjustment_amount`)))),
  CONSTRAINT `chk_staff_monthly_settlement_detail_legacy_subsidy` CHECK (((`legacy_subsidy_payable` = 0) or (`legacy_subsidy_status` in (_utf8mb4'confirmed',_utf8mb4'review_required')))),
  CONSTRAINT `chk_staff_monthly_settlement_detail_review_state` CHECK ((((`legacy_subsidy_status` = _utf8mb4'review_required') and (`review_required` = true)) or ((`legacy_subsidy_status` <> _utf8mb4'review_required') and (`review_required` = false))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_monthly_settlements` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `settlement_month` date NOT NULL COMMENT '薪資歸屬月份；固定使用該月首日',
  `revision` int unsigned NOT NULL DEFAULT '1' COMMENT '同一服務人員同月的月結修訂版，從 1 起',
  `total_payable` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '月結明細應付快照合計',
  `total_paid` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功轉帳分配的淨額投影，不得人工覆寫',
  `status` enum('draft','finalized','partially_paid','paid','cancelled','review_required') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `finalized_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_monthly_settlement_revision` (`staff_id`,`settlement_month`,`revision`),
  KEY `idx_staff_monthly_settlement_status` (`settlement_month`,`status`),
  CONSTRAINT `fk_staff_monthly_settlement_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_staff_monthly_settlement_finalized_at` CHECK (((`status` <> _utf8mb4'finalized') or (`finalized_at` is not null))),
  CONSTRAINT `chk_staff_monthly_settlement_month_start` CHECK ((dayofmonth(`settlement_month`) = 1)),
  CONSTRAINT `chk_staff_monthly_settlement_revision` CHECK ((`revision` >= 1)),
  CONSTRAINT `chk_staff_monthly_settlement_totals` CHECK (((`total_payable` >= 0) and (`total_paid` >= 0) and (`total_paid` <= `total_payable`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_obligation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_kind` enum('service_pay','adjustment','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('payable_to_staff','receivable_from_staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_type` enum('established','rebuilt','adjustment','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_amount_ntd` bigint NOT NULL,
  `after_amount_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `payroll_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_payroll_version` bigint unsigned NOT NULL,
  `resulting_payroll_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_obligation_event_idempotency` (`idempotency_key`),
  KEY `idx_staff_obligation_event_identity` (`obligation_identity`,`created_at`),
  KEY `fk_staff_obligation_event_owner` (`assignment_id`,`case_no`,`staff_id`),
  KEY `fk_staff_obligation_event_source` (`source_obligation_identity`,`case_no`),
  CONSTRAINT `fk_staff_obligation_event_owner` FOREIGN KEY (`assignment_id`, `case_no`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `case_no`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_obligation_event_source` FOREIGN KEY (`source_obligation_identity`, `case_no`) REFERENCES `staff_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_obligation_event_amount` CHECK (((`before_amount_ntd` >= 0) and (`after_amount_ntd` >= 0) and (`before_amount_ntd` <> `after_amount_ntd`))),
  CONSTRAINT `chk_staff_obligation_event_fingerprint` CHECK (regexp_like(`payroll_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_staff_obligation_event_version` CHECK ((`resulting_payroll_version` = (`expected_payroll_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_obligation_installments` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `funding_kind` enum('client','subsidy') COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  PRIMARY KEY (`obligation_identity`,`funding_kind`),
  CONSTRAINT `fk_payroll_installment_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`),
  CONSTRAINT `chk_payroll_installment_amount` CHECK ((`amount_ntd` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_obligations` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_kind` enum('service_pay','adjustment','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('payable_to_staff','receivable_from_staff') COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount_due_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `status` enum('open','settled','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `payout_history_exists` tinyint(1) NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`obligation_identity`),
  UNIQUE KEY `uq_staff_obligation_case_identity` (`obligation_identity`,`case_no`),
  KEY `idx_staff_obligation_assignment` (`assignment_id`),
  KEY `idx_staff_obligation_staff_due` (`staff_id`,`due_date`,`obligation_identity`),
  KEY `fk_staff_obligation_owner` (`assignment_id`,`case_no`,`staff_id`),
  KEY `fk_staff_obligation_current_event` (`current_event_id`),
  KEY `fk_staff_obligation_source` (`source_obligation_identity`,`case_no`),
  CONSTRAINT `fk_staff_obligation_current_event` FOREIGN KEY (`current_event_id`) REFERENCES `staff_obligation_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_obligation_owner` FOREIGN KEY (`assignment_id`, `case_no`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `case_no`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_obligation_source` FOREIGN KEY (`source_obligation_identity`, `case_no`) REFERENCES `staff_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_obligation_state` CHECK ((((`status` = _utf8mb4'open') and (`amount_due_ntd` > 0)) or ((`status` in (_utf8mb4'settled',_utf8mb4'cancelled')) and (`amount_due_ntd` = 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_overpayment_recoveries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `original_amount_ntd` bigint NOT NULL,
  `remaining_amount_ntd` bigint NOT NULL,
  `status` enum('open','partially_recovered','recovered','adjusted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `source_bank_fact_identities` json NOT NULL,
  `source_payout_event_ids` json NOT NULL,
  `source_obligation_identities` json NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_overpayment_recovery_identity` (`recovery_identity`),
  KEY `idx_staff_overpayment_recovery_staff_status` (`staff_id`,`status`,`id`),
  CONSTRAINT `fk_staff_overpayment_recovery_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_overpayment_recovery_amount` CHECK (((`original_amount_ntd` > 0) and (`remaining_amount_ntd` >= 0) and (`remaining_amount_ntd` <= `original_amount_ntd`))),
  CONSTRAINT `chk_staff_overpayment_recovery_sources` CHECK (((json_type(`source_bank_fact_identities`) = _utf8mb4'ARRAY') and (json_type(`source_payout_event_ids`) = _utf8mb4'ARRAY') and (json_type(`source_obligation_identities`) = _utf8mb4'ARRAY')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_overpayment_recovery_apply_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`),
  KEY `fk_staff_overpayment_recovery_receipt_root` (`recovery_identity`),
  CONSTRAINT `fk_staff_overpayment_recovery_receipt_root` FOREIGN KEY (`recovery_identity`) REFERENCES `staff_overpayment_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_overpayment_recovery_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('cash_recovered','authorized_adjustment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `before_remaining_ntd` bigint NOT NULL,
  `after_remaining_ntd` bigint NOT NULL,
  `resulting_status` enum('partially_recovered','recovered','adjusted') COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_overpayment_recovery_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_staff_overpayment_recovery_event_bank_row` (`finance_import_row_id`),
  KEY `fk_staff_overpayment_recovery_event_root` (`recovery_identity`),
  CONSTRAINT `fk_staff_overpayment_recovery_event_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_overpayment_recovery_event_root` FOREIGN KEY (`recovery_identity`) REFERENCES `staff_overpayment_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_overpayment_recovery_event_amount` CHECK (((`before_remaining_ntd` > 0) and (`after_remaining_ntd` >= 0))),
  CONSTRAINT `chk_staff_overpayment_recovery_event_evidence` CHECK (((`evidence_reference` is null) or (char_length(trim(`evidence_reference`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_overpayment_recovery_matching_receipts` (
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `matching_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`),
  KEY `fk_staff_recovery_matching_receipt` (`matching_identity`),
  CONSTRAINT `fk_staff_recovery_matching_receipt` FOREIGN KEY (`matching_identity`) REFERENCES `staff_overpayment_recovery_matchings` (`matching_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_recovery_matching_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_staff_recovery_matching_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_overpayment_recovery_matchings` (
  `matching_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `recovery_version` bigint unsigned NOT NULL,
  `staff_payables_version` bigint unsigned NOT NULL,
  `matching_version` bigint unsigned NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_reference` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`matching_identity`),
  UNIQUE KEY `uq_staff_recovery_matching_bank_row` (`finance_import_row_id`),
  UNIQUE KEY `uq_staff_recovery_matching_idempotency` (`idempotency_key`),
  KEY `fk_staff_recovery_matching_root` (`recovery_identity`),
  KEY `fk_staff_recovery_matching_staff` (`staff_id`),
  CONSTRAINT `fk_staff_recovery_matching_root` FOREIGN KEY (`recovery_identity`) REFERENCES `staff_overpayment_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_recovery_matching_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_recovery_matching_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_overpayment_recovery_matching_evidence` CHECK (((`evidence_reference` is null) or (char_length(trim(`evidence_reference`)) > 0))),
  CONSTRAINT `chk_staff_recovery_matching_version` CHECK ((`matching_version` = 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payable_accounts` (
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_staff_payable_account_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payable_projections` (
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_amount_ntd` bigint NOT NULL,
  `net_paid_ntd` bigint NOT NULL,
  `balance_ntd` bigint NOT NULL,
  `status` enum('payable','partially_paid','completed','recovery_required','anomaly') COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL,
  `current_event_id` bigint NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`obligation_identity`),
  KEY `idx_staff_payable_projection_status` (`staff_id`,`status`,`obligation_identity`),
  KEY `fk_staff_payable_projection_event` (`current_event_id`),
  CONSTRAINT `fk_staff_payable_projection_event` FOREIGN KEY (`current_event_id`) REFERENCES `staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payable_projection_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payable_projection_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payable_projection_money` CHECK (((`obligation_amount_ntd` > 0) and (`net_paid_ntd` >= 0) and (`balance_ntd` = (`obligation_amount_ntd` - `net_paid_ntd`)))),
  CONSTRAINT `chk_staff_payable_projection_status` CHECK ((((`status` = _utf8mb4'payable') and (`net_paid_ntd` = 0) and (`balance_ntd` = `obligation_amount_ntd`)) or ((`status` = _utf8mb4'partially_paid') and (`net_paid_ntd` > 0) and (`balance_ntd` > 0)) or ((`status` = _utf8mb4'completed') and (`net_paid_ntd` = `obligation_amount_ntd`) and (`balance_ntd` = 0)) or ((`status` = _utf8mb4'recovery_required') and (`net_paid_ntd` = `obligation_amount_ntd`) and (`balance_ntd` = 0)) or ((`status` = _utf8mb4'anomaly') and (`balance_ntd` < 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payables_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payables_receipt_idempotency` (`idempotency_key`),
  KEY `fk_staff_payables_receipt_staff` (`staff_id`),
  CONSTRAINT `fk_staff_payables_receipt_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payables_receipt_fingerprint` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_staff_payables_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payables_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `intent_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('payable_projection_refresh','payout_anomaly_required','staff_overpayment_recovery_updated','staff_overpayment_recovery_matched','staff_overpayment_recovery_collected') COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payables_outbox_intent` (`intent_key`),
  KEY `idx_staff_payables_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_staff_payables_outbox_staff` (`staff_id`),
  CONSTRAINT `fk_staff_payables_outbox_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payables_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payment_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_payment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `transaction_type` enum('transfer','reversal','return') COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payment_tx_reference` (`external_reference`),
  KEY `idx_staff_payment_tx_staff` (`staff_id`,`occurred_at`),
  KEY `fk_staff_payment_tx_summary` (`staff_payment_id`),
  KEY `fk_staff_payment_tx_case_no` (`case_no`),
  KEY `fk_staff_payment_tx_reversal` (`reversal_of_transaction_id`),
  CONSTRAINT `fk_staff_payment_tx_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_staff_payment_tx_reversal` FOREIGN KEY (`reversal_of_transaction_id`) REFERENCES `staff_payment_transactions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_payment_tx_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_payment_tx_summary` FOREIGN KEY (`staff_payment_id`) REFERENCES `staff_payments` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `service_hours` decimal(10,2) NOT NULL DEFAULT '0.00',
  `hourly_rate` decimal(10,2) NOT NULL DEFAULT '0.00',
  `service_salary` decimal(12,2) NOT NULL DEFAULT '0.00',
  `floor_fee_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `adjustment_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_payable` decimal(12,2) NOT NULL DEFAULT '0.00',
  `amount_paid` decimal(12,2) NOT NULL DEFAULT '0.00',
  `due_date` date DEFAULT NULL,
  `paid_at` date DEFAULT NULL COMMENT '全額實付完成日；部分轉帳見交易明細',
  `payment_status` enum('pending','partially_paid','paid','cancelled','review_required') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payment_assignment` (`assignment_id`),
  KEY `idx_staff_payment_staff_status` (`staff_id`,`payment_status`),
  KEY `idx_staff_payment_case_no` (`case_no`),
  CONSTRAINT `fk_staff_payment_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_payment_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_staff_payment_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payout_difference_source_bank_rows` (
  `payout_difference_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `ordinal` int unsigned NOT NULL,
  PRIMARY KEY (`payout_difference_identity`,`finance_import_row_id`),
  UNIQUE KEY `uq_staff_payout_difference_source_bank_ordinal` (`payout_difference_identity`,`ordinal`),
  KEY `fk_staff_payout_difference_source_bank_row` (`finance_import_row_id`),
  CONSTRAINT `fk_staff_payout_difference_source_bank_root` FOREIGN KEY (`payout_difference_identity`) REFERENCES `staff_payout_difference_sources` (`payout_difference_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_difference_source_bank_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payout_difference_source_obligations` (
  `payout_difference_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ordinal` int unsigned NOT NULL,
  PRIMARY KEY (`payout_difference_identity`,`obligation_identity`),
  UNIQUE KEY `uq_staff_payout_difference_source_obligation_ordinal` (`payout_difference_identity`,`ordinal`),
  KEY `fk_staff_payout_difference_source_obligation` (`obligation_identity`),
  CONSTRAINT `fk_staff_payout_difference_source_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_difference_source_obligation_root` FOREIGN KEY (`payout_difference_identity`) REFERENCES `staff_payout_difference_sources` (`payout_difference_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payout_difference_sources` (
  `payout_difference_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `difference_mode` enum('underpayment','overpayment') COLLATE utf8mb4_unicode_ci NOT NULL,
  `bank_total_ntd` bigint NOT NULL,
  `obligation_total_ntd` bigint NOT NULL,
  `recovery_identity` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resulting_staff_payables_version` bigint unsigned NOT NULL,
  `source_bank_facts_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`payout_difference_identity`),
  UNIQUE KEY `uq_staff_payout_difference_source_key` (`idempotency_key`),
  KEY `fk_staff_payout_difference_source_staff` (`staff_id`),
  KEY `fk_staff_payout_difference_source_recovery` (`recovery_identity`),
  CONSTRAINT `fk_staff_payout_difference_source_recovery` FOREIGN KEY (`recovery_identity`) REFERENCES `staff_overpayment_recoveries` (`recovery_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_difference_source_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payout_difference_source_amounts` CHECK (((`bank_total_ntd` > 0) and (`obligation_total_ntd` > 0) and (((`difference_mode` = _utf8mb4'underpayment') and (`bank_total_ntd` < `obligation_total_ntd`)) or ((`difference_mode` = _utf8mb4'overpayment') and (`bank_total_ntd` > `obligation_total_ntd`)))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payout_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `event_type` enum('payout','return','reversal') COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `occurred_on` date NOT NULL,
  `bank_account_identity_hash` char(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_event_id` bigint DEFAULT NULL,
  `reconciliation_reference` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payout_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_staff_payout_import_row` (`finance_import_row_id`),
  KEY `idx_staff_payout_staff_date` (`staff_id`,`occurred_on`,`id`),
  KEY `fk_staff_payout_reversal` (`reversal_of_event_id`),
  CONSTRAINT `fk_staff_payout_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_reversal` FOREIGN KEY (`reversal_of_event_id`) REFERENCES `staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payout_account_hash` CHECK (regexp_like(`bank_account_identity_hash`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_staff_payout_amount` CHECK ((`amount_ntd` > 0)),
  CONSTRAINT `chk_staff_payout_reversal_shape` CHECK ((((`event_type` = _utf8mb4'payout') and (`reversal_of_event_id` is null)) or ((`event_type` in (_utf8mb4'return',_utf8mb4'reversal')) and (`reversal_of_event_id` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_payout_obligation_links` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `payout_event_id` bigint NOT NULL,
  `obligation_identity` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `allocated_amount_ntd` bigint NOT NULL,
  `allocation_ordinal` int NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payout_obligation_link` (`payout_event_id`,`obligation_identity`),
  UNIQUE KEY `uq_staff_payout_link_ordinal` (`payout_event_id`,`allocation_ordinal`),
  KEY `idx_staff_payout_link_obligation` (`obligation_identity`,`payout_event_id`),
  CONSTRAINT `fk_staff_payout_link_event` FOREIGN KEY (`payout_event_id`) REFERENCES `staff_payout_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_payout_link_obligation` FOREIGN KEY (`obligation_identity`) REFERENCES `staff_obligations` (`obligation_identity`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payout_link_amount` CHECK ((`allocated_amount_ntd` > 0)),
  CONSTRAINT `chk_staff_payout_link_ordinal` CHECK ((`allocation_ordinal` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_profile_change_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `actor_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_values_json` json NOT NULL,
  `after_values_json` json NOT NULL,
  `created_at_utc` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_profile_event_key` (`idempotency_key`),
  UNIQUE KEY `uq_staff_profile_event_version` (`staff_id`,`resulting_version`),
  CONSTRAINT `fk_staff_profile_event_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_profile_event_payload` CHECK (((json_type(`before_values_json`) = _utf8mb4'OBJECT') and (json_type(`after_values_json`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_staff_profile_event_version` CHECK ((`resulting_version` = (`expected_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_regions` (
  `staff_id` int NOT NULL,
  `region_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '區域名稱 (北區/東區/香山區/新竹縣/苗栗縣/其他)',
  `custom_region_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '對應其他地區的補充說明',
  PRIMARY KEY (`staff_id`,`region_name`),
  CONSTRAINT `staff_regions_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_schedule` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '對應 orders.case_no',
  `staff_id` int NOT NULL COMMENT '對應 staff.id',
  `assignment_id` bigint DEFAULT NULL COMMENT '正式服務指派；既有未覆核排班保留 NULL',
  `generation_id` bigint DEFAULT NULL,
  `work_date` date NOT NULL COMMENT '工作日期',
  `is_work_day` tinyint(1) DEFAULT '1' COMMENT '是否為工作日 (FALSE代表放假/休假)',
  `is_double_pay` tinyint(1) DEFAULT '0' COMMENT '是否為雙倍薪資日 (如特殊國定假日上班)',
  `effective_marker` tinyint(1) DEFAULT '1',
  `notes` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行政人員調整備註',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_schedule_effective_date` (`staff_id`,`work_date`,`effective_marker`),
  UNIQUE KEY `uq_staff_schedule_generation_owner` (`generation_id`,`work_date`),
  KEY `idx_schedule_case_no` (`case_no`),
  KEY `idx_staff_schedule_assignment` (`assignment_id`),
  CONSTRAINT `fk_schedule_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_staff_schedule_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_staff_schedule_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `staff_schedule_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_schedule_assignment_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `schedule_id` int NOT NULL,
  `review_reason` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` enum('review_required','resolved') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'review_required',
  `resolved_assignment_id` bigint DEFAULT NULL,
  `resolved_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_schedule_review` (`schedule_id`),
  KEY `idx_schedule_assignment_review_status` (`review_status`,`created_at`),
  KEY `fk_schedule_assignment_review_assignment` (`resolved_assignment_id`),
  CONSTRAINT `fk_schedule_assignment_review_assignment` FOREIGN KEY (`resolved_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_schedule_assignment_review_schedule` FOREIGN KEY (`schedule_id`) REFERENCES `staff_schedule` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_schedule_assignment_review_resolution` CHECK ((((`review_status` = _utf8mb4'review_required') and (`resolved_assignment_id` is null) and (`resolved_by` is null) and (`resolved_at` is null)) or ((`review_status` = _utf8mb4'resolved') and (`resolved_assignment_id` is not null) and (`resolved_by` is not null) and (`resolved_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_time_slots` (
  `staff_id` int NOT NULL,
  `slot_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '時段名稱 (4小時_上午/4小時_下午/8小時/24小時/其他)',
  `custom_slot_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他時段的補充說明',
  PRIMARY KEY (`staff_id`,`slot_name`),
  CONSTRAINT `staff_time_slots_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_transfer_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `transfer_id` bigint NOT NULL,
  `settlement_detail_id` bigint NOT NULL,
  `allocated_amount` decimal(12,2) NOT NULL,
  `component_type` enum('regular_salary','legacy_subsidy','floor_fee','adjustment','unknown') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `allocation_method` enum('explicit','inferred') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'explicit',
  `review_status` enum('approved','review_required','rejected') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'review_required',
  `reversal_of_allocation_id` bigint DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_transfer_allocation_target` (`transfer_id`,`settlement_detail_id`,`component_type`),
  KEY `idx_staff_transfer_allocation_detail` (`settlement_detail_id`,`review_status`),
  KEY `fk_staff_transfer_allocation_reversal` (`reversal_of_allocation_id`),
  CONSTRAINT `fk_staff_transfer_allocation_detail` FOREIGN KEY (`settlement_detail_id`) REFERENCES `staff_monthly_settlement_details` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_transfer_allocation_reversal` FOREIGN KEY (`reversal_of_allocation_id`) REFERENCES `staff_transfer_allocations` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_staff_transfer_allocation_transfer` FOREIGN KEY (`transfer_id`) REFERENCES `staff_actual_transfers` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_staff_transfer_allocation_amount` CHECK ((`allocated_amount` > 0)),
  CONSTRAINT `chk_staff_transfer_allocation_inference_review` CHECK (((`allocation_method` <> _utf8mb4'inferred') or (`review_status` <> _utf8mb4'approved')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_transportation` (
  `staff_id` int NOT NULL,
  `vehicle_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '交通工具 (機車/轎車)',
  PRIMARY KEY (`staff_id`,`vehicle_type`),
  CONSTRAINT `staff_transportation_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `staff_weekly_rest` (
  `staff_id` int NOT NULL,
  `rest_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '放假類型 (連續服務/週休1日/週休2日/其他)',
  `custom_rest_detail` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他週間服務的補充說明',
  PRIMARY KEY (`staff_id`,`rest_type`),
  CONSTRAINT `staff_weekly_rest_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `subsidy_claim_batch_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `case_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `claimed_hours` decimal(10,2) NOT NULL DEFAULT '0.00',
  `unit_price` decimal(10,2) NOT NULL DEFAULT '0.00',
  `requested_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '建立批次時凍結，不由核准或撥款流程覆寫',
  `approved_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `paid_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_subsidy_claim_batch_assignment` (`batch_id`,`assignment_id`),
  UNIQUE KEY `uq_subsidy_claim_item_id_batch` (`id`,`batch_id`),
  KEY `idx_subsidy_claim_batch_item_case` (`case_no`),
  KEY `idx_subsidy_claim_batch_item_staff` (`staff_id`),
  KEY `fk_subsidy_claim_batch_item_assignment` (`assignment_id`),
  CONSTRAINT `fk_subsidy_claim_batch_item_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_subsidy_claim_batch_item_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_subsidy_claim_batch_item_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_subsidy_claim_batch_item_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_subsidy_claim_batch_item_values` CHECK (((`claimed_hours` >= 0) and (`unit_price` >= 0) and (`requested_amount` >= 0) and (`approved_amount` >= 0) and (`paid_amount` >= 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `subsidy_claim_batches` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `application_year` smallint unsigned NOT NULL,
  `quarter` tinyint unsigned NOT NULL,
  `revision` int unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
  `requested_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '送件時凍結的批次申請總額',
  `approved_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '政府核准總額，不覆寫申請總額',
  `paid_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '銀行撥款分配總額，不覆寫申請或核准總額',
  `submitted_at` datetime DEFAULT NULL,
  `approved_at` datetime DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_subsidy_claim_batch_revision` (`application_year`,`quarter`,`revision`),
  KEY `idx_subsidy_claim_batch_status` (`application_year`,`quarter`,`status`),
  CONSTRAINT `chk_subsidy_claim_batch_amounts` CHECK (((`requested_amount` >= 0) and (`approved_amount` >= 0) and (`paid_amount` >= 0))),
  CONSTRAINT `chk_subsidy_claim_batch_quarter` CHECK ((`quarter` between 1 and 4)),
  CONSTRAINT `chk_subsidy_claim_batch_revision` CHECK ((`revision` >= 1)),
  CONSTRAINT `chk_subsidy_claim_batch_state_times` CHECK ((((`status` = _utf8mb4'draft') and (`submitted_at` is null) and (`approved_at` is null)) or ((`status` = _utf8mb4'submitted') and (`submitted_at` is not null) and (`approved_at` is null)) or ((`status` in (_utf8mb4'approved',_utf8mb4'partially_paid',_utf8mb4'paid')) and (`submitted_at` is not null) and (`approved_at` is not null)))),
  CONSTRAINT `chk_subsidy_claim_batch_year` CHECK ((`application_year` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `system_alerts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `alert_code` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '異常代碼，例如 IMPORT-001, ORDER-001',
  `source_domain` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '來源領域',
  `case_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '案件識別鍵：正常為 case_no，查無案號時用 error_姓名_行動電話',
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '人類可讀的簡述',
  `details` json NOT NULL COMMENT '目前偵測到的異常內容，每次掃描直接覆蓋更新',
  `status` enum('open','claimed','resolved') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open' COMMENT '處理狀態',
  `claimed_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '認領人員',
  `claimed_at` datetime DEFAULT NULL COMMENT '認領時間',
  `resolved_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '處理人員',
  `resolved_at` datetime DEFAULT NULL COMMENT '排除時間',
  `resolution_reason` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '處理原因',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_alert_case` (`alert_code`,`case_key`),
  KEY `idx_system_alert_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `weekly_report_metrics` (
  `week_start_date` date NOT NULL,
  `promotion_count` int DEFAULT NULL,
  `inquiry_count` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`week_start_date`),
  CONSTRAINT `chk_weekly_report_metrics_inquiry_nonnegative` CHECK (((`inquiry_count` is null) or (`inquiry_count` >= 0))),
  CONSTRAINT `chk_weekly_report_metrics_promotion_nonnegative` CHECK (((`promotion_count` is null) or (`promotion_count` >= 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `accounting_pricing_state` (`singleton_id`,`revision`) VALUES (1,0);

INSERT INTO `client_subsidy_policy_migrations` (`policy_key`) VALUES ('subsidy-period-policy-2026-10-24-v1');

INSERT INTO `finance_statement_archive_state` (`id`,`version`) VALUES (1,0);

INSERT INTO `government_payers` (`payer_identity`,`payer_name`,`incoming_memo_match`,`is_active`) VALUES ('hccg','新竹市政府','新竹市政府',1);

INSERT INTO `payroll_rate_policies` (`policy_version`,`policy_kind`,`hourly_rate_ntd`,`effective_from`,`effective_until`) VALUES ('approved-rates-v1','citizen',300,'1900-01-01',NULL);

INSERT INTO `payroll_rate_policies` (`policy_version`,`policy_kind`,`hourly_rate_ntd`,`effective_from`,`effective_until`) VALUES ('approved-rates-v1','non_citizen',320,'1900-01-01',NULL);

INSERT INTO `payroll_rate_policies` (`policy_version`,`policy_kind`,`hourly_rate_ntd`,`effective_from`,`effective_until`) VALUES ('approved-rates-v1','subsidized_citizen',350,'1900-01-01',NULL);

INSERT INTO `payroll_rate_policies` (`policy_version`,`policy_kind`,`hourly_rate_ntd`,`effective_from`,`effective_until`) VALUES ('approved-rates-v1','twins',450,'1900-01-01',NULL);

INSERT INTO `staff_matching_preference_definitions` (`id`,`preference_key`,`display_name`,`value_kind`,`is_filterable`,`order_fact_key`,`comparison_operator`,`status`,`version`,`created_by`,`updated_by`) VALUES (2,'daily_service_hours','可承接每日服務時數','integer_set',1,'service_hours_per_day','contains_integer','active',1,'wp72','wp72');

INSERT INTO `staff_matching_preference_definitions` (`id`,`preference_key`,`display_name`,`value_kind`,`is_filterable`,`order_fact_key`,`comparison_operator`,`status`,`version`,`created_by`,`updated_by`) VALUES (1,'preferred_service_days','可承接服務天數','integer_range',1,'service_days','range_with_tolerance','active',1,'wp72','wp72');

DELIMITER $$
CREATE TRIGGER `trg_anomaly_workflow_events_before_delete` BEFORE DELETE ON `anomaly_workflow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_anomaly_workflow_events_before_update` BEFORE UPDATE ON `anomaly_workflow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_application_command_claims_before_delete` BEFORE DELETE ON `application_command_claims` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_application_command_claims_before_update` BEFORE UPDATE ON `application_command_claims` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_plan_receipts_before_delete` BEFORE DELETE ON `assignment_plan_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_plan_receipts_before_update` BEFORE UPDATE ON `assignment_plan_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_schedule_leave_substitution_batches_before_delete` BEFORE DELETE ON `assignment_schedule_leave_substitution_batches` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_schedule_leave_substitution_batches_before_update` BEFORE UPDATE ON `assignment_schedule_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_schedule_leave_substitution_events_before_delete` BEFORE DELETE ON `assignment_schedule_leave_substitution_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_assignment_schedule_leave_substitution_events_before_update` BEFORE UPDATE ON `assignment_schedule_leave_substitution_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_record_correction_events_before_delete` BEFORE DELETE ON `beclass_record_correction_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `beclass_records` r31 WHERE ((r31.`bound_case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND r31.`client_id`=@registry_delete_client))) AND OLD.`beclass_record_id`=r31.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'beclass correction events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_record_correction_events_before_update` BEFORE UPDATE ON `beclass_record_correction_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'beclass correction events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_events_before_delete` BEFORE DELETE ON `beclass_import_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_events_before_update` BEFORE UPDATE ON `beclass_import_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_receipts_before_delete` BEFORE DELETE ON `beclass_import_review_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_receipts_before_update` BEFORE UPDATE ON `beclass_import_review_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_rows_before_delete` BEFORE DELETE ON `beclass_import_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_beclass_review_rows_before_update` BEFORE UPDATE ON `beclass_import_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_locks_before_delete` BEFORE DELETE ON `caregiver_availability_locks` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`plan_id`=r40.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_locks records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_locks_before_update` BEFORE UPDATE ON `caregiver_availability_locks` FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.plan_id <=> NEW.plan_id AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_lock_days_before_delete` BEFORE DELETE ON `caregiver_availability_lock_days` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_availability_locks` r34 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r34.`plan_id`=r40.`id`))) AND OLD.`lock_id`=r34.`id`) OR EXISTS(SELECT 1 FROM `caregiver_matching_plan_segments` r39 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r39.`plan_id`=r40.`id`))) AND OLD.`segment_id`=r39.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_days records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_lock_days_before_update` BEFORE UPDATE ON `caregiver_availability_lock_days` FOR EACH ROW SET NEW.lock_id = IF(OLD.id <=> NEW.id AND OLD.lock_id <=> NEW.lock_id AND OLD.segment_id <=> NEW.segment_id AND OLD.staff_id <=> NEW.staff_id AND OLD.lock_date <=> NEW.lock_date AND OLD.created_at <=> NEW.created_at, NEW.lock_id, NULL)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_lock_events_before_delete` BEFORE DELETE ON `caregiver_availability_lock_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_availability_locks` r34 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r34.`plan_id`=r40.`id`))) AND OLD.`lock_id`=r34.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_availability_lock_events_before_update` BEFORE UPDATE ON `caregiver_availability_lock_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plans_before_delete` BEFORE DELETE ON `caregiver_matching_plans` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plans records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plans_before_update` BEFORE UPDATE ON `caregiver_matching_plans` FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.case_no <=> NEW.case_no AND OLD.version <=> NEW.version AND OLD.start_date <=> NEW.start_date AND OLD.end_date <=> NEW.end_date AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plan_events_before_delete` BEFORE DELETE ON `caregiver_matching_plan_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`plan_id`=r40.`id`) OR EXISTS(SELECT 1 FROM `caregiver_matching_plan_segments` r39 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r39.`plan_id`=r40.`id`))) AND OLD.`segment_id`=r39.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plan_events_before_update` BEFORE UPDATE ON `caregiver_matching_plan_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plan_segments_before_delete` BEFORE DELETE ON `caregiver_matching_plan_segments` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`plan_id`=r40.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_caregiver_matching_plan_segments_before_update` BEFORE UPDATE ON `caregiver_matching_plan_segments` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_architecture_bootstrap_events_before_delete` BEFORE DELETE ON `case_architecture_bootstrap_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_architecture_bootstrap_events_before_update` BEFORE UPDATE ON `case_architecture_bootstrap_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_architecture_bootstrap_receipts_before_delete` BEFORE DELETE ON `case_architecture_bootstrap_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_architecture_bootstrap_receipts_before_update` BEFORE UPDATE ON `case_architecture_bootstrap_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_events_before_delete` BEFORE DELETE ON `case_import_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND OLD.`client_id`=@registry_delete_client)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_import_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_events_before_update` BEFORE UPDATE ON `case_import_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_hcm_review_rows_before_delete` BEFORE DELETE ON `case_import_hcm_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_hcm_review_rows_before_update` BEFORE UPDATE ON `case_import_hcm_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_rows records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_receipts_before_delete` BEFORE DELETE ON `case_import_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND OLD.`client_id`=@registry_delete_client)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_import_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_import_receipts_before_update` BEFORE UPDATE ON `case_import_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_payroll_policy_snapshots_before_delete` BEFORE DELETE ON `case_payroll_rate_policy_snapshots` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_payroll_policy_snapshots_before_update` BEFORE UPDATE ON `case_payroll_rate_policy_snapshots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_staff_assignments_original_period_insert` BEFORE INSERT ON `case_staff_assignments` FOR EACH ROW SET NEW.original_assigned_start_date = COALESCE(NEW.original_assigned_start_date, NEW.assigned_start_date),
    NEW.original_assigned_end_date = COALESCE(NEW.original_assigned_end_date, NEW.assigned_end_date)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_case_staff_assignments_original_period_update` BEFORE UPDATE ON `case_staff_assignments` FOR EACH ROW SET NEW.original_assigned_start_date = OLD.original_assigned_start_date,
    NEW.original_assigned_end_date = OLD.original_assigned_end_date$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_deposit_reversal_receipts_before_delete` BEFORE DELETE ON `client_deposit_reversal_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_deposit_reversal_receipts_before_update` BEFORE UPDATE ON `client_deposit_reversal_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_deposit_reversal_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_finance_receipts_before_delete` BEFORE DELETE ON `client_finance_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_finance_receipts_before_update` BEFORE UPDATE ON `client_finance_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_ledger_allocations_before_delete` BEFORE DELETE ON `client_ledger_obligation_allocations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_ledger_entries` r59 WHERE ((r59.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`ledger_entry_id`=r59.`id`) OR EXISTS(SELECT 1 FROM `client_obligations` r63 WHERE ((r63.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r63.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client ledger allocations cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_ledger_allocations_before_update` BEFORE UPDATE ON `client_ledger_obligation_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_ledger_entries_before_delete` BEFORE DELETE ON `client_ledger_entries` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_ledger_entries records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_ledger_entries_before_update` BEFORE UPDATE ON `client_ledger_entries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_obligation_events_before_delete` BEFORE DELETE ON `client_obligation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_obligation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_obligation_events_before_update` BEFORE UPDATE ON `client_obligation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND NEW.`source_obligation_identity` IS NULL AND NEW.`id` <=> OLD.`id` AND NEW.`obligation_identity` <=> OLD.`obligation_identity` AND NEW.`case_no` <=> OLD.`case_no` AND NEW.`obligation_type` <=> OLD.`obligation_type` AND NEW.`direction` <=> OLD.`direction` AND NEW.`event_type` <=> OLD.`event_type` AND NEW.`before_amount_ntd` <=> OLD.`before_amount_ntd` AND NEW.`after_amount_ntd` <=> OLD.`after_amount_ntd` AND NEW.`before_due_date` <=> OLD.`before_due_date` AND NEW.`after_due_date` <=> OLD.`after_due_date` AND NEW.`source_event_identity` <=> OLD.`source_event_identity` AND NEW.`expected_account_version` <=> OLD.`expected_account_version` AND NEW.`idempotency_key` <=> OLD.`idempotency_key` AND NEW.`actor` <=> OLD.`actor` AND NEW.`reason` <=> OLD.`reason` AND NEW.`created_at` <=> OLD.`created_at`),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_obligation_events records cannot be updated'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_adjustment_receipts_before_delete` BEFORE DELETE ON `client_over_refund_recovery_adjustment_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_over_refund_recoveries` r64 WHERE ((r64.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`recovery_identity`=r64.`recovery_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_adjustment_receipts_before_update` BEFORE UPDATE ON `client_over_refund_recovery_adjustment_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund adjustment receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_recovery_events_before_delete` BEFORE DELETE ON `client_over_refund_recovery_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_ledger_entries` r59 WHERE ((r59.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`receipt_ledger_entry_id`=r59.`id`) OR EXISTS(SELECT 1 FROM `client_over_refund_recoveries` r64 WHERE ((r64.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`recovery_identity`=r64.`recovery_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_recovery_events_before_update` BEFORE UPDATE ON `client_over_refund_recovery_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_over_refund_recovery_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_recovery_receipts_before_delete` BEFORE DELETE ON `client_over_refund_recovery_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_ledger_entries` r59 WHERE ((r59.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`receipt_ledger_entry_id`=r59.`id`) OR EXISTS(SELECT 1 FROM `client_over_refund_recoveries` r64 WHERE ((r64.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`recovery_identity`=r64.`recovery_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_over_refund_recovery_receipts_before_update` BEFORE UPDATE ON `client_over_refund_recovery_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_destination_events_before_delete` BEFORE DELETE ON `client_payment_destination_configuration_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination events are immutable'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_destination_events_before_update` BEFORE UPDATE ON `client_payment_destination_configuration_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination events are immutable'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_destination_receipts_before_delete` BEFORE DELETE ON `client_payment_destination_configuration_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination receipts are immutable'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_destination_receipts_before_update` BEFORE UPDATE ON `client_payment_destination_configuration_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client payment destination receipts are immutable'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_terms_events_before_delete` BEFORE DELETE ON `client_payment_terms_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_payment_terms_events_before_update` BEFORE UPDATE ON `client_payment_terms_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_profile_admin_change_events_before_delete` BEFORE DELETE ON `client_profile_admin_change_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND (((@registry_delete_client_owned AND OLD.`client_id`=@registry_delete_client)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client profile admin events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_profile_admin_change_events_before_update` BEFORE UPDATE ON `client_profile_admin_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client profile admin events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_profile_change_events_before_delete` BEFORE DELETE ON `client_profile_change_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND (((@registry_delete_client_owned AND OLD.`client_id`=@registry_delete_client)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_profile_change_events_before_update` BEFORE UPDATE ON `client_profile_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client profile change events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_receipt_overage_dispositions_before_delete` BEFORE DELETE ON `client_receipt_overage_dispositions` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_receipt_overage_dispositions_before_update` BEFORE UPDATE ON `client_receipt_overage_dispositions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_receipt_overage_dispositions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_recovery_matchings_before_delete` BEFORE DELETE ON `client_over_refund_recovery_matchings` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_recovery_matchings_before_update` BEFORE UPDATE ON `client_over_refund_recovery_matchings` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matchings cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_recovery_matching_receipts_before_delete` BEFORE DELETE ON `client_over_refund_recovery_matching_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_over_refund_recovery_matchings` r69 WHERE ((r69.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`matching_identity`=r69.`matching_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_recovery_matching_receipts_before_update` BEFORE UPDATE ON `client_over_refund_recovery_matching_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client over-refund recovery matching receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_recipient_snapshots_before_delete` BEFORE DELETE ON `client_refund_recipient_snapshots` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_recipient_snapshots_before_update` BEFORE UPDATE ON `client_refund_recipient_snapshots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund recipient snapshots cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_return_review_event_before_delete` BEFORE DELETE ON `client_refund_return_review_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund return review events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_return_review_event_before_update` BEFORE UPDATE ON `client_refund_return_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_return_review_receipt_before_delete` BEFORE DELETE ON `client_refund_return_review_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_refund_return_review_events` r84 WHERE ((r84.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`review_event_id`=r84.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund return review receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_return_review_receipt_before_update` BEFORE UPDATE ON `client_refund_return_review_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund return review receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_reversal_receipt_before_delete` BEFORE DELETE ON `client_refund_reversal_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund reversal receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_reversal_receipt_before_update` BEFORE UPDATE ON `client_refund_reversal_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_sources_before_delete` BEFORE DELETE ON `client_refund_underpayment_sources` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund underpayment sources cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_sources_before_update` BEFORE UPDATE ON `client_refund_underpayment_sources` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment sources cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_source_obligations_before_delete` BEFORE DELETE ON `client_refund_underpayment_source_obligations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_obligations` r63 WHERE ((r63.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`refund_obligation_identity`=r63.`obligation_identity`) OR EXISTS(SELECT 1 FROM `client_refund_underpayment_sources` r89 WHERE ((r89.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`underpayment_identity`=r89.`underpayment_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_source_obligations_before_update` BEFORE UPDATE ON `client_refund_underpayment_source_obligations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source obligations cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_source_rows_before_delete` BEFORE DELETE ON `client_refund_underpayment_source_bank_rows` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `client_refund_underpayment_sources` r89 WHERE ((r89.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`underpayment_identity`=r89.`underpayment_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_refund_underpayment_source_rows_before_update` BEFORE UPDATE ON `client_refund_underpayment_source_bank_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund underpayment source bank rows cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_subsidy_advance_recovery_before_delete` BEFORE DELETE ON `client_subsidy_advance_recoveries` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_subsidy_advance_recovery_before_update` BEFORE UPDATE ON `client_subsidy_advance_recoveries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_subsidy_return_claim_item_link_before_delete` BEFORE DELETE ON `client_subsidy_return_claim_item_links` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `subsidy_claim_batch_items` r385 WHERE ((r385.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`claim_item_id`=r385.`id`) OR EXISTS(SELECT 1 FROM `client_obligations` r63 WHERE ((r63.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r63.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_client_subsidy_return_claim_item_link_before_update` BEFORE UPDATE ON `client_subsidy_return_claim_item_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_document_versions_before_delete` BEFORE DELETE ON `contract_document_versions` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_document_versions_before_update` BEFORE UPDATE ON `contract_document_versions` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_document_versions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_external_receipts_before_delete` BEFORE DELETE ON `contract_external_signing_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `contract_final_document_versions` r103 WHERE ((r103.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`final_document_version_id`=r103.`id`) OR EXISTS(SELECT 1 FROM `contract_external_completion_reports` r100 WHERE ((r100.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`completion_report_id`=r100.`id`) OR EXISTS(SELECT 1 FROM `contract_external_signing_sessions` r102 WHERE ((r102.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`external_signing_session_id`=r102.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_signing_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_external_receipts_before_update` BEFORE UPDATE ON `contract_external_signing_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_signing_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_external_reports_before_delete` BEFORE DELETE ON `contract_external_completion_reports` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_completion_reports records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_external_reports_before_update` BEFORE UPDATE ON `contract_external_completion_reports` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_external_completion_reports records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_final_documents_before_delete` BEFORE DELETE ON `contract_final_document_versions` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_final_document_versions records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_final_documents_before_update` BEFORE UPDATE ON `contract_final_document_versions` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_final_document_versions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_signing_events_before_delete` BEFORE DELETE ON `contract_signing_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_contract_signing_events_before_update` BEFORE UPDATE ON `contract_signing_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'contract_signing_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_apply_receipts_before_delete` BEFORE DELETE ON `controlled_file_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `controlled_file_objects` r112 WHERE (((r112.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r112.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`controlled_object_id`=r112.`id`) OR EXISTS(SELECT 1 FROM `controlled_file_staging_objects` r115 WHERE (((r115.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r115.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`staging_object_id`=r115.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_apply_receipts_before_update` BEFORE UPDATE ON `controlled_file_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_cleanup_events_before_delete` BEFORE DELETE ON `controlled_file_cleanup_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `controlled_file_staging_objects` r115 WHERE (((r115.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r115.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`staging_object_id`=r115.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_cleanup_events_before_update` BEFORE UPDATE ON `controlled_file_cleanup_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_cleanup_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_objects_before_delete` BEFORE DELETE ON `controlled_file_objects` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND (((OLD.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND OLD.`owner_type` IN ('orders','scheduling','contract_signing'))))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_objects_before_update` BEFORE UPDATE ON `controlled_file_objects` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_objects records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_reconciliation_events_before_delete` BEFORE DELETE ON `controlled_file_reconciliation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `controlled_file_objects` r112 WHERE (((r112.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r112.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`controlled_object_id`=r112.`id`) OR EXISTS(SELECT 1 FROM `controlled_file_staging_objects` r115 WHERE (((r115.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r115.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`staging_object_id`=r115.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_reconciliation_events_before_update` BEFORE UPDATE ON `controlled_file_reconciliation_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_reconciliation_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_references_before_delete` BEFORE DELETE ON `controlled_file_references` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `scheduling_service_day_log_attachments` r323 WHERE ((EXISTS(SELECT 1 FROM `controlled_file_objects` r112 WHERE (((r112.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r112.`owner_type` IN ('orders','scheduling','contract_signing')))) AND r323.`controlled_file_object_id`=r112.`id`) OR EXISTS(SELECT 1 FROM `scheduling_service_day_logs` r326 WHERE ((r326.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r323.`service_day_log_id`=r326.`id`))) AND OLD.`service_day_log_attachment_id`=r323.`id`) OR EXISTS(SELECT 1 FROM `controlled_file_objects` r112 WHERE (((r112.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r112.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`controlled_file_object_id`=r112.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'controlled_file_references cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_controlled_file_references_before_update` BEFORE UPDATE ON `controlled_file_references` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'controlled_file_references cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_customer_service_escalation_events_before_delete` BEFORE DELETE ON `customer_service_escalation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `customer_service_escalations` r118 WHERE ((EXISTS(SELECT 1 FROM `customer_service_tickets` r120 WHERE ((r120.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND r120.`client_id`=@registry_delete_client))) AND r118.`ticket_id`=r120.`id`))) AND OLD.`escalation_id`=r118.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_customer_service_escalation_events_before_update` BEFORE UPDATE ON `customer_service_escalation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'customer_service_escalation_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_anomaly_occurrences_before_delete` BEFORE DELETE ON `finance_anomaly_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_anomaly_occurrences_before_update` BEFORE UPDATE ON `finance_anomaly_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_apply_receipt_before_delete` BEFORE DELETE ON `finance_import_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_apply_receipt_before_update` BEFORE UPDATE ON `finance_import_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_classification_before_delete` BEFORE DELETE ON `finance_import_classification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_classification_before_update` BEFORE UPDATE ON `finance_import_classification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_correction_receipt_before_delete` BEFORE DELETE ON `finance_import_correction_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_correction_receipt_before_update` BEFORE UPDATE ON `finance_import_correction_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_dispatch_before_delete` BEFORE DELETE ON `finance_import_dispatch_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_dispatch_before_update` BEFORE UPDATE ON `finance_import_dispatch_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_historical_reprocess_receipt_before_delete` BEFORE DELETE ON `finance_import_historical_reprocess_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_historical_reprocess_receipt_before_update` BEFORE UPDATE ON `finance_import_historical_reprocess_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_ingestion_attempt_before_delete` BEFORE DELETE ON `finance_import_ingestion_attempts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_ingestion_attempt_before_update` BEFORE UPDATE ON `finance_import_ingestion_attempts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_attempts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_ingestion_receipt_before_delete` BEFORE DELETE ON `finance_import_ingestion_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_ingestion_receipt_before_update` BEFORE UPDATE ON `finance_import_ingestion_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_integrity_before_delete` BEFORE DELETE ON `finance_import_integrity_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_integrity_before_update` BEFORE UPDATE ON `finance_import_integrity_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_reconciliation_before_delete` BEFORE DELETE ON `finance_import_reconciliation_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_reconciliation_before_update` BEFORE UPDATE ON `finance_import_reconciliation_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_reprocess_runs_before_delete` BEFORE DELETE ON `finance_import_reprocess_runs` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_reprocess_runs_before_update` BEFORE UPDATE ON `finance_import_reprocess_runs` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_source_reviews_before_delete` BEFORE DELETE ON `finance_import_source_reviews` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_import_source_reviews_before_update` BEFORE UPDATE ON `finance_import_source_reviews` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_reviews cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_source_review_occurrences_before_delete` BEFORE DELETE ON `finance_import_source_review_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_finance_source_review_occurrences_before_update` BEFORE UPDATE ON `finance_import_source_review_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_source_review_occurrences cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustments_before_delete` BEFORE DELETE ON `financial_adjustments` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'financial adjustments cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustments_before_update` BEFORE UPDATE ON `financial_adjustments` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustment_receipt_before_delete` BEFORE DELETE ON `financial_adjustment_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'financial adjustment receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustment_receipt_before_update` BEFORE UPDATE ON `financial_adjustment_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustment_staff_before_delete` BEFORE DELETE ON `financial_adjustment_staff_allocations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `financial_adjustments` r147 WHERE ((r147.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`financial_adjustment_id`=r147.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_financial_adjustment_staff_before_update` BEFORE UPDATE ON `financial_adjustment_staff_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_overpayment_apply_receipts_before_delete` BEFORE DELETE ON `government_subsidy_overpayment_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_overpayment_apply_receipts_before_update` BEFORE UPDATE ON `government_subsidy_overpayment_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_allocations_before_delete` BEFORE DELETE ON `government_subsidy_allocations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `subsidy_claim_batch_items` r385 WHERE ((r385.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`claim_item_id`=r385.`id` AND OLD.`claim_batch_id`=r385.`batch_id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_allocations_before_update` BEFORE UPDATE ON `government_subsidy_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_approval_before_delete` BEFORE DELETE ON `government_subsidy_claim_approval_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_approval_before_update` BEFORE UPDATE ON `government_subsidy_claim_approval_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_approval_item_before_delete` BEFORE DELETE ON `government_subsidy_claim_approval_items` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `subsidy_claim_batch_items` r385 WHERE ((r385.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`claim_item_id`=r385.`id` AND OLD.`batch_id`=r385.`batch_id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'government subsidy approval item cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_approval_item_before_update` BEFORE UPDATE ON `government_subsidy_claim_approval_items` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_claim_receipt_before_delete` BEFORE DELETE ON `government_subsidy_claim_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_claim_receipt_before_update` BEFORE UPDATE ON `government_subsidy_claim_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_overpayment_events_before_delete` BEFORE DELETE ON `government_subsidy_overpayment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_overpayment_events_before_update` BEFORE UPDATE ON `government_subsidy_overpayment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_overpayment_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_projection_events_before_delete` BEFORE DELETE ON `government_subsidy_projection_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_projection_events_before_update` BEFORE UPDATE ON `government_subsidy_projection_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_receipts_before_delete` BEFORE DELETE ON `government_subsidy_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_receipts_before_update` BEFORE UPDATE ON `government_subsidy_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_submission_before_delete` BEFORE DELETE ON `government_subsidy_claim_submission_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_submission_before_update` BEFORE UPDATE ON `government_subsidy_claim_submission_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_transactions_before_delete` BEFORE DELETE ON `government_subsidy_transactions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_government_subsidy_transactions_before_update` BEFORE UPDATE ON `government_subsidy_transactions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_correction_events_before_delete` BEFORE DELETE ON `case_import_hcm_correction_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND OLD.`client_id`=@registry_delete_client)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_correction_events_before_update` BEFORE UPDATE ON `case_import_hcm_correction_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_correction_receipts_before_delete` BEFORE DELETE ON `case_import_hcm_correction_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_import_hcm_correction_events` r44 WHERE ((r44.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) OR (@registry_delete_client_owned AND r44.`client_id`=@registry_delete_client))) AND OLD.`correction_event_id`=r44.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_correction_receipts_before_update` BEFORE UPDATE ON `case_import_hcm_correction_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_correction_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_review_case_bindings_before_delete` BEFORE DELETE ON `case_import_hcm_review_case_bindings` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_hcm_review_case_bindings_before_update` BEFORE UPDATE ON `case_import_hcm_review_case_bindings` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_hcm_review_case_bindings cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_client_payment_events_before_delete` BEFORE DELETE ON `historical_client_payment_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_client_payment_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_client_payment_events_before_update` BEFORE UPDATE ON `historical_client_payment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_client_payment_links_before_delete` BEFORE DELETE ON `historical_client_payment_obligation_links` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_client_payment_events` r168 WHERE ((r168.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`event_id`=r168.`id`) OR EXISTS(SELECT 1 FROM `client_obligations` r63 WHERE ((r63.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r63.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_client_payment_obligation_links records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_client_payment_links_before_update` BEFORE UPDATE ON `historical_client_payment_obligation_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_client_payment_obligation_links records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_events_before_delete` BEFORE DELETE ON `historical_order_operational_baseline_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_operational_baseline_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_events_before_update` BEFORE UPDATE ON `historical_order_operational_baseline_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_outbox_before_delete` BEFORE DELETE ON `historical_order_operational_baseline_outbox` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_order_operational_baseline_events` r175 WHERE ((r175.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`event_id`=r175.`id`) OR EXISTS(SELECT 1 FROM `historical_order_operational_baseline_receipts` r177 WHERE ((EXISTS(SELECT 1 FROM `historical_order_operational_baseline_events` r175 WHERE ((r175.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r177.`event_id`=r175.`id`))) AND OLD.`receipt_id`=r177.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_operational_baseline_outbox records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_outbox_before_update` BEFORE UPDATE ON `historical_order_operational_baseline_outbox` FOR EACH ROW SET NEW.event_id = IF(
    OLD.id <=> NEW.id
    AND OLD.event_id <=> NEW.event_id
    AND OLD.receipt_id <=> NEW.receipt_id
    AND OLD.intent_key <=> NEW.intent_key
    AND OLD.intent_type <=> NEW.intent_type
    AND OLD.bounded_snapshot <=> NEW.bounded_snapshot
    AND OLD.created_at <=> NEW.created_at,
    NEW.event_id,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_receipts_before_delete` BEFORE DELETE ON `historical_order_operational_baseline_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_order_operational_baseline_events` r175 WHERE ((r175.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`event_id`=r175.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_operational_baseline_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_operational_baseline_receipts_before_update` BEFORE UPDATE ON `historical_order_operational_baseline_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_operational_baseline_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_adoption_receipts_before_delete` BEFORE DELETE ON `historical_order_adoption_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_adoption_receipts_before_update` BEFORE UPDATE ON `historical_order_adoption_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_adoption_reviews_before_delete` BEFORE DELETE ON `historical_order_adoption_reviews` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_adoption_reviews_before_update` BEFORE UPDATE ON `historical_order_adoption_reviews` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_adoption_reviews records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_pairing_evidence_before_delete` BEFORE DELETE ON `historical_order_pairing_evidence` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `historical_order_adoption_receipts` r173 WHERE ((r173.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`receipt_id`=r173.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_pairing_evidence_before_update` BEFORE UPDATE ON `historical_order_pairing_evidence` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_pairing_evidence records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_review_remediation_events_before_delete` BEFORE DELETE ON `historical_order_review_remediation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_order_adoption_receipts` r173 WHERE ((r173.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`original_adoption_receipt_id`=r173.`id`) OR EXISTS(SELECT 1 FROM `historical_order_adoption_receipts` r173 WHERE ((r173.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`replacement_adoption_receipt_id`=r173.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_review_remediation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_review_remediation_events_before_update` BEFORE UPDATE ON `historical_order_review_remediation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_review_remediation_receipts_before_delete` BEFORE DELETE ON `historical_order_review_remediation_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_order_review_remediation_events` r179 WHERE ((EXISTS(SELECT 1 FROM `historical_order_adoption_receipts` r173 WHERE ((r173.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r179.`original_adoption_receipt_id`=r173.`id`) OR EXISTS(SELECT 1 FROM `historical_order_adoption_receipts` r173 WHERE ((r173.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r179.`replacement_adoption_receipt_id`=r173.`id`))) AND OLD.`event_id`=r179.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_order_review_remediation_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_order_review_remediation_receipts_before_update` BEFORE UPDATE ON `historical_order_review_remediation_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_order_review_remediation_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_owner_selection_before_delete` BEFORE DELETE ON `historical_owner_selection_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_owner_selection_events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_owner_selection_before_update` BEFORE UPDATE ON `historical_owner_selection_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_owner_selection_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_service_day_events_before_delete` BEFORE DELETE ON `historical_service_day_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_service_day_events_before_update` BEFORE UPDATE ON `historical_service_day_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_service_day_items_before_delete` BEFORE DELETE ON `historical_service_day_items` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `historical_service_day_events` r184 WHERE ((r184.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`event_id`=r184.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_items records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_service_day_items_before_update` BEFORE UPDATE ON `historical_service_day_items` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='historical_service_day_items records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_staff_payout_events_before_delete` BEFORE DELETE ON `historical_staff_payout_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_staff_payout_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_staff_payout_events_before_update` BEFORE UPDATE ON `historical_staff_payout_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_staff_payout_links_before_delete` BEFORE DELETE ON `historical_staff_payout_obligation_links` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `historical_staff_payout_events` r187 WHERE ((r187.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`event_id`=r187.`id`) OR EXISTS(SELECT 1 FROM `staff_obligations` r360 WHERE ((r360.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r360.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'historical_staff_payout_obligation_links records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_historical_staff_payout_links_before_update` BEFORE UPDATE ON `historical_staff_payout_obligation_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_staff_payout_obligation_links records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_occurrences_before_delete` BEFORE DELETE ON `import_warning_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_occurrences_before_update` BEFORE UPDATE ON `import_warning_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_occurrences records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_tracking_events_before_delete` BEFORE DELETE ON `import_warning_tracking_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_tracking_events_before_update` BEFORE UPDATE ON `import_warning_tracking_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_tracking_receipts_before_delete` BEFORE DELETE ON `import_warning_tracking_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_import_warning_tracking_receipts_before_update` BEFORE UPDATE ON `import_warning_tracking_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'import_warning_tracking_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_knowledge_item_versions_before_delete` BEFORE DELETE ON `knowledge_item_versions` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_knowledge_item_versions_before_update` BEFORE UPDATE ON `knowledge_item_versions` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_alert_delivery_intents_before_delete` BEFORE DELETE ON `line_alert_delivery_intents` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `line_delivery_tasks` r213 WHERE (((r213.`source_aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r213.`source_aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll')) OR JSON_CONTAINS(@registry_delete_tasks,CAST(r213.id AS JSON)))) AND OLD.`delivery_task_id`=r213.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_alert_delivery_intents_before_update` BEFORE UPDATE ON `line_alert_delivery_intents` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_alert_delivery_intents records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_command_receipts_before_delete` BEFORE DELETE ON `line_command_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_command_receipts_before_update` BEFORE UPDATE ON `line_command_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_command_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_configuration_revisions_before_delete` BEFORE DELETE ON `line_configuration_revisions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_configuration_revisions_before_update` BEFORE UPDATE ON `line_configuration_revisions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_configuration_revisions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_delivery_attempt_events_before_delete` BEFORE DELETE ON `line_delivery_attempt_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `line_delivery_tasks` r213 WHERE (((r213.`source_aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r213.`source_aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll')) OR JSON_CONTAINS(@registry_delete_tasks,CAST(r213.id AS JSON)))) AND OLD.`task_id`=r213.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_delivery_attempt_events_before_update` BEFORE UPDATE ON `line_delivery_attempt_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_domain_audit_events_before_delete` BEFORE DELETE ON `line_domain_audit_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND (((OLD.`aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND OLD.`aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll'))))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_domain_audit_events_before_update` BEFORE UPDATE ON `line_domain_audit_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_domain_audit_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_friend_state_events_before_delete` BEFORE DELETE ON `line_friend_state_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_friend_state_events_before_update` BEFORE UPDATE ON `line_friend_state_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_friend_state_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_notification_decisions_before_delete` BEFORE DELETE ON `line_notification_decisions` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `line_notification_source_events` r227 WHERE (((r227.`source_aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r227.`source_aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll')))) AND OLD.`source_event_id`=r227.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_notification_decisions records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_notification_decisions_before_update` BEFORE UPDATE ON `line_notification_decisions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_decisions records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_notification_source_events_before_delete` BEFORE DELETE ON `line_notification_source_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND (((OLD.`source_aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND OLD.`source_aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll'))))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_notification_source_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_notification_source_events_before_update` BEFORE UPDATE ON `line_notification_source_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_notification_source_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_order_group_binding_events_before_delete` BEFORE DELETE ON `line_order_group_binding_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_order_group_binding_events_before_update` BEFORE UPDATE ON `line_order_group_binding_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_order_group_runtime_events_before_delete` BEFORE DELETE ON `line_order_group_runtime_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_order_group_runtime_events_before_update` BEFORE UPDATE ON `line_order_group_runtime_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_review_decision_events_before_delete` BEFORE DELETE ON `line_review_decision_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `line_review_requests` r234 WHERE (((@registry_delete_client_owned AND r234.`subject_reference`=(CAST(@registry_delete_client AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci) AND r234.`subject_type`='customer'))) AND OLD.`review_request_id`=r234.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_review_decision_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_review_decision_events_before_update` BEFORE UPDATE ON `line_review_decision_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_review_decision_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_cleanup_anomaly_before_delete` BEFORE DELETE ON `line_rich_menu_publication_cleanup_anomalies` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_cleanup_anomaly_before_update` BEFORE UPDATE ON `line_rich_menu_publication_cleanup_anomalies` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_cleanup_anomalies records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_ack_before_delete` BEFORE DELETE ON `line_rich_menu_publication_step_acknowledgements` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_ack_before_update` BEFORE UPDATE ON `line_rich_menu_publication_step_acknowledgements` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_acknowledgements records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_attempt_before_delete` BEFORE DELETE ON `line_rich_menu_publication_step_attempt_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_attempt_before_update` BEFORE UPDATE ON `line_rich_menu_publication_step_attempt_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_attempt_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_receipts_before_delete` BEFORE DELETE ON `line_rich_menu_publication_step_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_rich_menu_step_receipts_before_update` BEFORE UPDATE ON `line_rich_menu_publication_step_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_links_before_delete` BEFORE DELETE ON `line_safe_review_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_links records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_events_before_delete` BEFORE DELETE ON `line_safe_review_link_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_events_before_update` BEFORE UPDATE ON `line_safe_review_link_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_outbox_before_delete` BEFORE DELETE ON `line_safe_review_link_outbox` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_outbox records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_outbox_before_update` BEFORE UPDATE ON `line_safe_review_link_outbox` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_outbox records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_receipts_before_delete` BEFORE DELETE ON `line_safe_review_link_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_safe_review_link_receipts_before_update` BEFORE UPDATE ON `line_safe_review_link_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_safe_review_link_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_webhook_security_receipts_before_delete` BEFORE DELETE ON `line_webhook_security_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_line_webhook_security_receipts_before_update` BEFORE UPDATE ON `line_webhook_security_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_webhook_security_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_apply_receipts_before_delete` BEFORE DELETE ON `matching_coordination_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_apply_receipts_before_update` BEFORE UPDATE ON `matching_coordination_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_coordination_events_before_delete` BEFORE DELETE ON `matching_coordination_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_coordination_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_coordination_events_before_update` BEFORE UPDATE ON `matching_coordination_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_criteria_snapshots_before_delete` BEFORE DELETE ON `matching_coordination_criteria_snapshots` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_criteria_snapshots_before_update` BEFORE UPDATE ON `matching_coordination_criteria_snapshots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_criteria_snapshots records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_outbox_before_delete` BEFORE DELETE ON `matching_coordination_outbox` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_outbox_before_update` BEFORE UPDATE ON `matching_coordination_outbox` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_outbox records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_package_lineage_before_delete` BEFORE DELETE ON `matching_coordination_package_lineage` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_package_lineage_before_update` BEFORE UPDATE ON `matching_coordination_package_lineage` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_coordination_package_lineage records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_plan_create_receipts_before_delete` BEFORE DELETE ON `matching_plan_create_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching plan create receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_plan_create_receipts_before_update` BEFORE UPDATE ON `matching_plan_create_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching plan create receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_response_events_before_delete` BEFORE DELETE ON `matching_response_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`plan_id`=r40.`id`) OR EXISTS(SELECT 1 FROM `caregiver_matching_plan_segments` r39 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r39.`plan_id`=r40.`id`))) AND OLD.`segment_id`=r39.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'matching_response_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_matching_response_events_before_update` BEFORE UPDATE ON `matching_response_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'matching_response_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_actual_start_events_before_delete` BEFORE DELETE ON `order_actual_start_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_actual_start_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_actual_start_events_before_update` BEFORE UPDATE ON `order_actual_start_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_actual_start_receipts_before_delete` BEFORE DELETE ON `order_actual_start_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_actual_start_receipts_before_update` BEFORE UPDATE ON `order_actual_start_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_auto_completion_receipts_before_delete` BEFORE DELETE ON `order_auto_completion_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_auto_completion_receipts_before_update` BEFORE UPDATE ON `order_auto_completion_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_auto_completion_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_cancellation_events_before_delete` BEFORE DELETE ON `order_cancellation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_cancellation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_cancellation_events_before_update` BEFORE UPDATE ON `order_cancellation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_cancellation_receipts_before_delete` BEFORE DELETE ON `order_cancellation_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_cancellation_receipts_before_update` BEFORE UPDATE ON `order_cancellation_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_contract_completion_receipts_before_delete` BEFORE DELETE ON `order_contract_completion_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_contract_completion_receipts_before_update` BEFORE UPDATE ON `order_contract_completion_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_contract_flow_events_before_delete` BEFORE DELETE ON `order_contract_flow_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_contract_flow_events_before_update` BEFORE UPDATE ON `order_contract_flow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_lifecycle_control_events_before_delete` BEFORE DELETE ON `order_lifecycle_control_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_lifecycle_control_events_before_update` BEFORE UPDATE ON `order_lifecycle_control_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_lifecycle_control_state_before_delete` BEFORE DELETE ON `order_lifecycle_control_state` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_lifecycle_control_state records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_lifecycle_state_events_before_delete` BEFORE DELETE ON `order_lifecycle_state_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_lifecycle_state_events_before_update` BEFORE UPDATE ON `order_lifecycle_state_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_reopen_events_before_delete` BEFORE DELETE ON `order_reopen_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_reopen_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_reopen_events_before_update` BEFORE UPDATE ON `order_reopen_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_reopen_receipts_before_delete` BEFORE DELETE ON `order_reopen_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_reopen_receipts_before_update` BEFORE UPDATE ON `order_reopen_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_service_data_locks_before_delete` BEFORE DELETE ON `order_service_data_locks` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_service_data_locks records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_service_data_locks_before_update` BEFORE UPDATE ON `order_service_data_locks` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_terms_apply_receipts_before_delete` BEFORE DELETE ON `order_terms_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_terms_apply_receipts_before_update` BEFORE UPDATE ON `order_terms_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_terms_change_events_before_delete` BEFORE DELETE ON `order_terms_change_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'order_terms_change_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_order_terms_change_events_before_update` BEFORE UPDATE ON `order_terms_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_adjustment_allocations_before_delete` BEFORE DELETE ON `payroll_adjustment_allocations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `payroll_adjustment_events` r287 WHERE ((r287.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`adjustment_event_id`=r287.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_adjustment_allocations_before_update` BEFORE UPDATE ON `payroll_adjustment_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_adjustment_events_before_delete` BEFORE DELETE ON `payroll_adjustment_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_adjustment_events_before_update` BEFORE UPDATE ON `payroll_adjustment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_apply_receipts_before_delete` BEFORE DELETE ON `payroll_apply_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_apply_receipts_before_update` BEFORE UPDATE ON `payroll_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_special_pay_events_before_delete` BEFORE DELETE ON `payroll_special_pay_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_payroll_special_pay_events_before_update` BEFORE UPDATE ON `payroll_special_pay_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitments_before_delete` BEFORE DELETE ON `precontract_service_commitments` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitments_before_update` BEFORE UPDATE ON `precontract_service_commitments` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitments records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitment_days_before_delete` BEFORE DELETE ON `precontract_service_commitment_days` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `precontract_service_commitments` r295 WHERE ((r295.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`commitment_id`=r295.`id`) OR EXISTS(SELECT 1 FROM `caregiver_matching_plan_segments` r39 WHERE ((EXISTS(SELECT 1 FROM `caregiver_matching_plans` r40 WHERE ((r40.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND r39.`plan_id`=r40.`id`))) AND OLD.`matching_segment_id`=r39.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitment_days_before_update` BEFORE UPDATE ON `precontract_service_commitment_days` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_days records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitment_events_before_delete` BEFORE DELETE ON `precontract_service_commitment_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `precontract_service_commitments` r295 WHERE ((r295.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`commitment_id`=r295.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_precontract_service_commitment_events_before_update` BEFORE UPDATE ON `precontract_service_commitment_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'precontract_service_commitment_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_runtime_health_events_before_delete` BEFORE DELETE ON `runtime_health_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_runtime_health_events_before_update` BEFORE UPDATE ON `runtime_health_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'runtime_health_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_bootstrap_review_events_before_delete` BEFORE DELETE ON `scheduling_bootstrap_review_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_bootstrap_review_events_before_update` BEFORE UPDATE ON `scheduling_bootstrap_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_command_receipts_before_delete` BEFORE DELETE ON `scheduling_command_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_command_receipts_before_update` BEFORE UPDATE ON `scheduling_command_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_batches_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_batches` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_batches_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_outcomes_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_outcomes` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `scheduling_leave_substitution_batches` r309 WHERE ((r309.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`batch_key`=r309.`batch_key`) OR EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`original_assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `staff_schedule` r379 WHERE ((r379.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`original_schedule_id`=r379.`id`) OR EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`resulting_assignment_id`=r53.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_outcomes_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_outcomes` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_receipts_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_leave_receipts_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_rebuild_events_before_delete` BEFORE DELETE ON `scheduling_rebuild_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_rebuild_events_before_update` BEFORE UPDATE ON `scheduling_rebuild_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_rebuild_lineage_before_delete` BEFORE DELETE ON `scheduling_rebuild_lineage` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`new_assignment_id`=r53.`id` AND OLD.`new_generation_id`=r53.`generation_id`) OR EXISTS(SELECT 1 FROM `scheduling_rebuild_events` r312 WHERE ((r312.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`rebuild_event_id`=r312.`id` AND OLD.`new_generation_id`=r312.`new_generation_id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_rebuild_lineage_before_update` BEFORE UPDATE ON `scheduling_rebuild_lineage` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_checkpoints_before_delete` BEFORE DELETE ON `scheduling_service_day_checkpoints` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_checkpoints_before_update` BEFORE UPDATE ON `scheduling_service_day_checkpoints` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoints cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_checkpoint_events_before_delete` BEFORE DELETE ON `scheduling_service_day_checkpoint_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `scheduling_service_day_checkpoints` r322 WHERE ((r322.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`checkpoint_id`=r322.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_checkpoint_events_before_update` BEFORE UPDATE ON `scheduling_service_day_checkpoint_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_checkpoint_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_log_attachments_before_delete` BEFORE DELETE ON `scheduling_service_day_log_attachments` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `controlled_file_objects` r112 WHERE (((r112.`subject_reference`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r112.`owner_type` IN ('orders','scheduling','contract_signing')))) AND OLD.`controlled_file_object_id`=r112.`id`) OR EXISTS(SELECT 1 FROM `scheduling_service_day_logs` r326 WHERE ((r326.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`service_day_log_id`=r326.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_log_attachments_before_update` BEFORE UPDATE ON `scheduling_service_day_log_attachments` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_attachments cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_log_events_before_delete` BEFORE DELETE ON `scheduling_service_day_log_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `case_staff_assignments` r53 WHERE ((r53.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`assignment_id`=r53.`id`) OR EXISTS(SELECT 1 FROM `scheduling_service_day_logs` r326 WHERE ((r326.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`service_day_log_id`=r326.`id`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_scheduling_service_day_log_events_before_update` BEFORE UPDATE ON `scheduling_service_day_log_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_day_log_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_events_before_delete` BEFORE DELETE ON `scheduling_service_before_replacement_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_before_replacement_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_events_before_insert` BEFORE INSERT ON `scheduling_service_before_replacement_events` FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM scheduling_generations AS prior_generation
        INNER JOIN scheduling_generations AS replacement_generation
            ON replacement_generation.id = NEW.replacement_generation_id
           AND replacement_generation.case_no = NEW.case_no
        INNER JOIN scheduling_aggregates AS aggregate
            ON aggregate.case_no = NEW.case_no
        WHERE prior_generation.id = NEW.prior_generation_id
          AND prior_generation.case_no = NEW.case_no
          AND prior_generation.generation_number = NEW.expected_generation_version
          AND prior_generation.resulting_aggregate_version = NEW.expected_aggregate_version
          AND replacement_generation.generation_number = NEW.resulting_generation_version
          AND replacement_generation.resulting_aggregate_version = NEW.resulting_aggregate_version
          AND aggregate.generation_counter = NEW.resulting_generation_version
          AND aggregate.aggregate_version = NEW.resulting_aggregate_version
          AND NOT EXISTS (
              SELECT 1
              FROM scheduling_service_day_logs AS service_day_log
              WHERE service_day_log.case_no = NEW.case_no
          )
    ),
    NEW.case_no,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_events_before_update` BEFORE UPDATE ON `scheduling_service_before_replacement_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_outbox_before_delete` BEFORE DELETE ON `scheduling_service_before_replacement_outbox` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_before_replacement_outbox records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_outbox_before_insert` BEFORE INSERT ON `scheduling_service_before_replacement_outbox` FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM scheduling_service_before_replacement_receipts AS receipt
        WHERE receipt.id = NEW.receipt_id
          AND receipt.replacement_event_id = NEW.replacement_event_id
          AND receipt.case_no = NEW.case_no
          AND receipt.outbox_identity = NEW.outbox_identity
    ),
    NEW.case_no,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_outbox_before_update` BEFORE UPDATE ON `scheduling_service_before_replacement_outbox` FOR EACH ROW SET NEW.replacement_event_id = IF(
    OLD.id <=> NEW.id
    AND OLD.replacement_event_id <=> NEW.replacement_event_id
    AND OLD.receipt_id <=> NEW.receipt_id
    AND OLD.case_no <=> NEW.case_no
    AND OLD.outbox_identity <=> NEW.outbox_identity
    AND OLD.intent_type <=> NEW.intent_type
    AND OLD.target_owner <=> NEW.target_owner
    AND OLD.bounded_payload <=> NEW.bounded_payload
    AND OLD.created_at <=> NEW.created_at,
    NEW.replacement_event_id,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_receipts_before_delete` BEFORE DELETE ON `scheduling_service_before_replacement_receipts` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_before_replacement_receipts records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_receipts_before_insert` BEFORE INSERT ON `scheduling_service_before_replacement_receipts` FOR EACH ROW SET NEW.case_no = IF(
    NEW.retained_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS retained_root
        WHERE retained_root.replacement_event_id = NEW.replacement_event_id
          AND retained_root.case_no = NEW.case_no
          AND retained_root.disposition = 'retained'
    )
    AND NEW.retained_root_count = (
        SELECT COALESCE(MAX(retained_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS retained_root
        WHERE retained_root.replacement_event_id = NEW.replacement_event_id
          AND retained_root.case_no = NEW.case_no
          AND retained_root.disposition = 'retained'
    )
    AND NEW.superseded_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS superseded_root
        WHERE superseded_root.replacement_event_id = NEW.replacement_event_id
          AND superseded_root.case_no = NEW.case_no
          AND superseded_root.disposition = 'superseded'
    )
    AND NEW.superseded_root_count = (
        SELECT COALESCE(MAX(superseded_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS superseded_root
        WHERE superseded_root.replacement_event_id = NEW.replacement_event_id
          AND superseded_root.case_no = NEW.case_no
          AND superseded_root.disposition = 'superseded'
    )
    AND NEW.created_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS created_root
        WHERE created_root.replacement_event_id = NEW.replacement_event_id
          AND created_root.case_no = NEW.case_no
          AND created_root.disposition = 'created'
    )
    AND NEW.created_root_count = (
        SELECT COALESCE(MAX(created_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS created_root
        WHERE created_root.replacement_event_id = NEW.replacement_event_id
          AND created_root.case_no = NEW.case_no
          AND created_root.disposition = 'created'
    ),
    NEW.case_no,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_receipts_before_update` BEFORE UPDATE ON `scheduling_service_before_replacement_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_roots_before_delete` BEFORE DELETE ON `scheduling_service_before_replacement_roots` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_before_replacement_roots records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_roots_before_update` BEFORE UPDATE ON `scheduling_service_before_replacement_roots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_roots records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_successors_before_delete` BEFORE DELETE ON `scheduling_service_before_replacement_successors` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'scheduling_service_before_replacement_successors records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_successors_before_insert` BEFORE INSERT ON `scheduling_service_before_replacement_successors` FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM matching_coordination_package_lineage AS matching_package
        INNER JOIN matching_coordination_events AS matching_event
            ON matching_event.package_lineage_id = matching_package.id
        WHERE matching_package.id = NEW.matching_package_lineage_id
          AND matching_event.id = NEW.matching_event_id
          AND matching_package.package_id = NEW.successor_package_identity
          AND matching_event.event_id = NEW.successor_matching_event_identity
          AND matching_package.case_no = NEW.case_no
          AND matching_event.case_no = NEW.case_no
    ),
    NEW.case_no,
    NULL
)$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_service_before_replacement_successors_before_update` BEFORE UPDATE ON `scheduling_service_before_replacement_successors` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_successors records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_bank_account_events_before_delete` BEFORE DELETE ON `staff_bank_account_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff bank account events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_bank_account_events_before_update` BEFORE UPDATE ON `staff_bank_account_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff bank account events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_historical_adoption_receipts_before_delete` BEFORE DELETE ON `staff_historical_adoption_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_historical_adoption_receipts_before_update` BEFORE UPDATE ON `staff_historical_adoption_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_historical_adoption_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_request_events_before_delete` BEFORE DELETE ON `scheduling_staff_leave_request_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_request_events_before_update` BEFORE UPDATE ON `scheduling_staff_leave_request_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_request_receipts_before_delete` BEFORE DELETE ON `scheduling_staff_leave_request_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_request_receipts_before_update` BEFORE UPDATE ON `scheduling_staff_leave_request_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_receipts cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_resolution_links_before_delete` BEFORE DELETE ON `scheduling_staff_leave_request_resolution_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_leave_resolution_links_before_update` BEFORE UPDATE ON `scheduling_staff_leave_request_resolution_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_staff_leave_request_resolution_links cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_obligation_events_before_delete` BEFORE DELETE ON `staff_obligation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff_obligation_events records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_obligation_events_before_update` BEFORE UPDATE ON `staff_obligation_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND NEW.`source_obligation_identity` IS NULL AND NEW.`id` <=> OLD.`id` AND NEW.`obligation_identity` <=> OLD.`obligation_identity` AND NEW.`assignment_id` <=> OLD.`assignment_id` AND NEW.`case_no` <=> OLD.`case_no` AND NEW.`staff_id` <=> OLD.`staff_id` AND NEW.`obligation_kind` <=> OLD.`obligation_kind` AND NEW.`direction` <=> OLD.`direction` AND NEW.`event_type` <=> OLD.`event_type` AND NEW.`before_amount_ntd` <=> OLD.`before_amount_ntd` AND NEW.`after_amount_ntd` <=> OLD.`after_amount_ntd` AND NEW.`due_date` <=> OLD.`due_date` AND NEW.`payroll_fingerprint` <=> OLD.`payroll_fingerprint` AND NEW.`expected_payroll_version` <=> OLD.`expected_payroll_version` AND NEW.`resulting_payroll_version` <=> OLD.`resulting_payroll_version` AND NEW.`idempotency_key` <=> OLD.`idempotency_key` AND NEW.`actor` <=> OLD.`actor` AND NEW.`reason` <=> OLD.`reason` AND NEW.`created_at` <=> OLD.`created_at`),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff_obligation_events records cannot be updated'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_overpayment_recoveries_before_delete` BEFORE DELETE ON `staff_overpayment_recoveries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recoveries root facts cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_overpayment_recovery_events_before_delete` BEFORE DELETE ON `staff_overpayment_recovery_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_overpayment_recovery_events_before_update` BEFORE UPDATE ON `staff_overpayment_recovery_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_overpayment_recovery_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payables_receipts_before_delete` BEFORE DELETE ON `staff_payables_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payables_receipts_before_update` BEFORE UPDATE ON `staff_payables_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_sources_before_delete` BEFORE DELETE ON `staff_payout_difference_sources` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_sources_before_update` BEFORE UPDATE ON `staff_payout_difference_sources` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference sources cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_source_obligations_before_delete` BEFORE DELETE ON `staff_payout_difference_source_obligations` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `staff_obligations` r360 WHERE ((r360.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r360.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_source_obligations_before_update` BEFORE UPDATE ON `staff_payout_difference_source_obligations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source obligations cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_source_rows_before_delete` BEFORE DELETE ON `staff_payout_difference_source_bank_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_difference_source_rows_before_update` BEFORE UPDATE ON `staff_payout_difference_source_bank_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff payout difference source bank rows cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_events_before_delete` BEFORE DELETE ON `staff_payout_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_events_before_update` BEFORE UPDATE ON `staff_payout_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_links_before_delete` BEFORE DELETE ON `staff_payout_obligation_links` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `staff_obligations` r360 WHERE ((r360.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))) AND OLD.`obligation_identity`=r360.`obligation_identity`)))),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be deleted'; END IF; END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_payout_links_before_update` BEFORE UPDATE ON `staff_payout_obligation_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_profile_change_events_before_delete` BEFORE DELETE ON `staff_profile_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff profile events cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_profile_change_events_before_update` BEFORE UPDATE ON `staff_profile_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'staff profile events cannot be updated'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_recovery_matchings_before_delete` BEFORE DELETE ON `staff_overpayment_recovery_matchings` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be deleted'$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_staff_recovery_matchings_before_update` BEFORE UPDATE ON `staff_overpayment_recovery_matchings` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff overpayment recovery matchings cannot be updated'$$
DELIMITER ;

CREATE OR REPLACE VIEW `case_pricing_facts` AS select `o`.`case_no` AS `case_no`,1 AS `pricing_active`,(`e`.`id` is not null) AS `pricing_override_active`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.rule')),`i`.`rule_name`) AS `pricing_rule`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.subsidy_hours')),`i`.`subsidy_hours`) AS `pricing_subsidy_hours`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.client.covered')),`i`.`client_covered`) AS `pricing_client_covered`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.client.excess')),`i`.`client_excess`) AS `pricing_client_excess`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.payroll.covered')),`i`.`payroll_covered`) AS `pricing_payroll_covered`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.payroll.excess')),`i`.`payroll_excess`) AS `pricing_payroll_excess`,coalesce(json_unquote(json_extract(`e`.`pricing_json`,'$.payroll.covered')),json_unquote(json_extract(`p`.`policy_json`,'$.twins_payroll.covered'))) AS `pricing_twins_payroll_covered` from ((((`orders` `o` join `clients` `c` on((`c`.`id` = `o`.`client_id`))) left join `accounting_pricing_policies` `p` on((`p`.`id` = `o`.`pricing_policy_id`))) left join json_table(`p`.`policy_json`, '$.identities[*]' columns (`identity_name` varchar(100) character set utf8mb4 path '$.identity_name', `rule_name` varchar(20) character set utf8mb4 path '$.rule', `subsidy_hours` varchar(100) character set utf8mb4 path '$.subsidy_hours', `client_covered` varchar(30) character set utf8mb4 path '$.client.covered', `client_excess` varchar(30) character set utf8mb4 path '$.client.excess', `payroll_covered` varchar(30) character set utf8mb4 path '$.payroll.covered', `payroll_excess` varchar(30) character set utf8mb4 path '$.payroll.excess')) `i` on(((`i`.`identity_name` collate utf8mb4_unicode_ci) = ((case `c`.`identity_status` when '一般市民' then '補助市民' when '低收入戶' then '社福' when '中低收入戶' then '社福' else `c`.`identity_status` end) collate utf8mb4_unicode_ci)))) left join `case_pricing_events` `e` on(((`e`.`id` = `o`.`pricing_override_event_id`) and (`e`.`case_no` = `o`.`case_no`)))) where ((`o`.`pricing_policy_id` is not null) or (`o`.`pricing_override_event_id` is not null));

CREATE OR REPLACE VIEW `v_order_details` AS select `o`.`case_no` AS `case_no`,`o`.`status` AS `order_status`,`o`.`lifecycle_version` AS `lifecycle_version`,`o`.`cancel_reason` AS `cancel_reason`,`o`.`line_group_id` AS `line_group_id`,`o`.`actual_start_date` AS `actual_start_date`,`o`.`actual_end_date` AS `actual_end_date`,`o`.`contract_identity` AS `contract_identity`,`c`.`id` AS `client_id`,`c`.`name` AS `client_name`,`c`.`phone` AS `client_phone`,`c`.`service_type` AS `service_mode`,`s`.`id` AS `staff_id`,`s`.`name` AS `staff_name`,`s`.`phone` AS `staff_phone`,`o`.`service_days` AS `service_days`,`o`.`service_hours_per_day` AS `service_hours_per_day`,`c`.`identity_status` AS `identity_status`,`o`.`floor_fee` AS `floor_fee`,`o`.`deposit_date` AS `deposit_date`,`o`.`start_date` AS `start_date`,`o`.`end_date` AS `end_date`,(`o`.`service_days` * `o`.`service_hours_per_day`) AS `total_hours`,(case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end) AS `subsidy_hours`,greatest(0,((`o`.`service_days` * `o`.`service_hours_per_day`) - (case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end))) AS `self_pay_hours`,(case when (`c`.`identity_status` = '非市民') then 350 else 300 end) AS `employer_unit_price`,(case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) AS `deposit_days`,(((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) AS `deposit_amount`,((((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) + coalesce(`o`.`floor_fee`,0)) AS `initial_payment_payable`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then `o`.`start_date` else NULL end) AS `first_payment_date`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end))) else NULL end) AS `remaining_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) else NULL end) AS `first_payment_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else NULL end) AS `first_payment_amount`,(case when ((`o`.`status` not in ('洽談中','訂單取消')) and (((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15) > 0)) then (`o`.`start_date` + interval 15 day) else NULL end) AS `second_payment_date`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) else NULL end) AS `second_payment_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else NULL end) AS `second_payment_amount`,((((((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) + coalesce(`o`.`floor_fee`,0)) + coalesce((case when (`o`.`status` not in ('洽談中','訂單取消')) then ((least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else 0 end),0)) + coalesce((case when (`o`.`status` not in ('洽談中','訂單取消')) then ((greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else 0 end),0)) AS `total_employer_self_pay_payable`,`payroll_rate`.`hourly_rate_ntd` AS `service_unit_price`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((`o`.`service_days` * `o`.`service_hours_per_day`) * `payroll_rate`.`hourly_rate_ntd`) else NULL end) AS `service_salary`,`o`.`staff_payment_due_date` AS `salary_payment_date_1`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end) * `payroll_rate`.`hourly_rate_ntd`) else NULL end) AS `subsidy_salary`,(select max(cast(`claim_batch`.`submitted_at` as date)) from (`subsidy_claim_batch_items` `claim_item` join `subsidy_claim_batches` `claim_batch` on((`claim_batch`.`id` = `claim_item`.`batch_id`))) where ((`claim_item`.`case_no` = `o`.`case_no`) and (`claim_batch`.`submitted_at` is not null))) AS `govt_claim_date` from (((`orders` `o` join `clients` `c` on((`o`.`client_id` = `c`.`id`))) left join `staff` `s` on((`o`.`staff_id` = `s`.`id`))) left join `case_payroll_rate_policy_snapshots` `payroll_rate` on((`payroll_rate`.`case_no` = `o`.`case_no`)));

SET FOREIGN_KEY_CHECKS=1;
