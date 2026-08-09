-- MySQL dump 10.13  Distrib 8.4.11, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: lu_test_preserve_candidate_r2_20260804
-- ------------------------------------------------------
-- Server version	8.4.11

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `lu_test_preserve_candidate_r2_20260804`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `lu_test_preserve_candidate_r2_20260804` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `lu_test_preserve_candidate_r2_20260804`;

--
-- Table structure for table `actual_hours_adjustments`
--

DROP TABLE IF EXISTS `actual_hours_adjustments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `actual_hours_adjustments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `previous_actual_hours` decimal(10,2) NOT NULL,
  `adjusted_actual_hours` decimal(10,2) NOT NULL,
  `adjustment_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjusted_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjusted_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_actual_hours_adjustment_assignment` (`assignment_id`,`adjusted_at`),
  CONSTRAINT `fk_actual_hours_adjustment_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_actual_hours_adjustment_adjusted_nonnegative` CHECK ((`adjusted_actual_hours` >= 0)),
  CONSTRAINT `chk_actual_hours_adjustment_previous_nonnegative` CHECK ((`previous_actual_hours` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `actual_hours_adjustments`
--

LOCK TABLES `actual_hours_adjustments` WRITE;
/*!40000 ALTER TABLE `actual_hours_adjustments` DISABLE KEYS */;
/*!40000 ALTER TABLE `actual_hours_adjustments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `admin_audit_logs`
--

DROP TABLE IF EXISTS `admin_audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `admin_audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_user_id` bigint DEFAULT NULL,
  `action` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `resource_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resource_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `request_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `http_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_status` int DEFAULT NULL,
  `ip_address` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details_json` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_admin_audit_actor_time` (`admin_user_id`,`created_at`),
  KEY `idx_admin_audit_resource` (`resource_type`,`resource_id`,`created_at`),
  CONSTRAINT `fk_admin_audit_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `admin_audit_logs`
--

LOCK TABLES `admin_audit_logs` WRITE;
/*!40000 ALTER TABLE `admin_audit_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `admin_audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `admin_sessions`
--

DROP TABLE IF EXISTS `admin_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `admin_sessions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `admin_user_id` bigint NOT NULL,
  `session_token_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SHA-256；原始 Session Token 只回傳一次',
  `expires_at` datetime NOT NULL,
  `last_seen_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `revoked_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_session_token_hash` (`session_token_hash`),
  KEY `idx_admin_session_active` (`admin_user_id`,`revoked_at`,`expires_at`),
  CONSTRAINT `fk_admin_session_user` FOREIGN KEY (`admin_user_id`) REFERENCES `admin_users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `admin_sessions`
--

LOCK TABLES `admin_sessions` WRITE;
/*!40000 ALTER TABLE `admin_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `admin_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `admin_users`
--

DROP TABLE IF EXISTS `admin_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `admin_users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'scrypt 雜湊；不得保存明碼密碼',
  `display_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `linked_line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '選填：對應 line_users.line_user_id',
  `role` enum('line_viewer','line_agent','line_manager','system_admin') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'line_viewer',
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `last_login_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_admin_username` (`username`),
  UNIQUE KEY `uk_admin_linked_line_user` (`linked_line_user_id`),
  CONSTRAINT `fk_admin_linked_line_user` FOREIGN KEY (`linked_line_user_id`) REFERENCES `line_users` (`line_user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `admin_users`
--

LOCK TABLES `admin_users` WRITE;
/*!40000 ALTER TABLE `admin_users` DISABLE KEYS */;
/*!40000 ALTER TABLE `admin_users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `anomaly_consumer_checkpoints`
--

DROP TABLE IF EXISTS `anomaly_consumer_checkpoints`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `anomaly_consumer_checkpoints` (
  `consumer_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `partition_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `processed_at` datetime NOT NULL,
  PRIMARY KEY (`consumer_identity`,`partition_identity`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anomaly_consumer_checkpoints`
--

LOCK TABLES `anomaly_consumer_checkpoints` WRITE;
/*!40000 ALTER TABLE `anomaly_consumer_checkpoints` DISABLE KEYS */;
/*!40000 ALTER TABLE `anomaly_consumer_checkpoints` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `anomaly_current_alerts`
--

DROP TABLE IF EXISTS `anomaly_current_alerts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `anomaly_current_alerts` (
  `fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_code` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_version` int unsigned NOT NULL,
  `source_domain` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `predicate_active` tinyint(1) NOT NULL,
  `workflow_status` enum('open','claimed','resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `workflow_version` bigint unsigned NOT NULL,
  `projection_version` bigint unsigned NOT NULL,
  `claimed_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claimed_at` datetime DEFAULT NULL,
  `resolved_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anomaly_current_alerts`
--

LOCK TABLES `anomaly_current_alerts` WRITE;
/*!40000 ALTER TABLE `anomaly_current_alerts` DISABLE KEYS */;
/*!40000 ALTER TABLE `anomaly_current_alerts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `anomaly_root_fact_projection_receipts`
--

DROP TABLE IF EXISTS `anomaly_root_fact_projection_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `anomaly_root_fact_projection_receipts` (
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_payload_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `predicate_active` tinyint(1) NOT NULL,
  `workflow_version` bigint unsigned DEFAULT NULL,
  `occurrence_recorded` tinyint(1) NOT NULL,
  `processed_at` datetime NOT NULL,
  PRIMARY KEY (`source_event_identity`),
  CONSTRAINT `chk_anomaly_root_receipt_alert_fingerprint` CHECK (regexp_like(`alert_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_anomaly_root_receipt_event_fingerprint` CHECK (regexp_like(`event_payload_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anomaly_root_fact_projection_receipts`
--

LOCK TABLES `anomaly_root_fact_projection_receipts` WRITE;
/*!40000 ALTER TABLE `anomaly_root_fact_projection_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `anomaly_root_fact_projection_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_anomaly_root_receipts_before_update` BEFORE UPDATE ON `anomaly_root_fact_projection_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_anomaly_root_receipts_before_delete` BEFORE DELETE ON `anomaly_root_fact_projection_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly root fact projection receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `anomaly_root_fact_snapshots`
--

DROP TABLE IF EXISTS `anomaly_root_fact_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `anomaly_root_fact_snapshots` (
  `alert_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_version` bigint unsigned NOT NULL,
  `source_occurred_at` datetime NOT NULL,
  `root_condition_active` tinyint(1) NOT NULL,
  `integrity_blocker_active` tinyint(1) NOT NULL,
  `amount_delta_ntd` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `finance_import_batch_id` bigint NOT NULL,
  `affected_order_identities` json NOT NULL,
  `affected_obligation_identities` json NOT NULL,
  `domain_blockers` json NOT NULL,
  `reason_codes` json NOT NULL,
  `projection_freshness` enum('current','stale') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'current',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`alert_fingerprint`),
  KEY `fk_anomaly_root_snapshot_row` (`finance_import_row_id`),
  KEY `fk_anomaly_root_snapshot_batch` (`finance_import_batch_id`),
  CONSTRAINT `fk_anomaly_root_snapshot_alert` FOREIGN KEY (`alert_fingerprint`) REFERENCES `anomaly_current_alerts` (`fingerprint`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_anomaly_root_snapshot_batch` FOREIGN KEY (`finance_import_batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_anomaly_root_snapshot_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_anomaly_root_snapshot_blockers` CHECK ((json_type(`domain_blockers`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_anomaly_root_snapshot_obligations` CHECK ((json_type(`affected_obligation_identities`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_anomaly_root_snapshot_orders` CHECK ((json_type(`affected_order_identities`) = _utf8mb4'ARRAY')),
  CONSTRAINT `chk_anomaly_root_snapshot_reasons` CHECK ((json_type(`reason_codes`) = _utf8mb4'ARRAY'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anomaly_root_fact_snapshots`
--

LOCK TABLES `anomaly_root_fact_snapshots` WRITE;
/*!40000 ALTER TABLE `anomaly_root_fact_snapshots` DISABLE KEYS */;
/*!40000 ALTER TABLE `anomaly_root_fact_snapshots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `anomaly_workflow_events`
--

DROP TABLE IF EXISTS `anomaly_workflow_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `anomaly_workflow_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('claim','resolve','reopen','auto_resolve') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_workflow_version` bigint unsigned NOT NULL,
  `resulting_workflow_version` bigint unsigned NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_anomaly_workflow_event_idempotency` (`idempotency_key`),
  KEY `idx_anomaly_workflow_event_alert` (`alert_fingerprint`,`resulting_workflow_version`),
  CONSTRAINT `fk_anomaly_workflow_event_alert` FOREIGN KEY (`alert_fingerprint`) REFERENCES `anomaly_current_alerts` (`fingerprint`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_anomaly_workflow_event_version` CHECK ((`resulting_workflow_version` = (`expected_workflow_version` + 1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anomaly_workflow_events`
--

LOCK TABLES `anomaly_workflow_events` WRITE;
/*!40000 ALTER TABLE `anomaly_workflow_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `anomaly_workflow_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_anomaly_workflow_events_before_update` BEFORE UPDATE ON `anomaly_workflow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_anomaly_workflow_events_before_delete` BEFORE DELETE ON `anomaly_workflow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'anomaly_workflow_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `application_command_claims`
--

DROP TABLE IF EXISTS `application_command_claims`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `application_command_claims` (
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idempotency_key`),
  CONSTRAINT `chk_application_command_claim_fingerprint` CHECK (regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_application_command_claim_text` CHECK (((char_length(trim(`command_family`)) > 0) and (char_length(trim(`aggregate_identity`)) > 0) and (char_length(trim(`correlation_id`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `application_command_claims`
--

LOCK TABLES `application_command_claims` WRITE;
/*!40000 ALTER TABLE `application_command_claims` DISABLE KEYS */;
/*!40000 ALTER TABLE `application_command_claims` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_application_command_claims_before_update` BEFORE UPDATE ON `application_command_claims` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_application_command_claims_before_delete` BEFORE DELETE ON `application_command_claims` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'application_command_claims records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `assignment_payroll_rate_snapshots`
--

DROP TABLE IF EXISTS `assignment_payroll_rate_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `assignment_payroll_rate_snapshots` (
  `assignment_id` bigint NOT NULL,
  `policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`assignment_id`),
  KEY `fk_assignment_payroll_rate_policy` (`policy_version`,`policy_kind`),
  CONSTRAINT `fk_assignment_payroll_rate_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_assignment_payroll_rate_policy` FOREIGN KEY (`policy_version`, `policy_kind`) REFERENCES `payroll_rate_policies` (`policy_version`, `policy_kind`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_assignment_payroll_rate_amount` CHECK ((`hourly_rate_ntd` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `assignment_payroll_rate_snapshots`
--

LOCK TABLES `assignment_payroll_rate_snapshots` WRITE;
/*!40000 ALTER TABLE `assignment_payroll_rate_snapshots` DISABLE KEYS */;
/*!40000 ALTER TABLE `assignment_payroll_rate_snapshots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `assignment_plan_apply_receipts`
--

DROP TABLE IF EXISTS `assignment_plan_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `assignment_plan_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `assignment_plan_apply_receipts`
--

LOCK TABLES `assignment_plan_apply_receipts` WRITE;
/*!40000 ALTER TABLE `assignment_plan_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `assignment_plan_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_plan_receipts_before_update` BEFORE UPDATE ON `assignment_plan_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_plan_receipts_before_delete` BEFORE DELETE ON `assignment_plan_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'assignment_plan_apply_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `assignment_schedule_leave_substitution_batches`
--

DROP TABLE IF EXISTS `assignment_schedule_leave_substitution_batches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `assignment_schedule_leave_substitution_batches` (
  `batch_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '整批冪等鍵',
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'canonical preview sha256 lowercase hex',
  `item_count` int unsigned NOT NULL COMMENT 'canonical items 數量',
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '執行者管理員識別',
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '統一 non-empty 原因',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `assignment_schedule_leave_substitution_batches`
--

LOCK TABLES `assignment_schedule_leave_substitution_batches` WRITE;
/*!40000 ALTER TABLE `assignment_schedule_leave_substitution_batches` DISABLE KEYS */;
/*!40000 ALTER TABLE `assignment_schedule_leave_substitution_batches` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_schedule_leave_substitution_batches_before_update` BEFORE UPDATE ON `assignment_schedule_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_schedule_leave_substitution_batches_before_delete` BEFORE DELETE ON `assignment_schedule_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `assignment_schedule_leave_substitution_events`
--

DROP TABLE IF EXISTS `assignment_schedule_leave_substitution_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `assignment_schedule_leave_substitution_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
  `original_assignment_id` bigint NOT NULL COMMENT '請假日原始正式服務指派 id',
  `original_schedule_id` int NOT NULL COMMENT '被處置之日排班 id',
  `work_date` date NOT NULL COMMENT '被處置之休假日期',
  `resolution_type` enum('leave_only','defer_following_assignments','substitute') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '處置類型',
  `substitute_assignment_id` bigint DEFAULT NULL COMMENT '只在 substitute 時為非空',
  `event_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全域唯一冪等鍵',
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '執行者管理員識別',
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '非空原因',
  `schedule_snapshot` json NOT NULL COMMENT '原排班/順延/代班日套用前後快照',
  `payroll_snapshot` json NOT NULL COMMENT '原 assignment 與代班 assignment 的核對快照',
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
  `batch_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `assignment_schedule_leave_substitution_events`
--

LOCK TABLES `assignment_schedule_leave_substitution_events` WRITE;
/*!40000 ALTER TABLE `assignment_schedule_leave_substitution_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `assignment_schedule_leave_substitution_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_schedule_leave_substitution_events_before_update` BEFORE UPDATE ON `assignment_schedule_leave_substitution_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_assignment_schedule_leave_substitution_events_before_delete` BEFORE DELETE ON `assignment_schedule_leave_substitution_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `audit_logs`
--

DROP TABLE IF EXISTS `audit_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `action` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `table_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `pk_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_fields` json NOT NULL,
  `actor` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_fields_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `occurred_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_logs_table_pk_time` (`table_name`,`pk_value`,`occurred_at`),
  KEY `idx_audit_logs_request` (`request_id`),
  KEY `idx_audit_logs_actor` (`actor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `background_jobs`
--

DROP TABLE IF EXISTS `background_jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `background_jobs` (
  `job_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_type` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `command_version` smallint unsigned DEFAULT NULL,
  `command_payload` json DEFAULT NULL,
  `submitted_by` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('queued','running','succeeded','failed','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'queued',
  `receipt_payload` json DEFAULT NULL,
  `error_payload` json DEFAULT NULL,
  `available_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `attempt_count` smallint unsigned NOT NULL DEFAULT '0',
  `max_attempts` smallint unsigned NOT NULL DEFAULT '3',
  `lease_token` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_owner` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lease_expires_at` datetime(6) DEFAULT NULL,
  `result_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`job_id`),
  UNIQUE KEY `uk_command_identity` (`command_identity`),
  KEY `idx_status` (`status`),
  KEY `idx_background_jobs_queue` (`status`,`available_at`,`created_at`),
  KEY `idx_background_jobs_lease` (`status`,`lease_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `background_jobs`
--

LOCK TABLES `background_jobs` WRITE;
/*!40000 ALTER TABLE `background_jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `background_jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `beclass_import_review_events`
--

DROP TABLE IF EXISTS `beclass_import_review_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `beclass_import_review_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_row_id` bigint NOT NULL,
  `event_type` enum('resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `resulting_version` bigint unsigned NOT NULL,
  `candidate_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `owning_record_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `corrected_payload` json NOT NULL,
  `resolved_issue_codes` json NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_import_review_events`
--

LOCK TABLES `beclass_import_review_events` WRITE;
/*!40000 ALTER TABLE `beclass_import_review_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `beclass_import_review_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_events_before_update` BEFORE UPDATE ON `beclass_import_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_events_before_delete` BEFORE DELETE ON `beclass_import_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `beclass_import_review_outbox`
--

DROP TABLE IF EXISTS `beclass_import_review_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `beclass_import_review_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_row_id` bigint NOT NULL,
  `review_event_id` bigint DEFAULT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('review_opened','review_resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `bounded_snapshot` json NOT NULL,
  `published_at` datetime DEFAULT NULL,
  `attempts` int unsigned NOT NULL DEFAULT '0',
  `last_error` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_import_review_outbox`
--

LOCK TABLES `beclass_import_review_outbox` WRITE;
/*!40000 ALTER TABLE `beclass_import_review_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `beclass_import_review_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `beclass_import_review_receipts`
--

DROP TABLE IF EXISTS `beclass_import_review_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `beclass_import_review_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_row_id` bigint NOT NULL,
  `owning_record_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_import_review_receipts`
--

LOCK TABLES `beclass_import_review_receipts` WRITE;
/*!40000 ALTER TABLE `beclass_import_review_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `beclass_import_review_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_receipts_before_update` BEFORE UPDATE ON `beclass_import_review_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_receipts_before_delete` BEFORE DELETE ON `beclass_import_review_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `beclass_import_review_rows`
--

DROP TABLE IF EXISTS `beclass_import_review_rows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `beclass_import_review_rows` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `review_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_kind` enum('client','staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_sheet` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_row` int unsigned NOT NULL,
  `masked_identifier` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_payload` json NOT NULL,
  `issue_codes` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_beclass_review_identity` (`review_identity`),
  UNIQUE KEY `uq_beclass_review_source_event` (`source_kind`,`source_event_identity`),
  CONSTRAINT `chk_beclass_review_fingerprint` CHECK (regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_beclass_review_issues` CHECK (((json_type(`issue_codes`) = _utf8mb4'ARRAY') and (json_length(`issue_codes`) > 0))),
  CONSTRAINT `chk_beclass_review_payload` CHECK ((json_type(`source_payload`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_beclass_review_source_location` CHECK (((char_length(trim(`source_sheet`)) > 0) and (`source_row` > 0) and (char_length(trim(`masked_identifier`)) > 0) and (locate(_utf8mb4'*',`masked_identifier`) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_import_review_rows`
--

LOCK TABLES `beclass_import_review_rows` WRITE;
/*!40000 ALTER TABLE `beclass_import_review_rows` DISABLE KEYS */;
/*!40000 ALTER TABLE `beclass_import_review_rows` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_rows_before_update` BEFORE UPDATE ON `beclass_import_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_beclass_review_rows_before_delete` BEFORE DELETE ON `beclass_import_review_rows` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'beclass_import_review_rows records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `beclass_records`
--

DROP TABLE IF EXISTS `beclass_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `beclass_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `seq_num` int DEFAULT NULL COMMENT '項次',
  `query_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '查詢序號 - 與 clients.case_no 進行主關聯',
  `created_at` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '報名時間',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '姓名',
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Email',
  `birth_date` date DEFAULT NULL COMMENT '生日',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `tel` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '市話',
  `ext` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分機',
  `city` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '縣市',
  `zip_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '郵遞區號',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '地址',
  `refund_bank_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助款退款:銀行代號+分行代號',
  `refund_account_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助款退款:銀行帳號',
  `survey_details` json DEFAULT NULL COMMENT 'BeClass 問卷詳細內容 (包含餐點、用油、烹煮工具、特殊計費等 JSON)',
  `admin_notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '管理者註記事項',
  `db_created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `db_updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `query_no` (`query_no`),
  KEY `idx_query_no` (`query_no`),
  KEY `idx_phone` (`phone`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_records`
--

LOCK TABLES `beclass_records` WRITE;
/*!40000 ALTER TABLE `beclass_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `beclass_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `caregiver_availability_lock_days`
--

DROP TABLE IF EXISTS `caregiver_availability_lock_days`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caregiver_availability_lock_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `lock_id` bigint NOT NULL COMMENT '對應 caregiver_availability_locks.id',
  `segment_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plan_segments.id',
  `staff_id` int NOT NULL COMMENT '月嫂識別；對應 staff.id',
  `lock_date` date NOT NULL COMMENT '等待訂金占用日期',
  `active_marker` tinyint(1) DEFAULT NULL COMMENT '1表示該月嫂該日有效等待訂金鎖；已解除為 NULL 以支援 UNIQUE(staff_id, lock_date, active_marker)',
  `released_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '解除鎖定的管理員識別',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_availability_lock_days`
--

LOCK TABLES `caregiver_availability_lock_days` WRITE;
/*!40000 ALTER TABLE `caregiver_availability_lock_days` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_availability_lock_days` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_lock_days_before_update` BEFORE UPDATE ON `caregiver_availability_lock_days` FOR EACH ROW SET NEW.lock_id = IF(OLD.id <=> NEW.id AND OLD.lock_id <=> NEW.lock_id AND OLD.segment_id <=> NEW.segment_id AND OLD.staff_id <=> NEW.staff_id AND OLD.lock_date <=> NEW.lock_date AND OLD.created_at <=> NEW.created_at, NEW.lock_id, NULL) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_lock_days_before_delete` BEFORE DELETE ON `caregiver_availability_lock_days` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_days records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `caregiver_availability_lock_events`
--

DROP TABLE IF EXISTS `caregiver_availability_lock_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caregiver_availability_lock_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `lock_id` bigint NOT NULL COMMENT '對應 caregiver_availability_locks.id',
  `event_type` enum('lock_acquired','lock_released','lock_converted','lock_cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件類型',
  `event_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全域唯一非空冪等鍵',
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '記錄事件的非空管理員識別',
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'release/convert/cancel 的非空原因；acquired 為 NULL',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_availability_lock_events`
--

LOCK TABLES `caregiver_availability_lock_events` WRITE;
/*!40000 ALTER TABLE `caregiver_availability_lock_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_availability_lock_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_lock_events_before_update` BEFORE UPDATE ON `caregiver_availability_lock_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_lock_events_before_delete` BEFORE DELETE ON `caregiver_availability_lock_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_lock_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `caregiver_availability_locks`
--

DROP TABLE IF EXISTS `caregiver_availability_locks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caregiver_availability_locks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plans.id',
  `status` enum('active','released','converted','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '鎖定批次狀態',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '1表示該方案目前有效鎖定批次；歷史/無效為 NULL 以支援 UNIQUE(plan_id, is_active)',
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '建立鎖定批次的非空管理員識別',
  `released_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '解除/轉換/取消鎖定批次的管理員識別',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_availability_locks`
--

LOCK TABLES `caregiver_availability_locks` WRITE;
/*!40000 ALTER TABLE `caregiver_availability_locks` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_availability_locks` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_locks_before_update` BEFORE UPDATE ON `caregiver_availability_locks` FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.plan_id <=> NEW.plan_id AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_availability_locks_before_delete` BEFORE DELETE ON `caregiver_availability_locks` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_availability_locks records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `caregiver_matching_plan_events`
--

DROP TABLE IF EXISTS `caregiver_matching_plan_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caregiver_matching_plan_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_id` bigint NOT NULL COMMENT '對應 caregiver_matching_plans.id',
  `segment_id` bigint DEFAULT NULL COMMENT '對應 caregiver_matching_plan_segments.id；方案層級事件為 NULL',
  `event_type` enum('info_1_sent','info_2_sent','willingness_changed','resume_sent','plan_cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件類型',
  `event_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '呼叫端提供的全表唯一非空冪等鍵',
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '記錄事件的非空管理員識別',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_matching_plan_events`
--

LOCK TABLES `caregiver_matching_plan_events` WRITE;
/*!40000 ALTER TABLE `caregiver_matching_plan_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_matching_plan_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plan_events_before_update` BEFORE UPDATE ON `caregiver_matching_plan_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plan_events_before_delete` BEFORE DELETE ON `caregiver_matching_plan_events` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `caregiver_matching_plan_segments`
--

DROP TABLE IF EXISTS `caregiver_matching_plan_segments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_matching_plan_segments`
--

LOCK TABLES `caregiver_matching_plan_segments` WRITE;
/*!40000 ALTER TABLE `caregiver_matching_plan_segments` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_matching_plan_segments` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plan_segments_before_update` BEFORE UPDATE ON `caregiver_matching_plan_segments` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plan_segments_before_delete` BEFORE DELETE ON `caregiver_matching_plan_segments` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plan_segments records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `caregiver_matching_plans`
--

DROP TABLE IF EXISTS `caregiver_matching_plans`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `caregiver_matching_plans` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '洽談中訂單案件編號；對應 orders.case_no',
  `version` int NOT NULL DEFAULT '1' COMMENT '配對方案版本號 (1, 2, ...)',
  `status` enum('draft','proposed','accepted','rejected','superseded','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft' COMMENT '配對方案狀態',
  `is_active` tinyint(1) DEFAULT NULL COMMENT '1表示該案件目前有效版本；歷史版本或無效版本為 NULL 以支援 UNIQUE(case_no, is_active)',
  `start_date` date NOT NULL COMMENT '本方案完整服務開始日',
  `end_date` date NOT NULL COMMENT '本方案完整服務結束日',
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '建立方案版本的非空管理員識別',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `caregiver_matching_plans`
--

LOCK TABLES `caregiver_matching_plans` WRITE;
/*!40000 ALTER TABLE `caregiver_matching_plans` DISABLE KEYS */;
/*!40000 ALTER TABLE `caregiver_matching_plans` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plans_before_update` BEFORE UPDATE ON `caregiver_matching_plans` FOR EACH ROW SET NEW.created_by = IF(OLD.id <=> NEW.id AND OLD.case_no <=> NEW.case_no AND OLD.version <=> NEW.version AND OLD.start_date <=> NEW.start_date AND OLD.end_date <=> NEW.end_date AND OLD.created_by <=> NEW.created_by AND OLD.created_at <=> NEW.created_at, NEW.created_by, NULL) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_caregiver_matching_plans_before_delete` BEFORE DELETE ON `caregiver_matching_plans` FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'caregiver_matching_plans records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_architecture_bootstrap_events`
--

DROP TABLE IF EXISTS `case_architecture_bootstrap_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_architecture_bootstrap_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `client_payment_terms_event_id` bigint NOT NULL,
  `client_policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_hourly_rate_ntd` bigint NOT NULL,
  `payroll_policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payroll_policy_kind` enum('citizen','subsidized_citizen','non_citizen') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payroll_hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_architecture_bootstrap_events`
--

LOCK TABLES `case_architecture_bootstrap_events` WRITE;
/*!40000 ALTER TABLE `case_architecture_bootstrap_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_architecture_bootstrap_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_architecture_bootstrap_events_before_update` BEFORE UPDATE ON `case_architecture_bootstrap_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_architecture_bootstrap_events_before_delete` BEFORE DELETE ON `case_architecture_bootstrap_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_architecture_bootstrap_receipts`
--

DROP TABLE IF EXISTS `case_architecture_bootstrap_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_architecture_bootstrap_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  CONSTRAINT `chk_case_architecture_receipt_created` CHECK ((`bootstrap_created` in (0,1))),
  CONSTRAINT `chk_case_architecture_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_architecture_receipt_initial_versions` CHECK (((`client_finance_version` = 0) and (`payroll_version` = 0) and (`scheduling_version` = 0) and (`scheduling_generation` = 0))),
  CONSTRAINT `chk_case_architecture_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_architecture_bootstrap_receipts`
--

LOCK TABLES `case_architecture_bootstrap_receipts` WRITE;
/*!40000 ALTER TABLE `case_architecture_bootstrap_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_architecture_bootstrap_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_architecture_bootstrap_receipts_before_update` BEFORE UPDATE ON `case_architecture_bootstrap_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_architecture_bootstrap_receipts_before_delete` BEFORE DELETE ON `case_architecture_bootstrap_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_architecture_bootstrap_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_import_events`
--

DROP TABLE IF EXISTS `case_import_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_import_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `bootstrap_event_id` bigint NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `candidate_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_snapshot` json NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_import_events`
--

LOCK TABLES `case_import_events` WRITE;
/*!40000 ALTER TABLE `case_import_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_import_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_import_events_before_update` BEFORE UPDATE ON `case_import_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_import_events_before_delete` BEFORE DELETE ON `case_import_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_import_receipts`
--

DROP TABLE IF EXISTS `case_import_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_import_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int NOT NULL,
  `import_event_id` bigint NOT NULL,
  `bootstrap_event_id` bigint NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `result_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_case_import_receipt_key` (`idempotency_key`),
  UNIQUE KEY `uq_case_import_receipt_event` (`import_event_id`),
  KEY `fk_case_import_receipt_order` (`case_no`),
  KEY `fk_case_import_receipt_client` (`client_id`),
  KEY `fk_case_import_receipt_bootstrap_event` (`bootstrap_event_id`),
  CONSTRAINT `fk_case_import_receipt_bootstrap_event` FOREIGN KEY (`bootstrap_event_id`) REFERENCES `case_architecture_bootstrap_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_client` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_import_event` FOREIGN KEY (`import_event_id`) REFERENCES `case_import_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_case_import_receipt_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_case_import_receipt_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`source_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_case_import_receipt_snapshot` CHECK ((json_type(`result_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_case_import_receipt_versions` CHECK (((`order_version` = 0) and (`client_finance_version` = 0) and (`payroll_version` = 0) and (`scheduling_version` = 0) and (`scheduling_generation` = 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_import_receipts`
--

LOCK TABLES `case_import_receipts` WRITE;
/*!40000 ALTER TABLE `case_import_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_import_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_import_receipts_before_update` BEFORE UPDATE ON `case_import_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_import_receipts_before_delete` BEFORE DELETE ON `case_import_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_import_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_payroll_rate_policy_snapshots`
--

DROP TABLE IF EXISTS `case_payroll_rate_policy_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_payroll_rate_policy_snapshots` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `source_identity_status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_payroll_rate_policy_snapshots`
--

LOCK TABLES `case_payroll_rate_policy_snapshots` WRITE;
/*!40000 ALTER TABLE `case_payroll_rate_policy_snapshots` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_payroll_rate_policy_snapshots` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_payroll_policy_snapshots_before_update` BEFORE UPDATE ON `case_payroll_rate_policy_snapshots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_payroll_policy_snapshots_before_delete` BEFORE DELETE ON `case_payroll_rate_policy_snapshots` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'case_payroll_rate_policy_snapshots records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `case_staff_assignments`
--

DROP TABLE IF EXISTS `case_staff_assignments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `case_staff_assignments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `generation_id` bigint DEFAULT NULL,
  `candidate_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
  `status` enum('planned','active','completed','replaced','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'planned',
  `replacement_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_staff_assignments`
--

LOCK TABLES `case_staff_assignments` WRITE;
/*!40000 ALTER TABLE `case_staff_assignments` DISABLE KEYS */;
/*!40000 ALTER TABLE `case_staff_assignments` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_staff_assignments_original_period_insert` BEFORE INSERT ON `case_staff_assignments` FOR EACH ROW SET NEW.original_assigned_start_date = COALESCE(NEW.original_assigned_start_date, NEW.assigned_start_date),
    NEW.original_assigned_end_date = COALESCE(NEW.original_assigned_end_date, NEW.assigned_end_date) */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_case_staff_assignments_original_period_update` BEFORE UPDATE ON `case_staff_assignments` FOR EACH ROW SET NEW.original_assigned_start_date = OLD.original_assigned_start_date,
    NEW.original_assigned_end_date = OLD.original_assigned_end_date */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_deposit_settlement_projection`
--

DROP TABLE IF EXISTS `client_deposit_settlement_projection`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_deposit_settlement_projection` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `deposit_obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `settlement_state` enum('unsettled','settled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `contracted_amount_ntd` bigint unsigned NOT NULL,
  `allocated_net_amount_ntd` bigint NOT NULL,
  `settlement_identity` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_deposit_settlement_projection`
--

LOCK TABLES `client_deposit_settlement_projection` WRITE;
/*!40000 ALTER TABLE `client_deposit_settlement_projection` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_deposit_settlement_projection` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_finance_accounts`
--

DROP TABLE IF EXISTS `client_finance_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_finance_accounts` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  CONSTRAINT `fk_client_finance_account_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_finance_accounts`
--

LOCK TABLES `client_finance_accounts` WRITE;
/*!40000 ALTER TABLE `client_finance_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_finance_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_finance_apply_receipts`
--

DROP TABLE IF EXISTS `client_finance_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_finance_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_finance_apply_receipts`
--

LOCK TABLES `client_finance_apply_receipts` WRITE;
/*!40000 ALTER TABLE `client_finance_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_finance_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_finance_receipts_before_update` BEFORE UPDATE ON `client_finance_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_finance_receipts_before_delete` BEFORE DELETE ON `client_finance_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_finance_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_finance_outbox`
--

DROP TABLE IF EXISTS `client_finance_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_finance_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('orders_deposit_reconciled','orders_deposit_reversed','anomaly_review_required','projection_refresh') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_finance_outbox_intent` (`intent_key`),
  KEY `idx_client_finance_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_client_finance_outbox_order` (`case_no`),
  CONSTRAINT `fk_client_finance_outbox_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_finance_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_finance_outbox`
--

LOCK TABLES `client_finance_outbox` WRITE;
/*!40000 ALTER TABLE `client_finance_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_finance_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_ledger_entries`
--

DROP TABLE IF EXISTS `client_ledger_entries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_ledger_entries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `entry_type` enum('receipt','refund','subsidy_return','subsidy_advance','adjustment','reversal','refund_reversal','subsidy_return_reversal','subsidy_advance_reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `occurred_on` date NOT NULL,
  `reconciliation_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_entry_id` bigint DEFAULT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_ledger_entries`
--

LOCK TABLES `client_ledger_entries` WRITE;
/*!40000 ALTER TABLE `client_ledger_entries` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_ledger_entries` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_ledger_entries_before_update` BEFORE UPDATE ON `client_ledger_entries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_ledger_entries_before_delete` BEFORE DELETE ON `client_ledger_entries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_ledger_entries records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_ledger_obligation_allocations`
--

DROP TABLE IF EXISTS `client_ledger_obligation_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_ledger_obligation_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `ledger_entry_id` bigint NOT NULL,
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_ledger_obligation_allocations`
--

LOCK TABLES `client_ledger_obligation_allocations` WRITE;
/*!40000 ALTER TABLE `client_ledger_obligation_allocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_ledger_obligation_allocations` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_ledger_allocations_before_update` BEFORE UPDATE ON `client_ledger_obligation_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_ledger_allocations_before_delete` BEFORE DELETE ON `client_ledger_obligation_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client ledger allocations cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_obligation_events`
--

DROP TABLE IF EXISTS `client_obligation_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_obligation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_type` enum('deposit','first','second','refund','subsidy_return','adjustment') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('receivable_from_client','payable_to_client') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('established','recalculated','adjusted','reversed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_amount_ntd` bigint NOT NULL,
  `after_amount_ntd` bigint NOT NULL,
  `before_due_date` date DEFAULT NULL,
  `after_due_date` date DEFAULT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_account_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_obligation_event_idempotency` (`idempotency_key`),
  UNIQUE KEY `uq_client_obligation_source_event` (`obligation_identity`,`source_event_identity`),
  KEY `idx_client_obligation_event_case_type` (`case_no`,`obligation_type`,`created_at`),
  KEY `fk_client_obligation_event_source` (`source_obligation_identity`,`case_no`),
  CONSTRAINT `fk_client_obligation_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_client_obligation_event_source` FOREIGN KEY (`source_obligation_identity`, `case_no`) REFERENCES `client_obligations` (`obligation_identity`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_obligation_event_amount` CHECK (((`before_amount_ntd` >= 0) and (`after_amount_ntd` >= 0) and ((`before_amount_ntd` <> `after_amount_ntd`) or (not((`before_due_date` <=> `after_due_date`))))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_obligation_events`
--

LOCK TABLES `client_obligation_events` WRITE;
/*!40000 ALTER TABLE `client_obligation_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_obligation_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_obligation_events_before_update` BEFORE UPDATE ON `client_obligation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_obligation_events_before_delete` BEFORE DELETE ON `client_obligation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_obligation_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_obligations`
--

DROP TABLE IF EXISTS `client_obligations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_obligations` (
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `obligation_type` enum('deposit','first','second','refund','subsidy_return','adjustment') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('receivable_from_client','payable_to_client') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount_due_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `status` enum('open','settled','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_obligations`
--

LOCK TABLES `client_obligations` WRITE;
/*!40000 ALTER TABLE `client_obligations` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_obligations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_payment_terms`
--

DROP TABLE IF EXISTS `client_payment_terms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_payment_terms` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payment_terms`
--

LOCK TABLES `client_payment_terms` WRITE;
/*!40000 ALTER TABLE `client_payment_terms` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_payment_terms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_payment_terms_events`
--

DROP TABLE IF EXISTS `client_payment_terms_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_payment_terms_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_hourly_rate_ntd` bigint NOT NULL,
  `deposit_service_days` int unsigned NOT NULL,
  `deposit_due_date` date NOT NULL,
  `first_payment_due_date` date NOT NULL,
  `second_payment_due_date` date DEFAULT NULL,
  `expected_account_version` bigint unsigned NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payment_terms_source` (`case_no`,`source_event_identity`),
  UNIQUE KEY `uq_client_payment_terms_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_client_payment_terms_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_client_payment_terms_event_values` CHECK (((`client_hourly_rate_ntd` > 0) and (char_length(trim(`policy_version`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payment_terms_events`
--

LOCK TABLES `client_payment_terms_events` WRITE;
/*!40000 ALTER TABLE `client_payment_terms_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_payment_terms_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_payment_terms_events_before_update` BEFORE UPDATE ON `client_payment_terms_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_payment_terms_events_before_delete` BEFORE DELETE ON `client_payment_terms_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_payment_terms_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_payment_transactions`
--

DROP TABLE IF EXISTS `client_payment_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_payment_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `client_payment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `stage` enum('deposit','first_payment','second_payment','subsidy_refund','subsidy_return','adjustment') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_type` enum('receipt','refund','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行流水或金流平台唯一識別',
  `finance_import_row_id` bigint DEFAULT NULL COMMENT 'canonical 銀行流水；人工補登允許 NULL',
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payment_transactions`
--

LOCK TABLES `client_payment_transactions` WRITE;
/*!40000 ALTER TABLE `client_payment_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_payment_transactions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_payments`
--

DROP TABLE IF EXISTS `client_payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_payments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '唯一案件鍵，對應 orders.case_no',
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
  `subsidy_return_review_status` enum('review_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '補助退還人工覆核狀態；NULL 表示未暫停自動核銷',
  `subsidy_return_review_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '補助退還需人工覆核的原因',
  `payment_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '待收訂金',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_client_payments_case_no` (`case_no`),
  CONSTRAINT `fk_client_payments_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payments`
--

LOCK TABLES `client_payments` WRITE;
/*!40000 ALTER TABLE `client_payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `client_refund_reversal_apply_receipts`
--

DROP TABLE IF EXISTS `client_refund_reversal_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_refund_reversal_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correction_type` enum('refund','refund_return','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_refund_reversal_apply_receipts`
--

LOCK TABLES `client_refund_reversal_apply_receipts` WRITE;
/*!40000 ALTER TABLE `client_refund_reversal_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_refund_reversal_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_refund_reversal_receipt_before_update` BEFORE UPDATE ON `client_refund_reversal_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_refund_reversal_receipt_before_delete` BEFORE DELETE ON `client_refund_reversal_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client refund reversal receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_subsidy_advance_recoveries`
--

DROP TABLE IF EXISTS `client_subsidy_advance_recoveries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_subsidy_advance_recoveries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_subsidy_advance_recoveries`
--

LOCK TABLES `client_subsidy_advance_recoveries` WRITE;
/*!40000 ALTER TABLE `client_subsidy_advance_recoveries` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_subsidy_advance_recoveries` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_subsidy_advance_recovery_before_update` BEFORE UPDATE ON `client_subsidy_advance_recoveries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_subsidy_advance_recovery_before_delete` BEFORE DELETE ON `client_subsidy_advance_recoveries` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_advance_recoveries cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `client_subsidy_return_claim_item_links`
--

DROP TABLE IF EXISTS `client_subsidy_return_claim_item_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `client_subsidy_return_claim_item_links` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_subsidy_return_claim_item_links`
--

LOCK TABLES `client_subsidy_return_claim_item_links` WRITE;
/*!40000 ALTER TABLE `client_subsidy_return_claim_item_links` DISABLE KEYS */;
/*!40000 ALTER TABLE `client_subsidy_return_claim_item_links` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_subsidy_return_claim_item_link_before_update` BEFORE UPDATE ON `client_subsidy_return_claim_item_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_client_subsidy_return_claim_item_link_before_delete` BEFORE DELETE ON `client_subsidy_return_claim_item_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'client_subsidy_return_claim_item_links cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `clients`
--

DROP TABLE IF EXISTS `clients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `clients` (
  `id` int NOT NULL AUTO_INCREMENT,
  `seq_num` int DEFAULT NULL COMMENT '項次',
  `reject_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '不符合原因',
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '查詢序號(案件編號) - 去重唯一識別碼',
  `created_at` datetime DEFAULT NULL COMMENT '報名時間(建檔)',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'IP位址',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '姓名',
  `gender` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '性別',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `city` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '縣市',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '地址',
  `identity_status` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '身分資格',
  `service_time` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '服務時間',
  `due_month` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '預產期/預計服務開始月份',
  `service_start_date` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '預計服務日期',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '其他事項',
  `service_days` int DEFAULT NULL COMMENT '希望服務天數',
  `residence_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '居住型態',
  `delivery_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '生產方式',
  `service_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '服務方式',
  `baby_info` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '寶寶資訊',
  `line_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE ID',
  `line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
  `admin_notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '管理者註記事項',
  `db_created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '資料庫匯入時間',
  `db_updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '資料庫更新時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `case_no` (`case_no`),
  KEY `idx_case_no` (`case_no`),
  KEY `idx_phone` (`phone`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `clients`
--

LOCK TABLES `clients` WRITE;
/*!40000 ALTER TABLE `clients` DISABLE KEYS */;
/*!40000 ALTER TABLE `clients` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crawler_logs`
--

DROP TABLE IF EXISTS `crawler_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crawler_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `crawled_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '執行狀態 (SUCCESS/FAILED)',
  `records_inserted` int DEFAULT '0' COMMENT '新增筆數',
  `records_updated` int DEFAULT '0' COMMENT '更新筆數',
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '日誌詳細說明或錯誤原因',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crawler_logs`
--

LOCK TABLES `crawler_logs` WRITE;
/*!40000 ALTER TABLE `crawler_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `crawler_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `faq`
--

DROP TABLE IF EXISTS `faq`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `faq` (
  `id` int NOT NULL AUTO_INCREMENT,
  `question` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '標準問題',
  `answer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '預設答案',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `faq`
--

LOCK TABLES `faq` WRITE;
/*!40000 ALTER TABLE `faq` DISABLE KEYS */;
/*!40000 ALTER TABLE `faq` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_alert_events`
--

DROP TABLE IF EXISTS `finance_alert_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_alert_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_id` bigint NOT NULL,
  `event_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_domain` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `event_snapshot` json NOT NULL,
  `occurred_at` datetime NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_alert_event_key` (`event_key`),
  KEY `idx_finance_alert_event_history` (`alert_id`,`occurred_at`,`id`),
  KEY `idx_finance_alert_event_source` (`source_domain`,`source_type`,`source_id`),
  CONSTRAINT `fk_finance_alert_event_alert` FOREIGN KEY (`alert_id`) REFERENCES `finance_alerts` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_alert_events`
--

LOCK TABLES `finance_alert_events` WRITE;
/*!40000 ALTER TABLE `finance_alert_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_alert_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_alerts`
--

DROP TABLE IF EXISTS `finance_alerts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_alerts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `alert_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_domain` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `finance_import_batch_id` bigint DEFAULT NULL,
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_amount` decimal(18,2) DEFAULT NULL,
  `actual_amount` decimal(18,2) DEFAULT NULL,
  `difference_amount` decimal(18,2) DEFAULT NULL,
  `candidate_snapshot` json NOT NULL,
  `status` enum('open','claimed','resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `claimed_by` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claimed_at` datetime DEFAULT NULL,
  `resolved_by` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `resolution_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_alert_key` (`alert_key`),
  KEY `idx_finance_alert_status` (`status`,`created_at`),
  KEY `idx_finance_alert_source` (`source_domain`,`source_type`,`source_id`),
  KEY `idx_finance_alert_import_row` (`finance_import_row_id`),
  KEY `idx_finance_alert_import_batch` (`finance_import_batch_id`),
  CONSTRAINT `fk_finance_alert_import_batch` FOREIGN KEY (`finance_import_batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_alert_import_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_alert_actual_amount` CHECK (((`actual_amount` is null) or (`actual_amount` >= 0))),
  CONSTRAINT `chk_finance_alert_expected_amount` CHECK (((`expected_amount` is null) or (`expected_amount` >= 0))),
  CONSTRAINT `chk_finance_alert_workflow` CHECK ((((`status` = _utf8mb4'open') and (`claimed_by` is null) and (`claimed_at` is null) and (`resolved_by` is null) and (`resolved_at` is null) and (`resolution_reason` is null)) or ((`status` = _utf8mb4'claimed') and (`claimed_by` is not null) and (`claimed_at` is not null) and (`resolved_by` is null) and (`resolved_at` is null) and (`resolution_reason` is null)) or ((`status` = _utf8mb4'resolved') and (((`claimed_by` is null) and (`claimed_at` is null)) or ((`claimed_by` is not null) and (`claimed_at` is not null))) and (`resolved_by` is not null) and (`resolved_at` is not null) and (`resolution_reason` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_alerts`
--

LOCK TABLES `finance_alerts` WRITE;
/*!40000 ALTER TABLE `finance_alerts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_alerts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_anomaly_occurrences`
--

DROP TABLE IF EXISTS `finance_anomaly_occurrences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_anomaly_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `occurrence_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `definition_code` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_anomaly_occurrences`
--

LOCK TABLES `finance_anomaly_occurrences` WRITE;
/*!40000 ALTER TABLE `finance_anomaly_occurrences` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_anomaly_occurrences` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_anomaly_occurrences_before_update` BEFORE UPDATE ON `finance_anomaly_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_anomaly_occurrences_before_delete` BEFORE DELETE ON `finance_anomaly_occurrences` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_anomaly_occurrences records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_apply_receipts`
--

DROP TABLE IF EXISTS `finance_import_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_apply_receipts`
--

LOCK TABLES `finance_import_apply_receipts` WRITE;
/*!40000 ALTER TABLE `finance_import_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_apply_receipt_before_update` BEFORE UPDATE ON `finance_import_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_apply_receipt_before_delete` BEFORE DELETE ON `finance_import_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_apply_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_batch_contracts`
--

DROP TABLE IF EXISTS `finance_import_batch_contracts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_batch_contracts` (
  `batch_id` bigint NOT NULL,
  `batch_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `classifier_version` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `fingerprint_version` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_version` bigint unsigned NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  UNIQUE KEY `uq_finance_import_batch_contract_identity` (`batch_identity`),
  CONSTRAINT `fk_finance_import_batch_contract_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_batch_contract_digest` CHECK (regexp_like(`source_content_digest`,_utf8mb4'^[0-9a-f]{64}$')),
  CONSTRAINT `chk_finance_import_batch_contract_text` CHECK (((char_length(trim(`batch_identity`)) > 0) and (char_length(trim(`classifier_version`)) > 0) and (char_length(trim(`fingerprint_version`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_batch_contracts`
--

LOCK TABLES `finance_import_batch_contracts` WRITE;
/*!40000 ALTER TABLE `finance_import_batch_contracts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_batch_contracts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_import_batches`
--

DROP TABLE IF EXISTS `finance_import_batches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_batches` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `format_id` enum('legacy','taishin','sinopac') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '空批次或過渡期多來源輸入允許 NULL',
  `sheet_name` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `header_row` int unsigned NOT NULL,
  `row_count` int unsigned NOT NULL DEFAULT '0',
  `status` enum('staged','completed','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'staged',
  `failure_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_batch_id_status` (`id`,`status`),
  KEY `idx_finance_import_batch_status` (`status`,`created_at`),
  CONSTRAINT `chk_finance_import_batch_header_row` CHECK ((`header_row` >= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_batches`
--

LOCK TABLES `finance_import_batches` WRITE;
/*!40000 ALTER TABLE `finance_import_batches` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_batches` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_import_classification_events`
--

DROP TABLE IF EXISTS `finance_import_classification_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_classification_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `classification_version` bigint unsigned NOT NULL,
  `canonical_fact_version` bigint unsigned NOT NULL,
  `classification_type` enum('client_receipt','client_refund','client_refund_return','client_subsidy_return','government_subsidy','staff_payout','non_business_review') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `disposition` enum('create','existing','manual_review','business_pending','blocked') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `decision_facts_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_identities` json NOT NULL,
  `evidence` json NOT NULL,
  `available_actions` json NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_classification_events`
--

LOCK TABLES `finance_import_classification_events` WRITE;
/*!40000 ALTER TABLE `finance_import_classification_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_classification_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_classification_before_update` BEFORE UPDATE ON `finance_import_classification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_classification_before_delete` BEFORE DELETE ON `finance_import_classification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_classification_events cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_correction_receipts`
--

DROP TABLE IF EXISTS `finance_import_correction_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_correction_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_correction_receipts`
--

LOCK TABLES `finance_import_correction_receipts` WRITE;
/*!40000 ALTER TABLE `finance_import_correction_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_correction_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_correction_receipt_before_update` BEFORE UPDATE ON `finance_import_correction_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_correction_receipt_before_delete` BEFORE DELETE ON `finance_import_correction_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_correction_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_dispatch_events`
--

DROP TABLE IF EXISTS `finance_import_dispatch_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_dispatch_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `plan_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `outcome` enum('reconciled','existing','pending','rejected','conflict') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_dispatch_events`
--

LOCK TABLES `finance_import_dispatch_events` WRITE;
/*!40000 ALTER TABLE `finance_import_dispatch_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_dispatch_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_dispatch_before_update` BEFORE UPDATE ON `finance_import_dispatch_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_dispatch_before_delete` BEFORE DELETE ON `finance_import_dispatch_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_dispatch_events cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_historical_reprocess_receipts`
--

DROP TABLE IF EXISTS `finance_import_historical_reprocess_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_historical_reprocess_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_historical_reprocess_receipts`
--

LOCK TABLES `finance_import_historical_reprocess_receipts` WRITE;
/*!40000 ALTER TABLE `finance_import_historical_reprocess_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_historical_reprocess_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_historical_reprocess_receipt_before_update` BEFORE UPDATE ON `finance_import_historical_reprocess_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_historical_reprocess_receipt_before_delete` BEFORE DELETE ON `finance_import_historical_reprocess_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_historical_reprocess_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_ingestion_receipts`
--

DROP TABLE IF EXISTS `finance_import_ingestion_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_ingestion_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_content_digest` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_ingestion_receipts`
--

LOCK TABLES `finance_import_ingestion_receipts` WRITE;
/*!40000 ALTER TABLE `finance_import_ingestion_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_ingestion_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_ingestion_receipt_before_update` BEFORE UPDATE ON `finance_import_ingestion_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_ingestion_receipt_before_delete` BEFORE DELETE ON `finance_import_ingestion_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_ingestion_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_integrity_events`
--

DROP TABLE IF EXISTS `finance_import_integrity_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_integrity_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `issue_code` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_integrity_events`
--

LOCK TABLES `finance_import_integrity_events` WRITE;
/*!40000 ALTER TABLE `finance_import_integrity_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_integrity_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_integrity_before_update` BEFORE UPDATE ON `finance_import_integrity_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_integrity_before_delete` BEFORE DELETE ON `finance_import_integrity_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_integrity_events cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_occurrences`
--

DROP TABLE IF EXISTS `finance_import_occurrences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_occurrences` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `source_file` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sheet_name` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_occurrences`
--

LOCK TABLES `finance_import_occurrences` WRITE;
/*!40000 ALTER TABLE `finance_import_occurrences` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_occurrences` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_import_outbox`
--

DROP TABLE IF EXISTS `finance_import_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('dispatch_completed','manual_correction_completed','initial_classification_recorded','historical_reprocess_completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_outbox_intent` (`intent_key`),
  KEY `idx_finance_import_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_finance_import_outbox_batch` (`batch_id`),
  CONSTRAINT `fk_finance_import_outbox_batch` FOREIGN KEY (`batch_id`) REFERENCES `finance_import_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_outbox`
--

LOCK TABLES `finance_import_outbox` WRITE;
/*!40000 ALTER TABLE `finance_import_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `finance_import_reclassification_events`
--

DROP TABLE IF EXISTS `finance_import_reclassification_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_reclassification_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `actor` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_classification_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_classification_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `before_matched_identity_ids` json NOT NULL,
  `before_resolved_counterparty_account` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `after_classification_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_classification_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `after_matched_identity_ids` json NOT NULL,
  `after_resolved_counterparty_account` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dispatch_result` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `dispatch_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dispatch_references` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_finance_import_reclassification_event_row` (`run_id`,`finance_import_row_id`),
  KEY `idx_finance_import_reclassification_event_row` (`finance_import_row_id`,`created_at`),
  CONSTRAINT `fk_finance_import_reclassification_event_row` FOREIGN KEY (`finance_import_row_id`) REFERENCES `finance_import_rows` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_finance_import_reclassification_event_run` FOREIGN KEY (`run_id`) REFERENCES `finance_import_reprocess_runs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_finance_import_reclassification_event_actor` CHECK ((char_length(trim(`actor`)) > 0)),
  CONSTRAINT `chk_finance_import_reclassification_event_changed` CHECK (((not((`before_classification_type` <=> `after_classification_type`))) or (not((`before_classification_reason` <=> `after_classification_reason`))) or (not((`before_matched_identity_ids` <=> `after_matched_identity_ids`))) or (not((`before_resolved_counterparty_account` <=> `after_resolved_counterparty_account`)))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_reclassification_events`
--

LOCK TABLES `finance_import_reclassification_events` WRITE;
/*!40000 ALTER TABLE `finance_import_reclassification_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_reclassification_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reclassification_events_before_update` BEFORE UPDATE ON `finance_import_reclassification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reclassification_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reclassification_events_before_delete` BEFORE DELETE ON `finance_import_reclassification_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reclassification_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_reconciliation_receipts`
--

DROP TABLE IF EXISTS `finance_import_reconciliation_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_reconciliation_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `finance_import_row_id` bigint NOT NULL,
  `candidate_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `owning_domain` enum('client_finance','staff_payables') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_reconciliation_receipts`
--

LOCK TABLES `finance_import_reconciliation_receipts` WRITE;
/*!40000 ALTER TABLE `finance_import_reconciliation_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_reconciliation_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reconciliation_before_update` BEFORE UPDATE ON `finance_import_reconciliation_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reconciliation_before_delete` BEFORE DELETE ON `finance_import_reconciliation_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reconciliation_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_reprocess_runs`
--

DROP TABLE IF EXISTS `finance_import_reprocess_runs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_reprocess_runs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `batch_status` enum('staged','completed','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'completed',
  `actor` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `classifier_version` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `selected_count` int unsigned NOT NULL,
  `changed_count` int unsigned NOT NULL,
  `dispatch_count` int unsigned NOT NULL,
  `reconciled_count` int unsigned NOT NULL,
  `pending_count` int unsigned NOT NULL,
  `request_summary` json NOT NULL,
  `result_summary` json NOT NULL,
  `status` enum('completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'completed',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_reprocess_runs`
--

LOCK TABLES `finance_import_reprocess_runs` WRITE;
/*!40000 ALTER TABLE `finance_import_reprocess_runs` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_reprocess_runs` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reprocess_runs_before_update` BEFORE UPDATE ON `finance_import_reprocess_runs` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_finance_import_reprocess_runs_before_delete` BEFORE DELETE ON `finance_import_reprocess_runs` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'finance_import_reprocess_runs records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `finance_import_rows`
--

DROP TABLE IF EXISTS `finance_import_rows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `finance_import_rows` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dedup_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint DEFAULT NULL COMMENT '首度建立 canonical row 的相容批次；後續出現以 occurrence 為準',
  `format_id` enum('legacy','taishin','sinopac') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_file` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '首度出現來源，相容既有 writer',
  `source_bank_account` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sheet_name` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '首度出現工作表，相容既有 writer',
  `source_row` int unsigned DEFAULT NULL COMMENT '首度出現的一基底列號，相容既有 writer',
  `source_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行原始參考值；不承擔唯一性',
  `transaction_date` date DEFAULT NULL,
  `transaction_time` time DEFAULT NULL,
  `posting_date` date DEFAULT NULL,
  `value_date` date DEFAULT NULL,
  `debit` decimal(18,2) DEFAULT NULL,
  `credit` decimal(18,2) DEFAULT NULL,
  `direction` enum('incoming','outgoing','unknown') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `balance` decimal(18,2) DEFAULT NULL,
  `currency` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `summary` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `memo` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `counterparty_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `counterparty_account` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolved_counterparty_account` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cancellation_code` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `bank_references` json NOT NULL,
  `warnings` json NOT NULL,
  `raw_payload` json NOT NULL,
  `matched_identity_ids` json NOT NULL DEFAULT (json_array()),
  `classification_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `classification_reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `classified_at` timestamp NULL DEFAULT NULL,
  `reconciliation_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reconciliation_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_rows`
--

LOCK TABLES `finance_import_rows` WRITE;
/*!40000 ALTER TABLE `finance_import_rows` DISABLE KEYS */;
/*!40000 ALTER TABLE `finance_import_rows` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `financial_adjustment_apply_receipts`
--

DROP TABLE IF EXISTS `financial_adjustment_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `financial_adjustment_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `financial_adjustment_apply_receipts`
--

LOCK TABLES `financial_adjustment_apply_receipts` WRITE;
/*!40000 ALTER TABLE `financial_adjustment_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `financial_adjustment_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustment_receipt_before_update` BEFORE UPDATE ON `financial_adjustment_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustment_receipt_before_delete` BEFORE DELETE ON `financial_adjustment_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `financial_adjustment_staff_allocations`
--

DROP TABLE IF EXISTS `financial_adjustment_staff_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `financial_adjustment_staff_allocations`
--

LOCK TABLES `financial_adjustment_staff_allocations` WRITE;
/*!40000 ALTER TABLE `financial_adjustment_staff_allocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `financial_adjustment_staff_allocations` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustment_staff_before_update` BEFORE UPDATE ON `financial_adjustment_staff_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustment_staff_before_delete` BEFORE DELETE ON `financial_adjustment_staff_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustment staff allocations cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `financial_adjustments`
--

DROP TABLE IF EXISTS `financial_adjustments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `financial_adjustments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `adjustment_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_source_type` enum('preview_recalculation','manual_extra') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_scope` enum('client_only','client_and_staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'client_and_staff',
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_delta_ntd` bigint NOT NULL,
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reversal_of_adjustment_id` bigint DEFAULT NULL,
  `cancelled_at` timestamp NULL DEFAULT NULL,
  `apply_idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `financial_adjustments`
--

LOCK TABLES `financial_adjustments` WRITE;
/*!40000 ALTER TABLE `financial_adjustments` DISABLE KEYS */;
/*!40000 ALTER TABLE `financial_adjustments` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustments_before_update` BEFORE UPDATE ON `financial_adjustments` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_financial_adjustments_before_delete` BEFORE DELETE ON `financial_adjustments` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'financial adjustments cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_allocations`
--

DROP TABLE IF EXISTS `government_subsidy_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `transaction_id` bigint NOT NULL,
  `claim_batch_id` bigint NOT NULL,
  `claim_item_id` bigint NOT NULL,
  `allocation_type` enum('receipt','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
  `allocated_amount` decimal(18,2) NOT NULL,
  `reversal_of_allocation_id` bigint DEFAULT NULL,
  `reversal_target_type` enum('receipt','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_allocations`
--

LOCK TABLES `government_subsidy_allocations` WRITE;
/*!40000 ALTER TABLE `government_subsidy_allocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_allocations` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_allocations_before_update` BEFORE UPDATE ON `government_subsidy_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_allocations_before_delete` BEFORE DELETE ON `government_subsidy_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_allocations cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_apply_receipts`
--

DROP TABLE IF EXISTS `government_subsidy_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` enum('receipt','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_id` bigint NOT NULL,
  `batch_id` bigint NOT NULL,
  `batch_version` bigint unsigned NOT NULL,
  `bank_fact_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint unsigned NOT NULL,
  `allocation_count` int unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_apply_receipts`
--

LOCK TABLES `government_subsidy_apply_receipts` WRITE;
/*!40000 ALTER TABLE `government_subsidy_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_receipts_before_update` BEFORE UPDATE ON `government_subsidy_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_receipts_before_delete` BEFORE DELETE ON `government_subsidy_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_apply_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_batch_accounts`
--

DROP TABLE IF EXISTS `government_subsidy_batch_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_batch_accounts` (
  `batch_id` bigint NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL,
  `requested_total_ntd` bigint unsigned NOT NULL,
  `approved_total_ntd` bigint unsigned NOT NULL,
  `net_allocated_ntd` bigint unsigned NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_id`),
  CONSTRAINT `fk_government_subsidy_account_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_account_totals` CHECK (((`approved_total_ntd` <= `requested_total_ntd`) and (`net_allocated_ntd` <= `approved_total_ntd`) and (`outstanding_ntd` = (`approved_total_ntd` - `net_allocated_ntd`)))),
  CONSTRAINT `chk_government_subsidy_account_version` CHECK ((`aggregate_version` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_batch_accounts`
--

LOCK TABLES `government_subsidy_batch_accounts` WRITE;
/*!40000 ALTER TABLE `government_subsidy_batch_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_batch_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `government_subsidy_claim_apply_receipts`
--

DROP TABLE IF EXISTS `government_subsidy_claim_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_claim_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_kind` enum('plan','submit','approval') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `batch_id` bigint NOT NULL,
  `batch_version` bigint unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_count` int unsigned NOT NULL,
  `total_ntd` bigint unsigned NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_claim_apply_receipts`
--

LOCK TABLES `government_subsidy_claim_apply_receipts` WRITE;
/*!40000 ALTER TABLE `government_subsidy_claim_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_claim_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_claim_receipt_before_update` BEFORE UPDATE ON `government_subsidy_claim_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_claim_receipt_before_delete` BEFORE DELETE ON `government_subsidy_claim_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy claim receipt cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_claim_approval_events`
--

DROP TABLE IF EXISTS `government_subsidy_claim_approval_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_claim_approval_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `approved_total_ntd` bigint unsigned NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_claim_approval_events`
--

LOCK TABLES `government_subsidy_claim_approval_events` WRITE;
/*!40000 ALTER TABLE `government_subsidy_claim_approval_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_claim_approval_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_approval_before_update` BEFORE UPDATE ON `government_subsidy_claim_approval_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_approval_before_delete` BEFORE DELETE ON `government_subsidy_claim_approval_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_claim_approval_items`
--

DROP TABLE IF EXISTS `government_subsidy_claim_approval_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_claim_approval_items`
--

LOCK TABLES `government_subsidy_claim_approval_items` WRITE;
/*!40000 ALTER TABLE `government_subsidy_claim_approval_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_claim_approval_items` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_approval_item_before_update` BEFORE UPDATE ON `government_subsidy_claim_approval_items` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_approval_item_before_delete` BEFORE DELETE ON `government_subsidy_claim_approval_items` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy approval item cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_claim_outbox`
--

DROP TABLE IF EXISTS `government_subsidy_claim_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_claim_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('plan','submit','approval') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_government_subsidy_claim_outbox_intent` (`intent_key`),
  KEY `idx_government_subsidy_claim_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_government_subsidy_claim_outbox_batch` (`batch_id`),
  CONSTRAINT `fk_government_subsidy_claim_outbox_batch` FOREIGN KEY (`batch_id`) REFERENCES `subsidy_claim_batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_government_subsidy_claim_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_claim_outbox`
--

LOCK TABLES `government_subsidy_claim_outbox` WRITE;
/*!40000 ALTER TABLE `government_subsidy_claim_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_claim_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `government_subsidy_claim_submission_events`
--

DROP TABLE IF EXISTS `government_subsidy_claim_submission_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_claim_submission_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_claim_submission_events`
--

LOCK TABLES `government_subsidy_claim_submission_events` WRITE;
/*!40000 ALTER TABLE `government_subsidy_claim_submission_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_claim_submission_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_submission_before_update` BEFORE UPDATE ON `government_subsidy_claim_submission_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_submission_before_delete` BEFORE DELETE ON `government_subsidy_claim_submission_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government subsidy submission cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_outbox`
--

DROP TABLE IF EXISTS `government_subsidy_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `transaction_id` bigint NOT NULL,
  `projection_event_id` bigint NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('government_subsidy_receipt_applied','government_subsidy_receipt_allocated','government_subsidy_reversal_applied','government_subsidy_anomaly_root_changed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_outbox`
--

LOCK TABLES `government_subsidy_outbox` WRITE;
/*!40000 ALTER TABLE `government_subsidy_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `government_subsidy_projection_events`
--

DROP TABLE IF EXISTS `government_subsidy_projection_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_projection_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `transaction_id` bigint NOT NULL,
  `before_status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_net_allocated_ntd` bigint unsigned NOT NULL,
  `after_net_allocated_ntd` bigint unsigned NOT NULL,
  `outstanding_ntd` bigint unsigned NOT NULL,
  `expected_batch_version` bigint unsigned NOT NULL,
  `resulting_batch_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_projection_events`
--

LOCK TABLES `government_subsidy_projection_events` WRITE;
/*!40000 ALTER TABLE `government_subsidy_projection_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_projection_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_projection_events_before_update` BEFORE UPDATE ON `government_subsidy_projection_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_projection_events_before_delete` BEFORE DELETE ON `government_subsidy_projection_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_projection_events cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `government_subsidy_transactions`
--

DROP TABLE IF EXISTS `government_subsidy_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `government_subsidy_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `claim_batch_id` bigint NOT NULL,
  `finance_import_row_id` bigint NOT NULL,
  `transaction_type` enum('receipt','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(18,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `reversal_target_type` enum('receipt','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'receipt',
  `expected_batch_version` bigint unsigned DEFAULT NULL,
  `resulting_batch_version` bigint unsigned DEFAULT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `government_subsidy_transactions`
--

LOCK TABLES `government_subsidy_transactions` WRITE;
/*!40000 ALTER TABLE `government_subsidy_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `government_subsidy_transactions` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_transactions_before_update` BEFORE UPDATE ON `government_subsidy_transactions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_government_subsidy_transactions_before_delete` BEFORE DELETE ON `government_subsidy_transactions` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_subsidy_transactions cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `holidays`
--

DROP TABLE IF EXISTS `holidays`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `holidays` (
  `holiday_date` date NOT NULL COMMENT '假日日期',
  `holiday_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '假日名稱',
  `is_double_pay_default` tinyint(1) DEFAULT '0' COMMENT '相容欄位；排班不因國定假日自動套用雙倍薪資',
  PRIMARY KEY (`holiday_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `holidays`
--

LOCK TABLES `holidays` WRITE;
/*!40000 ALTER TABLE `holidays` DISABLE KEYS */;
/*!40000 ALTER TABLE `holidays` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_confirmation_requests`
--

DROP TABLE IF EXISTS `line_confirmation_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_confirmation_requests` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_type` enum('staff_verification','client_rebind') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `client_id` int DEFAULT NULL,
  `client_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `old_line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `new_line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` enum('pending','approved','rejected','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `reviewed_by_admin_user_id` bigint DEFAULT NULL COMMENT 'Web 管理中心處理者；開發終端處理時可為 NULL',
  `reviewed_by_line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `decision_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '核准備註或拒絕原因',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_confirmation_requests`
--

LOCK TABLES `line_confirmation_requests` WRITE;
/*!40000 ALTER TABLE `line_confirmation_requests` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_confirmation_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_rich_menu_publications`
--

DROP TABLE IF EXISTS `line_rich_menu_publications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_rich_menu_publications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `menu_config_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `audience_role` enum('customer','staff','union_staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_revision` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_snapshot` json NOT NULL,
  `status` enum('pending','processing','published','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `line_rich_menu_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `previous_line_rich_menu_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `image_asset_id` bigint DEFAULT NULL,
  `requested_by_admin_user_id` bigint DEFAULT NULL,
  `retry_count` int NOT NULL DEFAULT '0',
  `max_retries` int NOT NULL DEFAULT '3',
  `next_retry_at` datetime DEFAULT NULL,
  `processing_started_at` datetime DEFAULT NULL,
  `is_current` tinyint(1) NOT NULL DEFAULT '0',
  `error_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_rich_menu_publications`
--

LOCK TABLES `line_rich_menu_publications` WRITE;
/*!40000 ALTER TABLE `line_rich_menu_publications` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_rich_menu_publications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_task_attempts`
--

DROP TABLE IF EXISTS `line_task_attempts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_task_attempts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `attempt_no` int NOT NULL,
  `outcome` enum('running','sent','retry_scheduled','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'running',
  `retryable` tinyint(1) DEFAULT NULL,
  `error_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `line_request_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `started_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `finished_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_task_attempt_no` (`task_id`,`attempt_no`),
  KEY `idx_line_task_attempt_outcome_time` (`outcome`,`started_at`),
  CONSTRAINT `fk_line_task_attempt_task` FOREIGN KEY (`task_id`) REFERENCES `line_tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_task_attempts`
--

LOCK TABLES `line_task_attempts` WRITE;
/*!40000 ALTER TABLE `line_task_attempts` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_task_attempts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_tasks`
--

DROP TABLE IF EXISTS `line_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `to_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '接收訊息的 LINE 用戶唯一識別碼',
  `task_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'line_push' COMMENT 'line_push/rag_reply/rich_menu_link/rich_menu_unlink',
  `message_content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '文字推播內容',
  `payload_json` json DEFAULT NULL COMMENT '非純文字任務參數',
  `status` enum('pending','processing','sent','failed','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `scheduled_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '預定發送時間；未指定時立即執行',
  `processing_started_at` datetime DEFAULT NULL,
  `retry_count` int NOT NULL DEFAULT '0',
  `max_retries` int NOT NULL DEFAULT '3',
  `next_retry_at` datetime DEFAULT NULL,
  `sent_at` datetime DEFAULT NULL,
  `failed_at` datetime DEFAULT NULL,
  `error_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `line_request_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_event_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `idempotency_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_task_idempotency` (`idempotency_key`),
  KEY `idx_line_tasks_due` (`status`,`scheduled_at`,`next_retry_at`,`id`),
  KEY `idx_line_tasks_processing` (`status`,`processing_started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_tasks`
--

LOCK TABLES `line_tasks` WRITE;
/*!40000 ALTER TABLE `line_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_users`
--

DROP TABLE IF EXISTS `line_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('customer','staff','union_staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'customer',
  `status` enum('active','blocked','unknown') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_users`
--

LOCK TABLES `line_users` WRITE;
/*!40000 ALTER TABLE `line_users` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `line_webhook_events`
--

DROP TABLE IF EXISTS `line_webhook_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `line_webhook_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `webhook_event_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_group_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_timestamp` bigint DEFAULT NULL,
  `is_redelivery` tinyint(1) NOT NULL DEFAULT '0',
  `processing_status` enum('received','processing','completed','failed','ignored') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'received',
  `payload_json` json NOT NULL,
  `received_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `processed_at` datetime DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_line_webhook_event_id` (`webhook_event_id`),
  KEY `idx_line_webhook_status` (`processing_status`,`received_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_webhook_events`
--

LOCK TABLES `line_webhook_events` WRITE;
/*!40000 ALTER TABLE `line_webhook_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `line_webhook_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `matching_records`
--

DROP TABLE IF EXISTS `matching_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `matching_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '對應 orders.case_no',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `matching_records`
--

LOCK TABLES `matching_records` WRITE;
/*!40000 ALTER TABLE `matching_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `matching_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `media_assets`
--

DROP TABLE IF EXISTS `media_assets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `media_assets` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `category` enum('rich_menu','line_user_upload','contract','other') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `owner_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `owner_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `storage_provider` enum('local','nas','s3') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'local',
  `storage_key` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mime_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` bigint NOT NULL,
  `sha256` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `media_assets`
--

LOCK TABLES `media_assets` WRITE;
/*!40000 ALTER TABLE `media_assets` DISABLE KEYS */;
/*!40000 ALTER TABLE `media_assets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `order_actual_start_apply_receipts`
--

DROP TABLE IF EXISTS `order_actual_start_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_actual_start_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_start_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `reconfirmation_control_event_id` bigint unsigned DEFAULT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_start_date` date NOT NULL,
  `actual_end_date` date NOT NULL,
  `service_data_lock_formed` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_actual_start_apply_receipts`
--

LOCK TABLES `order_actual_start_apply_receipts` WRITE;
/*!40000 ALTER TABLE `order_actual_start_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_actual_start_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_actual_start_receipts_before_update` BEFORE UPDATE ON `order_actual_start_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_actual_start_receipts_before_delete` BEFORE DELETE ON `order_actual_start_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_actual_start_events`
--

DROP TABLE IF EXISTS `order_actual_start_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_actual_start_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('confirmed','corrected','reconfirmed_after_delayed_settlement') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_actual_start_date` date DEFAULT NULL,
  `after_actual_start_date` date NOT NULL,
  `deposit_settlement_identity` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_actual_start_events`
--

LOCK TABLES `order_actual_start_events` WRITE;
/*!40000 ALTER TABLE `order_actual_start_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_actual_start_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_actual_start_events_before_update` BEFORE UPDATE ON `order_actual_start_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_actual_start_events_before_delete` BEFORE DELETE ON `order_actual_start_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_actual_start_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_assignment_change_audits`
--

DROP TABLE IF EXISTS `order_assignment_change_audits`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_assignment_change_audits` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_before_snapshot` json NOT NULL,
  `order_after_snapshot` json NOT NULL,
  `assignment_plan_snapshot` json NOT NULL,
  `applied_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_order_assignment_change_audit_case_time` (`case_no`,`applied_at`),
  CONSTRAINT `fk_order_assignment_change_audit_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_assignment_change_audit_applied_by` CHECK ((char_length(trim(`applied_by`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_assignment_change_audits`
--

LOCK TABLES `order_assignment_change_audits` WRITE;
/*!40000 ALTER TABLE `order_assignment_change_audits` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_assignment_change_audits` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `order_cancellation_apply_receipts`
--

DROP TABLE IF EXISTS `order_cancellation_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_cancellation_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint NOT NULL,
  `cancellation_control_event_id` bigint unsigned NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actual_end_date` date DEFAULT NULL,
  `official_service_day_count` int unsigned NOT NULL,
  `official_service_hours` int unsigned NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_cancellation_apply_receipts`
--

LOCK TABLES `order_cancellation_apply_receipts` WRITE;
/*!40000 ALTER TABLE `order_cancellation_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_cancellation_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_cancellation_receipts_before_update` BEFORE UPDATE ON `order_cancellation_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_cancellation_receipts_before_delete` BEFORE DELETE ON `order_cancellation_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_cancellation_events`
--

DROP TABLE IF EXISTS `order_cancellation_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_cancellation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_date` date NOT NULL,
  `actual_end_date` date DEFAULT NULL,
  `official_service_day_count` int unsigned NOT NULL,
  `official_service_hours` int unsigned NOT NULL,
  `confirmed_service_days` json NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_cancellation_events`
--

LOCK TABLES `order_cancellation_events` WRITE;
/*!40000 ALTER TABLE `order_cancellation_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_cancellation_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_cancellation_events_before_update` BEFORE UPDATE ON `order_cancellation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_cancellation_events_before_delete` BEFORE DELETE ON `order_cancellation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_cancellation_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_contract_completion_apply_receipts`
--

DROP TABLE IF EXISTS `order_contract_completion_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_contract_completion_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_event_id` bigint NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_contract_completion_apply_receipts`
--

LOCK TABLES `order_contract_completion_apply_receipts` WRITE;
/*!40000 ALTER TABLE `order_contract_completion_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_contract_completion_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_contract_completion_receipts_before_update` BEFORE UPDATE ON `order_contract_completion_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_contract_completion_receipts_before_delete` BEFORE DELETE ON `order_contract_completion_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_completion_apply_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_contract_flow_events`
--

DROP TABLE IF EXISTS `order_contract_flow_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_contract_flow_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('contract_completed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_contract_completed_case` (`case_no`,`event_type`),
  UNIQUE KEY `uq_order_contract_event_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_order_contract_event_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_contract_event_text` CHECK (((char_length(trim(`contract_identity`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_contract_flow_events`
--

LOCK TABLES `order_contract_flow_events` WRITE;
/*!40000 ALTER TABLE `order_contract_flow_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_contract_flow_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_contract_flow_events_before_update` BEFORE UPDATE ON `order_contract_flow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_contract_flow_events_before_delete` BEFORE DELETE ON `order_contract_flow_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_contract_flow_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_lifecycle_control_events`
--

DROP TABLE IF EXISTS `order_lifecycle_control_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_lifecycle_control_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_type` enum('cancellation','actual_start_reconfirmation','human_hold') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope` enum('order','enter_service','auto_complete') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('activate','clear') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_lifecycle_control_events`
--

LOCK TABLES `order_lifecycle_control_events` WRITE;
/*!40000 ALTER TABLE `order_lifecycle_control_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_lifecycle_control_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_lifecycle_control_events_before_update` BEFORE UPDATE ON `order_lifecycle_control_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_lifecycle_control_events_before_delete` BEFORE DELETE ON `order_lifecycle_control_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_lifecycle_control_state`
--

DROP TABLE IF EXISTS `order_lifecycle_control_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_lifecycle_control_state` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_type` enum('cancellation','actual_start_reconfirmation','human_hold') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `control_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope` enum('order','enter_service','auto_complete') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `state` enum('active','cleared') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `current_event_id` bigint unsigned NOT NULL,
  `release_policy` enum('manual','expires_at') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `expires_at_utc` datetime(6) DEFAULT NULL,
  `confirmed_start_date` date DEFAULT NULL,
  `deposit_settlement_identity_hash` char(64) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_lifecycle_control_state`
--

LOCK TABLES `order_lifecycle_control_state` WRITE;
/*!40000 ALTER TABLE `order_lifecycle_control_state` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_lifecycle_control_state` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_lifecycle_control_state_before_delete` BEFORE DELETE ON `order_lifecycle_control_state` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_control_state records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_lifecycle_projection_outbox`
--

DROP TABLE IF EXISTS `order_lifecycle_projection_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_lifecycle_projection_outbox` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `scope` enum('enter_service','auto_complete') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `alert_code` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` enum('open','resolve') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_hash` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','projected','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at_utc` datetime(6) DEFAULT NULL,
  `locked_at_utc` datetime(6) DEFAULT NULL,
  `projected_at_utc` datetime(6) DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_lifecycle_projection_outbox_intent` (`case_no`,`intent_key`),
  KEY `idx_order_lifecycle_projection_outbox_retry` (`status`,`next_attempt_at_utc`,`id`),
  KEY `idx_order_lifecycle_projection_outbox_event` (`case_no`,`lifecycle_event_id`),
  KEY `fk_order_lifecycle_projection_outbox_event` (`lifecycle_event_id`),
  CONSTRAINT `fk_order_lifecycle_projection_outbox_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_lifecycle_projection_outbox_event` FOREIGN KEY (`lifecycle_event_id`) REFERENCES `order_lifecycle_state_events` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_lifecycle_projection_outbox_payload` CHECK ((regexp_like(`payload_hash`,_utf8mb4'^[0-9a-f]{64}$') and (json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))),
  CONSTRAINT `chk_order_lifecycle_projection_outbox_status` CHECK ((((`status` = _utf8mb4'pending') and (`locked_at_utc` is null) and (`projected_at_utc` is null) and (`last_error` is null)) or ((`status` = _utf8mb4'processing') and (`locked_at_utc` is not null) and (`projected_at_utc` is null)) or ((`status` = _utf8mb4'projected') and (`projected_at_utc` is not null) and (`last_error` is null)) or ((`status` = _utf8mb4'failed') and (`projected_at_utc` is null) and (`last_error` is not null)))),
  CONSTRAINT `chk_order_lifecycle_projection_outbox_text` CHECK (((char_length(trim(`intent_key`)) > 0) and (char_length(trim(`alert_code`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_lifecycle_projection_outbox`
--

LOCK TABLES `order_lifecycle_projection_outbox` WRITE;
/*!40000 ALTER TABLE `order_lifecycle_projection_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_lifecycle_projection_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `order_lifecycle_state_events`
--

DROP TABLE IF EXISTS `order_lifecycle_state_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_lifecycle_state_events` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事件所屬訂單（對應 orders.case_no）',
  `trigger_event` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '觸發本次狀態評估的事件名稱',
  `before_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '狀態評估前的 canonical 訂單狀態',
  `after_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '狀態評估後的 canonical 訂單狀態；維持或阻擋時可與 before_status 相同',
  `actor` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '觸發事件的操作者或系統身分',
  `business_date` date NOT NULL COMMENT '狀態評估採用的業務日期',
  `expected_version` bigint unsigned NOT NULL COMMENT '呼叫端進行樂觀鎖定時讀取的訂單版本',
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '同一訂單內唯一的呼叫端冪等鍵',
  `facts_snapshot` json NOT NULL COMMENT '狀態評估當下的權威事實與決策摘要',
  `created_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '事件建立時間',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_lifecycle_state_event_idempotency` (`case_no`,`idempotency_key`),
  UNIQUE KEY `uq_order_lifecycle_state_event_case_identity` (`id`,`case_no`),
  KEY `idx_order_lifecycle_state_event_case_time` (`case_no`,`created_at`),
  CONSTRAINT `fk_order_lifecycle_state_event_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_lifecycle_state_event_after_status` CHECK ((`after_status` in (_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中',_utf8mb4'訂單完成',_utf8mb4'訂單取消'))),
  CONSTRAINT `chk_order_lifecycle_state_event_before_status` CHECK ((`before_status` in (_utf8mb4'洽談中',_utf8mb4'訂單成立',_utf8mb4'服務中',_utf8mb4'訂單完成',_utf8mb4'訂單取消'))),
  CONSTRAINT `chk_order_lifecycle_state_event_facts_snapshot` CHECK ((json_type(`facts_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_order_lifecycle_state_event_required_text` CHECK (((char_length(trim(`trigger_event`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`idempotency_key`)) > 0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_lifecycle_state_events`
--

LOCK TABLES `order_lifecycle_state_events` WRITE;
/*!40000 ALTER TABLE `order_lifecycle_state_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_lifecycle_state_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_lifecycle_state_events_before_update` BEFORE UPDATE ON `order_lifecycle_state_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_lifecycle_state_events_before_delete` BEFORE DELETE ON `order_lifecycle_state_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'order_lifecycle_state_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_reopen_apply_receipts`
--

DROP TABLE IF EXISTS `order_reopen_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_reopen_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reopen_event_id` bigint NOT NULL,
  `cancellation_control_event_id` bigint unsigned NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `requires_fresh_scheduling_preview` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_reopen_apply_receipts`
--

LOCK TABLES `order_reopen_apply_receipts` WRITE;
/*!40000 ALTER TABLE `order_reopen_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_reopen_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_reopen_receipts_before_update` BEFORE UPDATE ON `order_reopen_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_reopen_receipts_before_delete` BEFORE DELETE ON `order_reopen_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_reopen_events`
--

DROP TABLE IF EXISTS `order_reopen_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_reopen_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `cancellation_event_id` bigint NOT NULL,
  `before_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `after_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_reopen_events`
--

LOCK TABLES `order_reopen_events` WRITE;
/*!40000 ALTER TABLE `order_reopen_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_reopen_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_reopen_events_before_update` BEFORE UPDATE ON `order_reopen_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_reopen_events_before_delete` BEFORE DELETE ON `order_reopen_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_reopen_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_service_data_locks`
--

DROP TABLE IF EXISTS `order_service_data_locks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_service_data_locks` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `client_settlement_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  KEY `fk_order_service_data_lock_lifecycle_event` (`lifecycle_event_id`,`case_no`),
  CONSTRAINT `fk_order_service_data_lock_lifecycle_event` FOREIGN KEY (`lifecycle_event_id`, `case_no`) REFERENCES `order_lifecycle_state_events` (`id`, `case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_order_service_data_lock_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_order_service_data_lock_actor` CHECK ((char_length(trim(`created_by`)) > 0)),
  CONSTRAINT `chk_order_service_data_lock_fingerprint` CHECK (regexp_like(`client_settlement_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_service_data_locks`
--

LOCK TABLES `order_service_data_locks` WRITE;
/*!40000 ALTER TABLE `order_service_data_locks` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_service_data_locks` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_service_data_locks_before_update` BEFORE UPDATE ON `order_service_data_locks` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_service_data_locks_before_delete` BEFORE DELETE ON `order_service_data_locks` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_service_data_locks records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_terms_apply_receipts`
--

DROP TABLE IF EXISTS `order_terms_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_terms_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_terms_event_id` bigint NOT NULL,
  `scheduling_command_receipt_id` bigint NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `order_version` bigint unsigned NOT NULL,
  `scheduling_version` bigint unsigned NOT NULL,
  `scheduling_generation` int unsigned NOT NULL,
  `client_finance_version` bigint unsigned NOT NULL,
  `payroll_version` bigint unsigned NOT NULL,
  `lifecycle_status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `service_data_lock_formed` tinyint(1) NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_terms_apply_receipts`
--

LOCK TABLES `order_terms_apply_receipts` WRITE;
/*!40000 ALTER TABLE `order_terms_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_terms_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_terms_apply_receipts_before_update` BEFORE UPDATE ON `order_terms_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_terms_apply_receipts_before_delete` BEFORE DELETE ON `order_terms_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `order_terms_change_events`
--

DROP TABLE IF EXISTS `order_terms_change_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `order_terms_change_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `resulting_order_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_terms_change_events`
--

LOCK TABLES `order_terms_change_events` WRITE;
/*!40000 ALTER TABLE `order_terms_change_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `order_terms_change_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_terms_change_events_before_update` BEFORE UPDATE ON `order_terms_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_order_terms_change_events_before_delete` BEFORE DELETE ON `order_terms_change_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'order_terms_change_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `orders`
--

DROP TABLE IF EXISTS `orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '案件唯一識別碼；對應 clients.case_no',
  `client_id` int NOT NULL COMMENT '對應 clients.id',
  `staff_id` int DEFAULT NULL COMMENT '對應 staff.id (可為 NULL，代表尚未配對成功)',
  `status` enum('洽談中','訂單成立','服務中','訂單完成','訂單取消') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '洽談中' COMMENT '專案狀態 (生命週期: 洽談中→訂單成立→服務中→訂單完成, 任何階段可→訂單取消)',
  `lifecycle_version` bigint unsigned NOT NULL DEFAULT '0' COMMENT 'ORD-01 aggregate revision；每個非 replay command 恰遞增一次',
  `cancel_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT '當狀態變更為 訂單取消 時的取消原因說明',
  `line_group_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '三方服務 LINE 群組 ID',
  `actual_start_date` date DEFAULT NULL COMMENT '實際生產服務開始日',
  `actual_end_date` date DEFAULT NULL COMMENT '實際生產服務結束日',
  `staff_payment_due_date` date DEFAULT NULL,
  `service_start_time` time DEFAULT NULL COMMENT '案件統一每日服務開始時間；既有案件待明確補登',
  `service_end_time` time DEFAULT NULL COMMENT '案件統一每日服務結束時間；既有案件待明確補登',
  `service_end_day_offset` tinyint unsigned DEFAULT NULL COMMENT '0=服務日當日結束，1=次日結束；不得由時間大小推測',
  `contract_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '好好簽線上契約 ID',
  `service_days` int DEFAULT '0' COMMENT '服務天數 (N)',
  `service_hours_per_day` int DEFAULT '0' COMMENT '每日服務時數 (J)',
  `floor_fee` decimal(10,2) DEFAULT '0.00' COMMENT '樓層費用 (O)',
  `deposit_date` date DEFAULT NULL COMMENT '訂金收取日期',
  `deposit_service_days` int DEFAULT NULL COMMENT '訂金服務天數；NULL 表示歷史案件待人工補登',
  `start_date` date DEFAULT NULL COMMENT '預計/實際服務開始日 (AK)',
  `end_date` date DEFAULT NULL COMMENT '預計/實際服務結束日 (AL)',
  `custom_rest_dates` json DEFAULT NULL COMMENT '排定/自訂休假日期 JSON 陣列 (如 ["2026-07-05", "2026-07-12"])',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  KEY `client_id` (`client_id`),
  KEY `staff_id` (`staff_id`),
  KEY `idx_order_status` (`status`),
  CONSTRAINT `fk_orders_case_no` FOREIGN KEY (`case_no`) REFERENCES `clients` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`client_id`) REFERENCES `clients` (`id`) ON DELETE CASCADE,
  CONSTRAINT `orders_ibfk_2` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE SET NULL,
  CONSTRAINT `chk_orders_deposit_service_days_nonnegative` CHECK (((`deposit_service_days` is null) or (`deposit_service_days` >= 0))),
  CONSTRAINT `chk_orders_service_end_day_offset` CHECK (((`service_end_day_offset` is null) or (`service_end_day_offset` in (0,1)))),
  CONSTRAINT `chk_orders_service_time_terms_complete` CHECK ((((`service_start_time` is null) and (`service_end_time` is null) and (`service_end_day_offset` is null)) or ((`service_start_time` is not null) and (`service_end_time` is not null) and (`service_end_day_offset` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `orders`
--

LOCK TABLES `orders` WRITE;
/*!40000 ALTER TABLE `orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `orders_domain_outbox`
--

DROP TABLE IF EXISTS `orders_domain_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `orders_domain_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `lifecycle_event_id` bigint unsigned NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('lifecycle_projection_changed','service_data_locked','anomaly_root_changed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `orders_domain_outbox`
--

LOCK TABLES `orders_domain_outbox` WRITE;
/*!40000 ALTER TABLE `orders_domain_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `orders_domain_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payment_migration_reviews`
--

DROP TABLE IF EXISTS `payment_migration_reviews`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payment_migration_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `legacy_payment_id` int NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `legacy_caregiver_fee` decimal(12,2) NOT NULL,
  `legacy_caregiver_paid_at` date DEFAULT NULL,
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` enum('pending','resolved','dismissed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `resolved_at` timestamp NULL DEFAULT NULL,
  `resolution_notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payment_migration_review_legacy` (`legacy_payment_id`),
  KEY `idx_payment_migration_review_case` (`case_no`,`review_status`),
  CONSTRAINT `fk_payment_migration_review_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payment_migration_reviews`
--

LOCK TABLES `payment_migration_reviews` WRITE;
/*!40000 ALTER TABLE `payment_migration_reviews` DISABLE KEYS */;
/*!40000 ALTER TABLE `payment_migration_reviews` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_adjustment_allocations`
--

DROP TABLE IF EXISTS `payroll_adjustment_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_adjustment_allocations`
--

LOCK TABLES `payroll_adjustment_allocations` WRITE;
/*!40000 ALTER TABLE `payroll_adjustment_allocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_adjustment_allocations` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_adjustment_allocations_before_update` BEFORE UPDATE ON `payroll_adjustment_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_adjustment_allocations_before_delete` BEFORE DELETE ON `payroll_adjustment_allocations` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_allocations records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `payroll_adjustment_events`
--

DROP TABLE IF EXISTS `payroll_adjustment_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_adjustment_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `adjustment_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_adjustment_identity` (`adjustment_identity`),
  UNIQUE KEY `uq_payroll_adjustment_idempotency` (`idempotency_key`),
  KEY `fk_payroll_adjustment_order` (`case_no`),
  CONSTRAINT `fk_payroll_adjustment_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_adjustment_nonzero` CHECK ((`amount_ntd` <> 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_adjustment_events`
--

LOCK TABLES `payroll_adjustment_events` WRITE;
/*!40000 ALTER TABLE `payroll_adjustment_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_adjustment_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_adjustment_events_before_update` BEFORE UPDATE ON `payroll_adjustment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_adjustment_events_before_delete` BEFORE DELETE ON `payroll_adjustment_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_adjustment_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `payroll_apply_receipts`
--

DROP TABLE IF EXISTS `payroll_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_apply_receipts`
--

LOCK TABLES `payroll_apply_receipts` WRITE;
/*!40000 ALTER TABLE `payroll_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_apply_receipts_before_update` BEFORE UPDATE ON `payroll_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_apply_receipts_before_delete` BEFORE DELETE ON `payroll_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `payroll_case_accounts`
--

DROP TABLE IF EXISTS `payroll_case_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_case_accounts` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_no`),
  CONSTRAINT `fk_payroll_case_account_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_case_accounts`
--

LOCK TABLES `payroll_case_accounts` WRITE;
/*!40000 ALTER TABLE `payroll_case_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_case_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_outbox`
--

DROP TABLE IF EXISTS `payroll_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('staff_obligation_changed','payroll_anomaly_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_outbox_intent` (`intent_key`),
  KEY `idx_payroll_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_payroll_outbox_order` (`case_no`),
  CONSTRAINT `fk_payroll_outbox_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_payroll_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_outbox`
--

LOCK TABLES `payroll_outbox` WRITE;
/*!40000 ALTER TABLE `payroll_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_rate_policies`
--

DROP TABLE IF EXISTS `payroll_rate_policies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_rate_policies` (
  `policy_version` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `policy_kind` enum('citizen','subsidized_citizen','non_citizen') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `hourly_rate_ntd` bigint NOT NULL,
  `effective_from` date NOT NULL,
  `effective_until` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`policy_version`,`policy_kind`),
  CONSTRAINT `chk_payroll_rate_policy_amount` CHECK ((`hourly_rate_ntd` > 0)),
  CONSTRAINT `chk_payroll_rate_policy_interval` CHECK (((`effective_until` is null) or (`effective_until` >= `effective_from`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_rate_policies`
--

LOCK TABLES `payroll_rate_policies` WRITE;
/*!40000 ALTER TABLE `payroll_rate_policies` DISABLE KEYS */;
INSERT INTO `payroll_rate_policies` VALUES ('approved-rates-v1','citizen',300,'1900-01-01',NULL,'2026-08-03 23:28:06'),('approved-rates-v1','subsidized_citizen',350,'1900-01-01',NULL,'2026-08-03 23:28:06'),('approved-rates-v1','non_citizen',320,'1900-01-01',NULL,'2026-08-03 23:28:06');
/*!40000 ALTER TABLE `payroll_rate_policies` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_special_pay_events`
--

DROP TABLE IF EXISTS `payroll_special_pay_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_special_pay_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `service_date` date NOT NULL,
  `event_type` enum('double_pay') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_event_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payroll_special_pay_assignment_date` (`assignment_id`,`service_date`,`event_type`),
  UNIQUE KEY `uq_payroll_special_pay_idempotency` (`idempotency_key`),
  CONSTRAINT `fk_payroll_special_pay_assignment` FOREIGN KEY (`assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_special_pay_events`
--

LOCK TABLES `payroll_special_pay_events` WRITE;
/*!40000 ALTER TABLE `payroll_special_pay_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_special_pay_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_special_pay_events_before_update` BEFORE UPDATE ON `payroll_special_pay_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_payroll_special_pay_events_before_delete` BEFORE DELETE ON `payroll_special_pay_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'payroll_special_pay_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_aggregates`
--

DROP TABLE IF EXISTS `scheduling_aggregates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_aggregates` (
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_aggregates`
--

LOCK TABLES `scheduling_aggregates` WRITE;
/*!40000 ALTER TABLE `scheduling_aggregates` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_aggregates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduling_bootstrap_review_events`
--

DROP TABLE IF EXISTS `scheduling_bootstrap_review_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_bootstrap_review_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `issue_code` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `migration_identity` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `evidence_snapshot` json NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_bootstrap_review_issue` (`case_no`,`issue_code`,`migration_identity`),
  CONSTRAINT `fk_scheduling_bootstrap_review_order` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_bootstrap_review_code` CHECK (regexp_like(`issue_code`,_utf8mb4'^SCHED-BOOT-[0-9]{3}$')),
  CONSTRAINT `chk_scheduling_bootstrap_review_evidence` CHECK ((json_type(`evidence_snapshot`) = _utf8mb4'OBJECT')),
  CONSTRAINT `chk_scheduling_bootstrap_review_migration` CHECK ((char_length(trim(`migration_identity`)) > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_bootstrap_review_events`
--

LOCK TABLES `scheduling_bootstrap_review_events` WRITE;
/*!40000 ALTER TABLE `scheduling_bootstrap_review_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_bootstrap_review_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_bootstrap_review_events_before_update` BEFORE UPDATE ON `scheduling_bootstrap_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_bootstrap_review_events_before_delete` BEFORE DELETE ON `scheduling_bootstrap_review_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_bootstrap_review_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_buffer_days`
--

DROP TABLE IF EXISTS `scheduling_buffer_days`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_buffer_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `generation_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `buffer_date` date NOT NULL,
  `status` enum('active','released','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `active_marker` tinyint(1) DEFAULT '1',
  `released_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `released_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scheduling_buffer_assignment_date` (`assignment_id`,`buffer_date`),
  UNIQUE KEY `uq_scheduling_buffer_staff_date_active` (`staff_id`,`buffer_date`,`active_marker`),
  KEY `fk_scheduling_buffer_generation` (`generation_id`),
  KEY `fk_scheduling_buffer_assignment` (`assignment_id`,`generation_id`,`staff_id`),
  CONSTRAINT `fk_scheduling_buffer_assignment` FOREIGN KEY (`assignment_id`, `generation_id`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `generation_id`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_buffer_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_buffer_state` CHECK ((((`status` = _utf8mb4'active') and (`active_marker` = 1) and (`released_by` is null) and (`released_at` is null)) or ((`status` in (_utf8mb4'released',_utf8mb4'cancelled')) and (`active_marker` is null) and (char_length(trim(`released_by`)) > 0) and (`released_at` is not null))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_buffer_days`
--

LOCK TABLES `scheduling_buffer_days` WRITE;
/*!40000 ALTER TABLE `scheduling_buffer_days` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_buffer_days` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduling_command_receipts`
--

DROP TABLE IF EXISTS `scheduling_command_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_command_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_family` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `resulting_generation_id` bigint NOT NULL,
  `rebuild_event_id` bigint NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_command_receipts`
--

LOCK TABLES `scheduling_command_receipts` WRITE;
/*!40000 ALTER TABLE `scheduling_command_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_command_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_command_receipts_before_update` BEFORE UPDATE ON `scheduling_command_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_command_receipts_before_delete` BEFORE DELETE ON `scheduling_command_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_command_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_effective_occupancy`
--

DROP TABLE IF EXISTS `scheduling_effective_occupancy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_effective_occupancy` (
  `staff_id` int NOT NULL,
  `occupancy_date` date NOT NULL,
  `generation_id` bigint NOT NULL,
  `assignment_id` bigint NOT NULL,
  `occupancy_type` enum('assignment_interval','buffer') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`staff_id`,`occupancy_date`),
  KEY `idx_scheduling_effective_occupancy_generation` (`generation_id`),
  KEY `fk_scheduling_occupancy_assignment` (`assignment_id`,`generation_id`,`staff_id`),
  CONSTRAINT `fk_scheduling_occupancy_assignment` FOREIGN KEY (`assignment_id`, `generation_id`, `staff_id`) REFERENCES `case_staff_assignments` (`id`, `generation_id`, `staff_id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_occupancy_generation` FOREIGN KEY (`generation_id`) REFERENCES `scheduling_generations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_effective_occupancy`
--

LOCK TABLES `scheduling_effective_occupancy` WRITE;
/*!40000 ALTER TABLE `scheduling_effective_occupancy` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_effective_occupancy` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduling_generations`
--

DROP TABLE IF EXISTS `scheduling_generations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_generations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `generation_number` int unsigned NOT NULL,
  `resulting_aggregate_version` bigint unsigned NOT NULL,
  `status` enum('preparing','effective','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `effective_marker` tinyint(1) DEFAULT NULL,
  `created_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `change_reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_generations`
--

LOCK TABLES `scheduling_generations` WRITE;
/*!40000 ALTER TABLE `scheduling_generations` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_generations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduling_leave_occupancy_days`
--

DROP TABLE IF EXISTS `scheduling_leave_occupancy_days`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_leave_occupancy_days` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_index` int unsigned NOT NULL,
  `outcome_id` bigint NOT NULL,
  `generation_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `occupancy_date` date NOT NULL,
  `status` enum('active','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `active_marker` tinyint(1) DEFAULT '1',
  `cancelled_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_leave_occupancy_days`
--

LOCK TABLES `scheduling_leave_occupancy_days` WRITE;
/*!40000 ALTER TABLE `scheduling_leave_occupancy_days` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_leave_occupancy_days` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduling_leave_substitution_batches`
--

DROP TABLE IF EXISTS `scheduling_leave_substitution_batches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_leave_substitution_batches` (
  `batch_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_assignment_id` bigint NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `request_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `item_count` int unsigned NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_snapshot` json NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`batch_key`),
  KEY `idx_scheduling_leave_batch_case_time` (`case_no`,`created_at`),
  KEY `fk_scheduling_leave_batch_original_assignment` (`original_assignment_id`),
  CONSTRAINT `fk_scheduling_leave_batch_case` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_scheduling_leave_batch_original_assignment` FOREIGN KEY (`original_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_scheduling_leave_batch_fingerprints` CHECK ((regexp_like(`command_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`preview_fingerprint`,_utf8mb4'^[0-9a-f]{64}$') and regexp_like(`request_fingerprint`,_utf8mb4'^[0-9a-f]{64}$'))),
  CONSTRAINT `chk_scheduling_leave_batch_identity` CHECK (((`item_count` > 0) and (char_length(trim(`batch_key`)) > 0) and (char_length(trim(`actor`)) > 0) and (char_length(trim(`reason`)) > 0) and (char_length(trim(`correlation_id`)) > 0) and (json_type(`request_snapshot`) = _utf8mb4'OBJECT')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_leave_substitution_batches`
--

LOCK TABLES `scheduling_leave_substitution_batches` WRITE;
/*!40000 ALTER TABLE `scheduling_leave_substitution_batches` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_leave_substitution_batches` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_batches_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_batches_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_batches` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_batches cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_leave_substitution_outcomes`
--

DROP TABLE IF EXISTS `scheduling_leave_substitution_outcomes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_leave_substitution_outcomes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_index` int unsigned NOT NULL,
  `event_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `original_assignment_id` bigint NOT NULL,
  `original_schedule_id` int NOT NULL,
  `original_staff_id` int NOT NULL,
  `original_work_date` date NOT NULL,
  `resolution_type` enum('defer_following_assignments','substitute') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_leave_substitution_outcomes`
--

LOCK TABLES `scheduling_leave_substitution_outcomes` WRITE;
/*!40000 ALTER TABLE `scheduling_leave_substitution_outcomes` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_leave_substitution_outcomes` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_outcomes_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_outcomes` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_outcomes_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_outcomes` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_outcomes cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_leave_substitution_receipts`
--

DROP TABLE IF EXISTS `scheduling_leave_substitution_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_leave_substitution_receipts` (
  `batch_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_leave_substitution_receipts`
--

LOCK TABLES `scheduling_leave_substitution_receipts` WRITE;
/*!40000 ALTER TABLE `scheduling_leave_substitution_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_leave_substitution_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_receipts_before_update` BEFORE UPDATE ON `scheduling_leave_substitution_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_leave_receipts_before_delete` BEFORE DELETE ON `scheduling_leave_substitution_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_leave_substitution_receipts cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_rebuild_events`
--

DROP TABLE IF EXISTS `scheduling_rebuild_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_rebuild_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `previous_generation_id` bigint DEFAULT NULL,
  `new_generation_id` bigint NOT NULL,
  `expected_order_version` bigint unsigned NOT NULL,
  `expected_scheduling_version` bigint unsigned NOT NULL,
  `resulting_scheduling_version` bigint unsigned NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correlation_id` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_rebuild_events`
--

LOCK TABLES `scheduling_rebuild_events` WRITE;
/*!40000 ALTER TABLE `scheduling_rebuild_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_rebuild_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_rebuild_events_before_update` BEFORE UPDATE ON `scheduling_rebuild_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_rebuild_events_before_delete` BEFORE DELETE ON `scheduling_rebuild_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `scheduling_rebuild_lineage`
--

DROP TABLE IF EXISTS `scheduling_rebuild_lineage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduling_rebuild_lineage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `rebuild_event_id` bigint NOT NULL,
  `old_assignment_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_rebuild_lineage`
--

LOCK TABLES `scheduling_rebuild_lineage` WRITE;
/*!40000 ALTER TABLE `scheduling_rebuild_lineage` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduling_rebuild_lineage` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_rebuild_lineage_before_update` BEFORE UPDATE ON `scheduling_rebuild_lineage` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_scheduling_rebuild_lineage_before_delete` BEFORE DELETE ON `scheduling_rebuild_lineage` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_rebuild_lineage records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `staff`
--

DROP TABLE IF EXISTS `staff`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff` (
  `id` int NOT NULL AUTO_INCREMENT,
  `registered_at` datetime DEFAULT NULL COMMENT '報名時間',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '註冊IP',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '姓名',
  `identity_card` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '身分證字號',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行動電話',
  `tel` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '市話',
  `tel_ext` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分機',
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'EMAIL',
  `birthday` date DEFAULT NULL COMMENT '生日 (由民國生日整合)',
  `city` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '居住縣市',
  `zip_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '郵遞區號',
  `address` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '詳細地址',
  `has_massage_cert` tinyint(1) DEFAULT '0' COMMENT '有嬰幼兒按摩證書嗎',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'active' COMMENT '在職狀態 (active/inactive)',
  `line_user_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'LINE 平台用戶唯一識別碼 (Webhook 取得)',
  `weekly_rest_days` json DEFAULT NULL COMMENT '固定休假偏好 JSON 陣列 (如 ["Sunday"])',
  `care_babies` int DEFAULT '1' COMMENT '最大可照顧寶寶數量 (1:單胞胎, 2:雙胞胎, 3:三胞胎)',
  `service_regions` json DEFAULT NULL COMMENT '接受服務區域 JSON 陣列',
  `special_skills` json DEFAULT NULL COMMENT '特殊技能與偏好標籤 JSON 陣列',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `identity_card` (`identity_card`),
  KEY `idx_staff_name` (`name`),
  KEY `idx_staff_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff`
--

LOCK TABLES `staff` WRITE;
/*!40000 ALTER TABLE `staff` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_actual_transfers`
--

DROP TABLE IF EXISTS `staff_actual_transfers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_actual_transfers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `settlement_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `payment_phase` enum('normal','first_salary','second_subsidy','unknown') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `transaction_type` enum('transfer','return','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `source_bank` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_account` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `counterparty_account` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `external_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_transfer_id` bigint DEFAULT NULL,
  `raw_import_reference` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `review_status` enum('not_required','pending','confirmed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_actual_transfers`
--

LOCK TABLES `staff_actual_transfers` WRITE;
/*!40000 ALTER TABLE `staff_actual_transfers` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_actual_transfers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_availability`
--

DROP TABLE IF EXISTS `staff_availability`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_availability` (
  `id` int NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `start_date` date NOT NULL COMMENT '可工作開始日期',
  `end_date` date NOT NULL COMMENT '可工作結束日期',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `staff_id` (`staff_id`),
  KEY `idx_avail_dates` (`start_date`,`end_date`),
  CONSTRAINT `staff_availability_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_availability`
--

LOCK TABLES `staff_availability` WRITE;
/*!40000 ALTER TABLE `staff_availability` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_availability` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_baby_types`
--

DROP TABLE IF EXISTS `staff_baby_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_baby_types` (
  `staff_id` int NOT NULL,
  `baby_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '胎數類型 (單胞胎/雙胞胎/其他)',
  `custom_baby_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他胎數的補充說明',
  PRIMARY KEY (`staff_id`,`baby_type`),
  CONSTRAINT `staff_baby_types_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_baby_types`
--

LOCK TABLES `staff_baby_types` WRITE;
/*!40000 ALTER TABLE `staff_baby_types` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_baby_types` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_bank_accounts`
--

DROP TABLE IF EXISTS `staff_bank_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_bank_accounts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `bank_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '銀行代碼(3碼)',
  `branch_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '分行代碼(4碼)',
  `account_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '銀行帳號',
  `is_primary` tinyint(1) DEFAULT '1' COMMENT '是否為主要帳戶',
  PRIMARY KEY (`id`),
  KEY `staff_id` (`staff_id`),
  CONSTRAINT `staff_bank_accounts_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_bank_accounts`
--

LOCK TABLES `staff_bank_accounts` WRITE;
/*!40000 ALTER TABLE `staff_bank_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_bank_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_bookings`
--

DROP TABLE IF EXISTS `staff_bookings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_bookings`
--

LOCK TABLES `staff_bookings` WRITE;
/*!40000 ALTER TABLE `staff_bookings` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_bookings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_cooking_skills`
--

DROP TABLE IF EXISTS `staff_cooking_skills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_cooking_skills` (
  `staff_id` int NOT NULL,
  `skill_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '料理類型 (葷食/素食/其他)',
  `custom_skill_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他料理的補充說明',
  PRIMARY KEY (`staff_id`,`skill_name`),
  CONSTRAINT `staff_cooking_skills_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_cooking_skills`
--

LOCK TABLES `staff_cooking_skills` WRITE;
/*!40000 ALTER TABLE `staff_cooking_skills` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_cooking_skills` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_holiday_availability`
--

DROP TABLE IF EXISTS `staff_holiday_availability`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_holiday_availability` (
  `staff_id` int NOT NULL,
  `holiday_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '節日名稱 (初一/初二/初三/端午/中秋/國定假日必休/其他)',
  `custom_holiday_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他節日的補充說明',
  PRIMARY KEY (`staff_id`,`holiday_name`),
  CONSTRAINT `staff_holiday_availability_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_holiday_availability`
--

LOCK TABLES `staff_holiday_availability` WRITE;
/*!40000 ALTER TABLE `staff_holiday_availability` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_holiday_availability` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_monthly_settlement_details`
--

DROP TABLE IF EXISTS `staff_monthly_settlement_details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_monthly_settlement_details` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `settlement_id` bigint NOT NULL,
  `staff_payment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `staff_id` int NOT NULL,
  `service_salary` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '一般服務薪資快照',
  `legacy_subsidy_payable` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '舊制補助應付構成快照',
  `floor_fee_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '樓層費快照',
  `adjustment_amount` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '可正可負的人工調整快照',
  `payable_amount` decimal(12,2) NOT NULL COMMENT '應付構成合計快照',
  `legacy_subsidy_status` enum('not_applicable','confirmed','review_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'not_applicable',
  `review_required` tinyint(1) NOT NULL DEFAULT '0',
  `review_note` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_monthly_settlement_details`
--

LOCK TABLES `staff_monthly_settlement_details` WRITE;
/*!40000 ALTER TABLE `staff_monthly_settlement_details` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_monthly_settlement_details` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_monthly_settlements`
--

DROP TABLE IF EXISTS `staff_monthly_settlements`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_monthly_settlements` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `settlement_month` date NOT NULL COMMENT '薪資歸屬月份；固定使用該月首日',
  `revision` int unsigned NOT NULL DEFAULT '1' COMMENT '同一服務人員同月的月結修訂版，從 1 起',
  `total_payable` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '月結明細應付快照合計',
  `total_paid` decimal(12,2) NOT NULL DEFAULT '0.00' COMMENT '成功轉帳分配的淨額投影，不得人工覆寫',
  `status` enum('draft','finalized','partially_paid','paid','cancelled','review_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_monthly_settlements`
--

LOCK TABLES `staff_monthly_settlements` WRITE;
/*!40000 ALTER TABLE `staff_monthly_settlements` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_monthly_settlements` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_obligation_events`
--

DROP TABLE IF EXISTS `staff_obligation_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_obligation_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_kind` enum('service_pay','adjustment','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('payable_to_staff','receivable_from_staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `event_type` enum('established','rebuilt','adjustment','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `before_amount_ntd` bigint NOT NULL,
  `after_amount_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `payroll_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `expected_payroll_version` bigint unsigned NOT NULL,
  `resulting_payroll_version` bigint unsigned NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_obligation_events`
--

LOCK TABLES `staff_obligation_events` WRITE;
/*!40000 ALTER TABLE `staff_obligation_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_obligation_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_obligation_events_before_update` BEFORE UPDATE ON `staff_obligation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_obligation_events_before_delete` BEFORE DELETE ON `staff_obligation_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_obligation_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `staff_obligations`
--

DROP TABLE IF EXISTS `staff_obligations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_obligations` (
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_kind` enum('service_pay','adjustment','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `direction` enum('payable_to_staff','receivable_from_staff') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `amount_due_ntd` bigint NOT NULL,
  `due_date` date DEFAULT NULL,
  `status` enum('open','settled','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_obligations`
--

LOCK TABLES `staff_obligations` WRITE;
/*!40000 ALTER TABLE `staff_obligations` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_obligations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payable_accounts`
--

DROP TABLE IF EXISTS `staff_payable_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payable_accounts` (
  `staff_id` int NOT NULL,
  `aggregate_version` bigint unsigned NOT NULL DEFAULT '0',
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`staff_id`),
  CONSTRAINT `fk_staff_payable_account_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payable_accounts`
--

LOCK TABLES `staff_payable_accounts` WRITE;
/*!40000 ALTER TABLE `staff_payable_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payable_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payable_projections`
--

DROP TABLE IF EXISTS `staff_payable_projections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payable_projections` (
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `obligation_amount_ntd` bigint NOT NULL,
  `net_paid_ntd` bigint NOT NULL,
  `balance_ntd` bigint NOT NULL,
  `status` enum('payable','completed','anomaly') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  CONSTRAINT `chk_staff_payable_projection_status` CHECK ((((`status` = _utf8mb4'payable') and (`net_paid_ntd` = 0) and (`balance_ntd` = `obligation_amount_ntd`)) or ((`status` = _utf8mb4'completed') and (`net_paid_ntd` = `obligation_amount_ntd`) and (`balance_ntd` = 0)) or ((`status` = _utf8mb4'anomaly') and (`net_paid_ntd` <> 0) and (`balance_ntd` <> 0))))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payable_projections`
--

LOCK TABLES `staff_payable_projections` WRITE;
/*!40000 ALTER TABLE `staff_payable_projections` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payable_projections` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payables_apply_receipts`
--

DROP TABLE IF EXISTS `staff_payables_apply_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payables_apply_receipts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `command_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `preview_fingerprint` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payables_apply_receipts`
--

LOCK TABLES `staff_payables_apply_receipts` WRITE;
/*!40000 ALTER TABLE `staff_payables_apply_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payables_apply_receipts` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payables_receipts_before_update` BEFORE UPDATE ON `staff_payables_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payables_receipts_before_delete` BEFORE DELETE ON `staff_payables_apply_receipts` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payables_apply_receipts records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `staff_payables_outbox`
--

DROP TABLE IF EXISTS `staff_payables_outbox`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payables_outbox` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `intent_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `intent_type` enum('payable_projection_refresh','payout_anomaly_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload_snapshot` json NOT NULL,
  `status` enum('pending','processing','delivered','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `attempt_count` int unsigned NOT NULL DEFAULT '0',
  `next_attempt_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `last_error` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_staff_payables_outbox_intent` (`intent_key`),
  KEY `idx_staff_payables_outbox_delivery` (`status`,`next_attempt_at`,`id`),
  KEY `fk_staff_payables_outbox_staff` (`staff_id`),
  CONSTRAINT `fk_staff_payables_outbox_staff` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `chk_staff_payables_outbox_payload` CHECK ((json_type(`payload_snapshot`) = _utf8mb4'OBJECT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payables_outbox`
--

LOCK TABLES `staff_payables_outbox` WRITE;
/*!40000 ALTER TABLE `staff_payables_outbox` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payables_outbox` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payment_transactions`
--

DROP TABLE IF EXISTS `staff_payment_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payment_transactions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_payment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `staff_id` int NOT NULL,
  `transaction_type` enum('transfer','reversal','return') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `transaction_status` enum('succeeded','failed','reversed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'succeeded',
  `amount` decimal(12,2) NOT NULL,
  `occurred_at` date DEFAULT NULL,
  `external_reference` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reversal_of_transaction_id` bigint DEFAULT NULL,
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payment_transactions`
--

LOCK TABLES `staff_payment_transactions` WRITE;
/*!40000 ALTER TABLE `staff_payment_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payment_transactions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payments`
--

DROP TABLE IF EXISTS `staff_payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `assignment_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  `payment_status` enum('pending','partially_paid','paid','cancelled','review_required') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payments`
--

LOCK TABLES `staff_payments` WRITE;
/*!40000 ALTER TABLE `staff_payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_payout_events`
--

DROP TABLE IF EXISTS `staff_payout_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payout_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `staff_id` int NOT NULL,
  `finance_import_row_id` bigint DEFAULT NULL,
  `event_type` enum('payout','return','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_ntd` bigint NOT NULL,
  `occurred_on` date NOT NULL,
  `bank_account_identity_hash` char(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reversal_of_event_id` bigint DEFAULT NULL,
  `reconciliation_reference` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `idempotency_key` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `actor` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payout_events`
--

LOCK TABLES `staff_payout_events` WRITE;
/*!40000 ALTER TABLE `staff_payout_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payout_events` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payout_events_before_update` BEFORE UPDATE ON `staff_payout_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payout_events_before_delete` BEFORE DELETE ON `staff_payout_events` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_events records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `staff_payout_obligation_links`
--

DROP TABLE IF EXISTS `staff_payout_obligation_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_payout_obligation_links` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `payout_event_id` bigint NOT NULL,
  `obligation_identity` varchar(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payout_obligation_links`
--

LOCK TABLES `staff_payout_obligation_links` WRITE;
/*!40000 ALTER TABLE `staff_payout_obligation_links` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_payout_obligation_links` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payout_links_before_update` BEFORE UPDATE ON `staff_payout_obligation_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be updated' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`%`*/ /*!50003 TRIGGER `trg_staff_payout_links_before_delete` BEFORE DELETE ON `staff_payout_obligation_links` FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'staff_payout_obligation_links records cannot be deleted' */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `staff_regions`
--

DROP TABLE IF EXISTS `staff_regions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_regions` (
  `staff_id` int NOT NULL,
  `region_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '區域名稱 (北區/東區/香山區/新竹縣/苗栗縣/其他)',
  `custom_region_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '對應其他地區的補充說明',
  PRIMARY KEY (`staff_id`,`region_name`),
  CONSTRAINT `staff_regions_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_regions`
--

LOCK TABLES `staff_regions` WRITE;
/*!40000 ALTER TABLE `staff_regions` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_regions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_schedule`
--

DROP TABLE IF EXISTS `staff_schedule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_schedule` (
  `id` int NOT NULL AUTO_INCREMENT,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '對應 orders.case_no',
  `staff_id` int NOT NULL COMMENT '對應 staff.id',
  `assignment_id` bigint DEFAULT NULL COMMENT '正式服務指派；既有未覆核排班保留 NULL',
  `generation_id` bigint DEFAULT NULL,
  `work_date` date NOT NULL COMMENT '工作日期',
  `is_work_day` tinyint(1) DEFAULT '1' COMMENT '是否為工作日 (FALSE代表放假/休假)',
  `is_double_pay` tinyint(1) DEFAULT '0' COMMENT '是否為雙倍薪資日 (如特殊國定假日上班)',
  `effective_marker` tinyint(1) DEFAULT '1',
  `notes` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '行政人員調整備註',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_schedule`
--

LOCK TABLES `staff_schedule` WRITE;
/*!40000 ALTER TABLE `staff_schedule` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_schedule` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_schedule_assignment_reviews`
--

DROP TABLE IF EXISTS `staff_schedule_assignment_reviews`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_schedule_assignment_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `schedule_id` int NOT NULL,
  `review_reason` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `review_status` enum('review_required','resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'review_required',
  `resolved_assignment_id` bigint DEFAULT NULL,
  `resolved_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_schedule_assignment_reviews`
--

LOCK TABLES `staff_schedule_assignment_reviews` WRITE;
/*!40000 ALTER TABLE `staff_schedule_assignment_reviews` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_schedule_assignment_reviews` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_time_slots`
--

DROP TABLE IF EXISTS `staff_time_slots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_time_slots` (
  `staff_id` int NOT NULL,
  `slot_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '時段名稱 (4小時_上午/4小時_下午/8小時/24小時/其他)',
  `custom_slot_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他時段的補充說明',
  PRIMARY KEY (`staff_id`,`slot_name`),
  CONSTRAINT `staff_time_slots_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_time_slots`
--

LOCK TABLES `staff_time_slots` WRITE;
/*!40000 ALTER TABLE `staff_time_slots` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_time_slots` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_transfer_allocations`
--

DROP TABLE IF EXISTS `staff_transfer_allocations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_transfer_allocations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `transfer_id` bigint NOT NULL,
  `settlement_detail_id` bigint NOT NULL,
  `allocated_amount` decimal(12,2) NOT NULL,
  `component_type` enum('regular_salary','legacy_subsidy','floor_fee','adjustment','unknown') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'unknown',
  `allocation_method` enum('explicit','inferred') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'explicit',
  `review_status` enum('approved','review_required','rejected') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'review_required',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_transfer_allocations`
--

LOCK TABLES `staff_transfer_allocations` WRITE;
/*!40000 ALTER TABLE `staff_transfer_allocations` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_transfer_allocations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_transportation`
--

DROP TABLE IF EXISTS `staff_transportation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_transportation` (
  `staff_id` int NOT NULL,
  `vehicle_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '交通工具 (機車/轎車)',
  PRIMARY KEY (`staff_id`,`vehicle_type`),
  CONSTRAINT `staff_transportation_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_transportation`
--

LOCK TABLES `staff_transportation` WRITE;
/*!40000 ALTER TABLE `staff_transportation` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_transportation` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `staff_weekly_rest`
--

DROP TABLE IF EXISTS `staff_weekly_rest`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff_weekly_rest` (
  `staff_id` int NOT NULL,
  `rest_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '放假類型 (連續服務/週休1日/週休2日/其他)',
  `custom_rest_detail` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '其他週間服務的補充說明',
  PRIMARY KEY (`staff_id`,`rest_type`),
  CONSTRAINT `staff_weekly_rest_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_weekly_rest`
--

LOCK TABLES `staff_weekly_rest` WRITE;
/*!40000 ALTER TABLE `staff_weekly_rest` DISABLE KEYS */;
/*!40000 ALTER TABLE `staff_weekly_rest` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subsidy_claim_batch_items`
--

DROP TABLE IF EXISTS `subsidy_claim_batch_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `subsidy_claim_batch_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `batch_id` bigint NOT NULL,
  `case_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subsidy_claim_batch_items`
--

LOCK TABLES `subsidy_claim_batch_items` WRITE;
/*!40000 ALTER TABLE `subsidy_claim_batch_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `subsidy_claim_batch_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subsidy_claim_batches`
--

DROP TABLE IF EXISTS `subsidy_claim_batches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `subsidy_claim_batches` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `application_year` smallint unsigned NOT NULL,
  `quarter` tinyint unsigned NOT NULL,
  `revision` int unsigned NOT NULL,
  `status` enum('draft','submitted','approved','partially_paid','paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subsidy_claim_batches`
--

LOCK TABLES `subsidy_claim_batches` WRITE;
/*!40000 ALTER TABLE `subsidy_claim_batches` DISABLE KEYS */;
/*!40000 ALTER TABLE `subsidy_claim_batches` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_alerts`
--

DROP TABLE IF EXISTS `system_alerts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_alerts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `alert_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '異常代碼，例如 IMPORT-001, ORDER-001',
  `source_domain` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '來源領域',
  `case_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '案件識別鍵：正常為 case_no，查無案號時用 error_姓名_行動電話',
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '人類可讀的簡述',
  `details` json NOT NULL COMMENT '目前偵測到的異常內容，每次掃描直接覆蓋更新',
  `status` enum('open','claimed','resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open' COMMENT '處理狀態',
  `claimed_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '認領人員',
  `claimed_at` datetime DEFAULT NULL COMMENT '認領時間',
  `resolved_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '處理人員',
  `resolved_at` datetime DEFAULT NULL COMMENT '排除時間',
  `resolution_reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '處理原因',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_alert_case` (`alert_code`,`case_key`),
  KEY `idx_system_alert_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_alerts`
--

LOCK TABLES `system_alerts` WRITE;
/*!40000 ALTER TABLE `system_alerts` DISABLE KEYS */;
/*!40000 ALTER TABLE `system_alerts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Temporary view structure for view `v_order_details`
--

DROP TABLE IF EXISTS `v_order_details`;
/*!50001 DROP VIEW IF EXISTS `v_order_details`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_order_details` AS SELECT 
 1 AS `case_no`,
 1 AS `order_status`,
 1 AS `lifecycle_version`,
 1 AS `cancel_reason`,
 1 AS `line_group_id`,
 1 AS `actual_start_date`,
 1 AS `actual_end_date`,
 1 AS `contract_id`,
 1 AS `client_id`,
 1 AS `client_name`,
 1 AS `client_phone`,
 1 AS `service_mode`,
 1 AS `staff_id`,
 1 AS `staff_name`,
 1 AS `staff_phone`,
 1 AS `service_days`,
 1 AS `service_hours_per_day`,
 1 AS `identity_status`,
 1 AS `floor_fee`,
 1 AS `deposit_date`,
 1 AS `start_date`,
 1 AS `end_date`,
 1 AS `total_hours`,
 1 AS `subsidy_hours`,
 1 AS `self_pay_hours`,
 1 AS `employer_unit_price`,
 1 AS `deposit_days`,
 1 AS `deposit_amount`,
 1 AS `initial_payment_payable`,
 1 AS `first_payment_date`,
 1 AS `remaining_days`,
 1 AS `first_payment_days`,
 1 AS `first_payment_amount`,
 1 AS `second_payment_date`,
 1 AS `second_payment_days`,
 1 AS `second_payment_amount`,
 1 AS `total_employer_self_pay_payable`,
 1 AS `service_unit_price`,
 1 AS `service_salary`,
 1 AS `salary_payment_date_1`,
 1 AS `subsidy_salary`,
 1 AS `govt_claim_date`*/;
SET character_set_client = @saved_cs_client;

--
-- Dumping events for database 'lu_test_preserve_candidate_r2_20260804'
--

--
-- Dumping routines for database 'lu_test_preserve_candidate_r2_20260804'
--

--
-- Current Database: `lu_test_preserve_candidate_r2_20260804`
--

USE `lu_test_preserve_candidate_r2_20260804`;

--
-- Final view structure for view `v_order_details`
--

/*!50001 DROP VIEW IF EXISTS `v_order_details`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_order_details` AS select `o`.`case_no` AS `case_no`,`o`.`status` AS `order_status`,`o`.`lifecycle_version` AS `lifecycle_version`,`o`.`cancel_reason` AS `cancel_reason`,`o`.`line_group_id` AS `line_group_id`,`o`.`actual_start_date` AS `actual_start_date`,`o`.`actual_end_date` AS `actual_end_date`,`o`.`contract_id` AS `contract_id`,`c`.`id` AS `client_id`,`c`.`name` AS `client_name`,`c`.`phone` AS `client_phone`,`c`.`service_type` AS `service_mode`,`s`.`id` AS `staff_id`,`s`.`name` AS `staff_name`,`s`.`phone` AS `staff_phone`,`o`.`service_days` AS `service_days`,`o`.`service_hours_per_day` AS `service_hours_per_day`,`c`.`identity_status` AS `identity_status`,`o`.`floor_fee` AS `floor_fee`,`o`.`deposit_date` AS `deposit_date`,`o`.`start_date` AS `start_date`,`o`.`end_date` AS `end_date`,(`o`.`service_days` * `o`.`service_hours_per_day`) AS `total_hours`,(case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end) AS `subsidy_hours`,greatest(0,((`o`.`service_days` * `o`.`service_hours_per_day`) - (case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end))) AS `self_pay_hours`,(case when (`c`.`identity_status` = '非市民') then 350 else 300 end) AS `employer_unit_price`,(case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) AS `deposit_days`,(((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) AS `deposit_amount`,((((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) + coalesce(`o`.`floor_fee`,0)) AS `initial_payment_payable`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then `o`.`start_date` else NULL end) AS `first_payment_date`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end))) else NULL end) AS `remaining_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) else NULL end) AS `first_payment_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else NULL end) AS `first_payment_amount`,(case when ((`o`.`status` not in ('洽談中','訂單取消')) and (((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15) > 0)) then (`o`.`start_date` + interval 15 day) else NULL end) AS `second_payment_date`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) else NULL end) AS `second_payment_days`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else NULL end) AS `second_payment_amount`,((((((case when (`c`.`identity_status` = '補助市民') then 0 else 5 end) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) * `o`.`service_hours_per_day`) + coalesce(`o`.`floor_fee`,0)) + coalesce((case when (`o`.`status` not in ('洽談中','訂單取消')) then ((least(15,greatest(0,(`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)))) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else 0 end),0)) + coalesce((case when (`o`.`status` not in ('洽談中','訂單取消')) then ((greatest(0,((`o`.`service_days` - (case when (`c`.`identity_status` = '補助市民') then 0 else 5 end)) - 15)) * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '非市民') then 350 else 300 end)) else 0 end),0)) AS `total_employer_self_pay_payable`,(case when (`c`.`identity_status` = '一般市民') then 300 when (`c`.`identity_status` = '補助市民') then 350 else 320 end) AS `service_unit_price`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((`o`.`service_days` * `o`.`service_hours_per_day`) * (case when (`c`.`identity_status` = '一般市民') then 300 when (`c`.`identity_status` = '補助市民') then 350 else 320 end)) else NULL end) AS `service_salary`,(case when ((`o`.`status` not in ('洽談中','訂單取消')) and (`o`.`end_date` is not null) and (`c`.`identity_status` = '補助市民')) then (last_day((`o`.`end_date` + interval 1 month)) + interval 15 day) when ((`o`.`status` not in ('洽談中','訂單取消')) and (`o`.`end_date` is not null)) then (last_day(`o`.`end_date`) + interval 15 day) else NULL end) AS `salary_payment_date_1`,(case when (`o`.`status` not in ('洽談中','訂單取消')) then ((case when (`c`.`identity_status` = '一般市民') then 40 when (`c`.`identity_status` = '補助市民') then 120 else 0 end) * (case when (`c`.`identity_status` = '一般市民') then 300 when (`c`.`identity_status` = '補助市民') then 350 else 320 end)) else NULL end) AS `subsidy_salary`,(case when ((`o`.`status` not in ('洽談中','訂單取消')) and (`c`.`identity_status` <> '非市民') and (`o`.`end_date` is not null)) then (last_day(`o`.`end_date`) + interval 5 day) else NULL end) AS `govt_claim_date` from ((`orders` `o` join `clients` `c` on((`o`.`client_id` = `c`.`id`))) left join `staff` `s` on((`o`.`staff_id` = `s`.`id`))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-08-04  1:30:39
