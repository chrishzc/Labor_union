-- Keep the registry deletion guard and admit one pending case-group purge.
DELIMITER $$
DROP TRIGGER IF EXISTS `trg_line_order_group_binding_events_before_delete`$$
CREATE TRIGGER `trg_line_order_group_binding_events_before_delete` BEFORE DELETE ON `line_order_group_binding_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))))
 OR (@line_group_history_delete_key IS NOT NULL
    AND @line_group_history_delete_case IS NOT NULL
    AND OLD.case_no=(CONVERT(@line_group_history_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)
    AND EXISTS(SELECT 1 FROM application_command_claims cmd
        WHERE cmd.idempotency_key=(CONVERT(@line_group_history_delete_key USING utf8mb4) COLLATE utf8mb4_bin)
        AND cmd.command_family='line_order_group_history_delete/v1'
        AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@line_group_history_delete_case USING utf8mb4)) COLLATE utf8mb4_bin))
    AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt
        WHERE receipt.idempotency_key=(CONVERT(@line_group_history_delete_key USING utf8mb4) COLLATE utf8mb4_bin))
    AND EXISTS(SELECT 1 FROM line_order_group_bindings binding
        WHERE binding.case_no=OLD.case_no AND binding.group_id IS NULL AND binding.binding_status='unbound')),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be deleted'; END IF; END$$
DROP TRIGGER IF EXISTS `trg_line_order_group_runtime_events_before_delete`$$
CREATE TRIGGER `trg_line_order_group_runtime_events_before_delete` BEFORE DELETE ON `line_order_group_runtime_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((OLD.`case_no`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci))))
 OR (@line_group_history_delete_key IS NOT NULL
    AND @line_group_history_delete_case IS NOT NULL
    AND OLD.case_no=(CONVERT(@line_group_history_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci)
    AND EXISTS(SELECT 1 FROM application_command_claims cmd
        WHERE cmd.idempotency_key=(CONVERT(@line_group_history_delete_key USING utf8mb4) COLLATE utf8mb4_bin)
        AND cmd.command_family='line_order_group_history_delete/v1'
        AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@line_group_history_delete_case USING utf8mb4)) COLLATE utf8mb4_bin))
    AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt
        WHERE receipt.idempotency_key=(CONVERT(@line_group_history_delete_key USING utf8mb4) COLLATE utf8mb4_bin))
    AND EXISTS(SELECT 1 FROM line_order_group_bindings binding
        WHERE binding.case_no=OLD.case_no AND binding.group_id IS NULL AND binding.binding_status='unbound')),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_order_group_runtime_events records cannot be deleted'; END IF; END$$
DELIMITER ;
