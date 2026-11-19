-- Preserve registry deletion and admit receipt-scoped expired delivery cleanup.
DELIMITER $$
DROP TRIGGER IF EXISTS `trg_line_delivery_attempt_events_before_delete`$$
CREATE TRIGGER `trg_line_delivery_attempt_events_before_delete` BEFORE DELETE ON `line_delivery_attempt_events` FOR EACH ROW BEGIN IF NOT COALESCE(((@registry_delete_key IS NOT NULL AND @registry_delete_case IS NOT NULL AND EXISTS(SELECT 1 FROM application_command_claims cmd WHERE cmd.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin) AND cmd.command_family='registry_delete/v1' AND cmd.aggregate_identity=(CONCAT('case:',CONVERT(@registry_delete_case USING utf8mb4)) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM admin_command_receipts receipt WHERE receipt.command_family='registry_delete/v1' AND receipt.idempotency_key=(CONVERT(@registry_delete_key USING utf8mb4) COLLATE utf8mb4_bin)) AND NOT EXISTS(SELECT 1 FROM contract_signing_events signed_event WHERE signed_event.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND signed_event.event_type='signed_received') AND NOT EXISTS(SELECT 1 FROM order_contract_flow_events completed WHERE completed.case_no=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND completed.event_type='contract_completed')) AND ((EXISTS(SELECT 1 FROM `line_delivery_tasks` r213 WHERE (((r213.`source_aggregate_identity`=(CONVERT(@registry_delete_case USING utf8mb4) COLLATE utf8mb4_unicode_ci) AND r213.`source_aggregate_type` IN ('orders','scheduling','contract_signing','client_finance','payroll')) OR JSON_CONTAINS(@registry_delete_tasks,CAST(r213.id AS JSON)))) AND OLD.`task_id`=r213.`id`)))) OR (@line_delivery_retention_key IS NOT NULL AND EXISTS(
 SELECT 1 FROM line_command_receipts retention_receipt
 JOIN line_delivery_tasks retention_task ON retention_task.id=OLD.task_id
 WHERE retention_receipt.idempotency_key=(CONVERT(@line_delivery_retention_key USING utf8mb4) COLLATE utf8mb4_unicode_ci)
 AND retention_receipt.result_reference=CONCAT('line-delivery-retention:',OLD.task_id)
 AND JSON_EXTRACT(retention_receipt.result_snapshot,'$.task_id')=OLD.task_id
 AND retention_task.processing_status IN ('sent','cancelled')
 AND retention_task.lease_owner IS NULL AND retention_task.lease_acquired_at_utc IS NULL AND retention_task.lease_expires_at_utc IS NULL
 AND retention_task.updated_at_utc < CAST(JSON_UNQUOTE(JSON_EXTRACT(retention_receipt.result_snapshot,'$.cutoff')) AS DATETIME(6))
 AND OLD.completed_at_utc < CAST(JSON_UNQUOTE(JSON_EXTRACT(retention_receipt.result_snapshot,'$.cutoff')) AS DATETIME(6))
 AND CAST(JSON_UNQUOTE(JSON_EXTRACT(retention_receipt.result_snapshot,'$.cutoff')) AS DATETIME(6)) <= CONVERT_TZ(DATE_SUB(CONVERT_TZ(UTC_TIMESTAMP(6),'+00:00','+08:00'), INTERVAL 6 MONTH),'+08:00','+00:00')
)),FALSE) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'line_delivery_attempt_events records cannot be deleted'; END IF; END$$
DELIMITER ;
