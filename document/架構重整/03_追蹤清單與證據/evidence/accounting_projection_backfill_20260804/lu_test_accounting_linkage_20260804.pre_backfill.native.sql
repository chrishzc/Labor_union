-- MySQL dump 10.13  Distrib 8.4.11, for Linux (x86_64)
--
-- Host: localhost    Database: lu_test_accounting_linkage_20260804
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
-- Current Database: `lu_test_accounting_linkage_20260804`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `lu_test_accounting_linkage_20260804` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `lu_test_accounting_linkage_20260804`;

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
) ENGINE=InnoDB AUTO_INCREMENT=701 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `admin_audit_logs`
--

LOCK TABLES `admin_audit_logs` WRITE;
/*!40000 ALTER TABLE `admin_audit_logs` DISABLE KEYS */;
INSERT INTO `admin_audit_logs` VALUES (1,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',500,'127.0.0.1',NULL,'2026-07-30 10:42:44'),(2,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',500,'127.0.0.1',NULL,'2026-07-30 10:42:44'),(3,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 10:53:26'),(4,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 10:55:12'),(5,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 10:56:46'),(6,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:26:20'),(7,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:26:50'),(8,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:27:21'),(9,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:28:05'),(10,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:29:58'),(11,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:30:29'),(12,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:30:34'),(13,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:30:37'),(14,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:30:40'),(15,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:30:42'),(16,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(17,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000016/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(18,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000021/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(19,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000023/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(20,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000025/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(21,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000030/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(22,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000035/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:36'),(23,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000036/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(24,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000037/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(25,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000039/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(26,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(27,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000046/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(28,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000049/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(29,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000050/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:32:37'),(30,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:38:31'),(31,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:40:04'),(32,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:40:05'),(33,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 11:40:06'),(34,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 12:04:10'),(35,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 12:05:14'),(36,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-30 14:44:21'),(37,NULL,'api.mutation',NULL,NULL,'/api/v1/line/review-requests/4/reject','POST',422,'testclient',NULL,'2026-07-30 14:44:23'),(38,NULL,'line.review.reject','line_confirmation_request','4','/api/v1/line/review-requests/4/reject','POST',200,'testclient','{\"reason\": \"API 測試拒絕\", \"request_type\": \"staff_verification\"}','2026-07-30 14:44:23'),(43,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-30 14:44:27'),(44,NULL,'line.rich_menu.image.upload','media_asset','1','/api/v1/line/rich-menus/default_menu/images','POST',200,'testclient',NULL,'2026-07-30 14:44:27'),(45,NULL,'line.rich_menu.publish','line_rich_menu_publication','3','/api/v1/line/rich-menus/default_menu/publish','POST',202,'testclient','{\"reason\": \"integration test\"}','2026-07-30 14:44:27'),(46,NULL,'line.task.run_now','line_task','10','/api/v1/line/tasks/10/run-now','POST',200,'testclient','{\"reason\": \"integration test\"}','2026-07-30 14:44:30'),(47,NULL,'line.task.cancel','line_task','10','/api/v1/line/tasks/10/cancel','POST',200,'testclient','{\"reason\": \"integration test cleanup\"}','2026-07-30 14:44:31'),(48,NULL,'line.task.retry','line_task','11','/api/v1/line/tasks/11/retry','POST',200,'testclient','{\"reason\": \"integration test\"}','2026-07-30 14:44:31'),(49,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-30 14:44:31'),(50,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 14:51:49'),(51,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',422,'127.0.0.1',NULL,'2026-07-30 14:52:20'),(52,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 14:52:36'),(53,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 14:53:52'),(54,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 14:54:19'),(55,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 14:59:26'),(56,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:00:18'),(57,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:03:33'),(58,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:08:28'),(59,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:17:13'),(60,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:18:04'),(61,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:21:02'),(62,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:22:26'),(63,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:27:16'),(64,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:28:05'),(65,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:28:32'),(66,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:29:28'),(67,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:32:10'),(68,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:33:55'),(69,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:34:42'),(70,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:34:59'),(71,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 15:35:02'),(72,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:35:56'),(73,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:36:23'),(74,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:43:51'),(75,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:44:28'),(76,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:44:46'),(77,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 15:44:48'),(78,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:47:36'),(79,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:48:18'),(80,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:48:41'),(81,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:49:35'),(82,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 15:50:00'),(83,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 16:04:13'),(84,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 16:05:12'),(85,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 16:05:29'),(86,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 16:05:31'),(87,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:44:24'),(88,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:44:38'),(89,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:45:13'),(90,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:48:02'),(91,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:48:19'),(92,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-07-30 23:48:21'),(93,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:49:14'),(94,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:49:31'),(95,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:52:28'),(96,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-30 23:52:31'),(97,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-30 23:52:31'),(98,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-30 23:52:56'),(99,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-30 23:56:27'),(100,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-30 23:56:27'),(101,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-30 23:56:27'),(102,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-30 23:56:56'),(103,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-30 23:56:56'),(104,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-30 23:56:56'),(105,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 00:31:57'),(106,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 00:31:57'),(107,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 00:31:57'),(108,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 00:32:20'),(109,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 00:32:20'),(110,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 00:32:20'),(111,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 00:32:48'),(112,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 00:32:48'),(113,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 00:32:48'),(114,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:04:14'),(115,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:04:45'),(116,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:09:11'),(117,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:10:16'),(118,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:10:49'),(119,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:27:47'),(120,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:20'),(121,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/240/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:27'),(122,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/241/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:32'),(123,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/242/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:37'),(124,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/243/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:41'),(125,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/244/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:46'),(126,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/245/send-info-1','POST',200,'127.0.0.1',NULL,'2026-07-31 06:28:51'),(127,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000042/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:29:09'),(128,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 06:52:12'),(129,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 08:33:30'),(130,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 08:33:46'),(131,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-07-31 08:34:24'),(132,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 15:49:20'),(133,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 15:49:21'),(134,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 15:49:21'),(135,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 15:49:21'),(136,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 15:49:21'),(137,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 15:50:29'),(138,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 15:50:29'),(139,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 15:50:29'),(140,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 15:50:29'),(141,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 15:50:29'),(142,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 16:41:03'),(143,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 16:41:03'),(144,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 16:41:03'),(145,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 16:41:03'),(146,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 16:41:03'),(147,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 16:43:14'),(148,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 16:43:14'),(149,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 16:43:14'),(150,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 16:43:14'),(151,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 16:43:14'),(152,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 17:08:14'),(153,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 17:08:14'),(154,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 17:08:14'),(155,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 17:08:15'),(156,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 17:08:16'),(157,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 17:08:16'),(158,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 17:08:16'),(159,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 17:08:16'),(160,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 17:18:46'),(161,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 17:18:47'),(162,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 17:18:47'),(163,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 17:18:48'),(164,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 17:18:48'),(165,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 17:18:48'),(166,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 17:18:48'),(167,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 17:18:48'),(168,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-07-31 17:23:20'),(169,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-07-31 17:23:20'),(170,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-07-31 17:23:20'),(171,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-07-31 17:23:21'),(172,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-07-31 17:23:21'),(173,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-07-31 17:23:21'),(174,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-07-31 17:23:21'),(175,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-07-31 17:23:21'),(176,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 05:29:51'),(177,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 05:29:51'),(178,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 05:29:51'),(179,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 05:29:52'),(180,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 05:29:52'),(181,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 05:29:52'),(182,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 05:29:52'),(183,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 05:29:52'),(184,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:34:28'),(185,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:34:28'),(186,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:34:28'),(187,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:34:28'),(188,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:34:28'),(189,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:35:12'),(190,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:35:13'),(191,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:35:13'),(192,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:35:13'),(193,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:35:13'),(194,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:35:36'),(195,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:35:36'),(196,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:35:36'),(197,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:35:37'),(198,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:35:37'),(199,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:36:31'),(200,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:36:31'),(201,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:36:32'),(202,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:36:32'),(203,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:36:32'),(204,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 07:38:50'),(205,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 07:38:50'),(206,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 07:38:50'),(207,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:38:51'),(208,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:38:51'),(209,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:38:51'),(210,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:38:51'),(211,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:38:51'),(212,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 07:49:34'),(213,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 07:49:34'),(214,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 07:49:34'),(215,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 07:49:35'),(216,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 07:49:35'),(217,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 07:49:35'),(218,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 07:49:35'),(219,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 07:49:35'),(220,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 08:02:31'),(221,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',422,'testclient',NULL,'2026-08-02 08:02:31'),(222,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 08:02:31'),(223,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 08:02:31'),(224,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 08:02:31'),(225,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 08:13:27'),(226,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 08:13:27'),(227,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 08:13:28'),(228,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 08:13:28'),(229,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 08:13:28'),(230,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 08:16:06'),(231,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 08:16:06'),(232,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 08:16:06'),(233,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 08:16:07'),(234,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 08:16:07'),(235,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',422,'testclient',NULL,'2026-08-02 08:17:50'),(236,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',422,'testclient',NULL,'2026-08-02 08:17:50'),(237,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',422,'testclient',NULL,'2026-08-02 08:17:50'),(238,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',422,'testclient',NULL,'2026-08-02 08:17:50'),(239,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 08:17:50'),(240,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 12:35:16'),(241,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 12:35:16'),(242,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 12:35:16'),(243,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(244,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(245,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(246,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(247,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(248,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 12:35:17'),(249,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 12:40:50'),(250,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 12:40:50'),(251,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 12:40:50'),(252,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(253,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(254,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(255,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(256,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(257,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 12:40:51'),(258,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 14:35:17'),(259,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:13:45'),(260,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:13:46'),(261,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:13:46'),(262,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:14:29'),(263,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:14:29'),(264,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:14:29'),(265,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:15:38'),(266,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:15:39'),(267,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:15:39'),(268,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:15:39'),(269,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:15:39'),(270,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:15:39'),(271,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:15:39'),(272,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:15:39'),(273,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:15:40'),(274,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:16:22'),(275,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:16:22'),(276,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:16:22'),(277,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:16:23'),(278,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:16:24'),(279,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:16:24'),(280,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:16:24'),(281,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:16:24'),(282,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:16:24'),(283,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:17:02'),(284,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:17:02'),(285,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:17:02'),(286,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(287,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(288,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(289,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(290,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(291,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:17:03'),(292,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:18:15'),(293,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:18:15'),(294,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:18:15'),(295,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:18:16'),(296,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:18:16'),(297,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:18:16'),(298,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:18:16'),(299,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:18:16'),(300,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:18:17'),(301,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:19:11'),(302,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:19:11'),(303,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:19:11'),(304,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:19:12'),(305,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:19:12'),(306,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:19:12'),(307,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:19:12'),(308,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:19:12'),(309,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:19:13'),(310,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:20:07'),(311,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:20:07'),(312,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:20:07'),(313,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(314,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(315,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(316,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(317,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(318,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:20:08'),(319,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 15:47:43'),(320,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 15:47:43'),(321,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 15:47:43'),(322,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 15:47:44'),(323,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 15:47:45'),(324,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 15:47:45'),(325,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 15:47:45'),(326,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 15:47:45'),(327,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 15:47:45'),(328,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:09:07'),(329,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:10:08'),(330,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:13:13'),(331,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:16:38'),(332,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:20:49'),(333,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:21:14'),(334,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:21:38'),(335,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:22:28'),(336,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:23:16'),(337,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:23:57'),(338,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/246/send-info-1','POST',200,'127.0.0.1',NULL,'2026-08-02 16:24:03'),(339,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/247/send-info-1','POST',200,'127.0.0.1',NULL,'2026-08-02 16:24:08'),(340,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:24:33'),(341,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:25:25'),(342,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/246/send-info-1','POST',200,'127.0.0.1',NULL,'2026-08-02 16:25:32'),(343,NULL,'api.mutation',NULL,NULL,'/api/v1/matches/247/send-info-1','POST',200,'127.0.0.1',NULL,'2026-08-02 16:25:36'),(344,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:26:01'),(345,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:28:29'),(346,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 16:28:54'),(347,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 16:28:56'),(348,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 17:33:23'),(349,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 17:34:22'),(350,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-single-eligibility/check','POST',200,'127.0.0.1',NULL,'2026-08-02 17:35:50'),(351,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 17:35:52'),(352,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 17:35:52'),(353,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 17:35:52'),(354,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(355,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(356,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(357,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(358,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(359,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 17:35:59'),(360,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 18:05:53'),(361,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 18:05:53'),(362,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 18:05:54'),(363,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(364,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(365,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(366,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(367,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(368,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 18:05:55'),(369,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 18:14:14'),(370,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 18:14:14'),(371,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 18:14:14'),(372,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 18:14:14'),(373,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 18:14:15'),(374,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 18:14:15'),(375,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 18:14:15'),(376,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 18:14:15'),(377,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 18:14:15'),(378,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 18:29:05'),(379,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 18:29:46'),(380,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/matches','POST',410,'127.0.0.1',NULL,'2026-08-02 18:29:46'),(381,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 18:29:59'),(382,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 18:30:00'),(383,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 18:30:00'),(384,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 18:30:00'),(385,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 18:30:01'),(386,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 18:30:01'),(387,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 18:30:01'),(388,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 18:30:01'),(389,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 18:30:01'),(390,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 18:52:52'),(391,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 18:53:24'),(392,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 18:59:35'),(393,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 18:59:35'),(394,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 18:59:35'),(395,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 18:59:36'),(396,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 18:59:36'),(397,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 18:59:36'),(398,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 18:59:37'),(399,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 18:59:37'),(400,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 18:59:37'),(401,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 19:10:11'),(402,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 19:10:11'),(403,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 19:10:11'),(404,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(405,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(406,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(407,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(408,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(409,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 19:10:12'),(410,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 19:39:55'),(411,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 19:39:55'),(412,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 19:39:55'),(413,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 19:39:56'),(414,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 19:39:56'),(415,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 19:39:56'),(416,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 19:39:56'),(417,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 19:39:56'),(418,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 19:39:57'),(419,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 19:44:04'),(420,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 19:44:04'),(421,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 19:44:04'),(422,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(423,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(424,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(425,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(426,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(427,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 19:44:05'),(428,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 19:52:01'),(429,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 19:59:05'),(430,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 19:59:05'),(431,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 19:59:06'),(432,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 19:59:28'),(433,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 19:59:28'),(434,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 19:59:28'),(435,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:01:21'),(436,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:01:22'),(437,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:01:22'),(438,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:01:57'),(439,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:01:57'),(440,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:01:57'),(441,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(442,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(443,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(444,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(445,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(446,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 20:01:58'),(447,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:05:06'),(448,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:05:06'),(449,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:05:06'),(450,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(451,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(452,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(453,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(454,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(455,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 20:05:08'),(456,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:21:42'),(457,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:21:42'),(458,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:21:42'),(459,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(460,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(461,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(462,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(463,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(464,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 20:21:43'),(465,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:29:16'),(466,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:29:16'),(467,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:29:16'),(468,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(469,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(470,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(471,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(472,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(473,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 20:29:17'),(474,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 20:51:34'),(475,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 20:51:34'),(476,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 20:51:34'),(477,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(478,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(479,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(480,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(481,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(482,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 20:51:35'),(483,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 20:55:13'),(484,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 20:56:08'),(485,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 20:58:36'),(486,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:00:09'),(487,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:00:09'),(488,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:01:36'),(489,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:17:13'),(490,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:17:13'),(491,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:17:13'),(492,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(493,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(494,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(495,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(496,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(497,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:17:14'),(498,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:23:52'),(499,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:23:52'),(500,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:23:52'),(501,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(502,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(503,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(504,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(505,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(506,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:23:53'),(507,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:36:32'),(508,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:36:32'),(509,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:36:32'),(510,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(511,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(512,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(513,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(514,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(515,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:36:33'),(516,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:37:17'),(517,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:37:17'),(518,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:37:17'),(519,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(520,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(521,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(522,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(523,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(524,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:37:18'),(525,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:37:53'),(526,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:37:53'),(527,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:37:53'),(528,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(529,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(530,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(531,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(532,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(533,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:37:54'),(534,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 21:52:33'),(535,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 21:52:33'),(536,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 21:52:33'),(537,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(538,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(539,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(540,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(541,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(542,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 21:52:34'),(543,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 22:10:28'),(544,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 22:10:28'),(545,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 22:10:29'),(546,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(547,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(548,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(549,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(550,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(551,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 22:10:30'),(552,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 22:11:26'),(553,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 22:11:26'),(554,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 22:11:26'),(555,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(556,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(557,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(558,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(559,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(560,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 22:11:27'),(561,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 22:54:26'),(562,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 22:54:26'),(563,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 22:54:26'),(564,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(565,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(566,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(567,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(568,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(569,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 22:54:27'),(570,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 23:06:57'),(571,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 23:24:33'),(572,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 23:24:33'),(573,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 23:24:33'),(574,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(575,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(576,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(577,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(578,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(579,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 23:24:34'),(580,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 23:25:42'),(581,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 23:25:42'),(582,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 23:25:42'),(583,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(584,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(585,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(586,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(587,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(588,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 23:25:43'),(589,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-02 23:35:33'),(590,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 23:43:38'),(591,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 23:43:39'),(592,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 23:43:39'),(593,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 23:43:39'),(594,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 23:43:39'),(595,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 23:43:39'),(596,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 23:43:40'),(597,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 23:43:40'),(598,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 23:43:40'),(599,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-02 23:50:08'),(600,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-02 23:50:08'),(601,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-02 23:50:08'),(602,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(603,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(604,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(605,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(606,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(607,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-02 23:50:09'),(608,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 00:08:59'),(609,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 00:08:59'),(610,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 00:08:59'),(611,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 00:09:00'),(612,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 00:09:00'),(613,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 00:09:00'),(614,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 00:09:01'),(615,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 00:09:01'),(616,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 00:09:01'),(617,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-03 00:13:30'),(618,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 00:26:47'),(619,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 00:26:47'),(620,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 00:26:47'),(621,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(622,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(623,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(624,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(625,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(626,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 00:26:48'),(627,NULL,'api.mutation',NULL,NULL,'/api/v1/anomaly-recovery/definitions/finance_import_manual_review/scan','POST',200,'127.0.0.1',NULL,'2026-08-03 00:56:14'),(628,NULL,'api.mutation',NULL,NULL,'/api/v1/cases/115000001/architecture-bootstrap/apply','POST',200,'127.0.0.1',NULL,'2026-08-03 01:45:21'),(629,NULL,'api.mutation',NULL,NULL,'/api/v1/cases/115000002/architecture-bootstrap/apply','POST',200,'127.0.0.1',NULL,'2026-08-03 02:03:20'),(630,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-03 03:31:26'),(631,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-03 05:01:48'),(632,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 05:15:49'),(633,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 05:15:49'),(634,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 05:15:50'),(635,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 05:15:52'),(636,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 05:15:52'),(637,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 05:15:52'),(638,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 05:15:52'),(639,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 05:15:53'),(640,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 05:15:53'),(641,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 07:44:10'),(642,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 07:44:11'),(643,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 07:44:11'),(644,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(645,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(646,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(647,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(648,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(649,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 07:44:12'),(650,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:04:07'),(651,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:04:07'),(652,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:04:07'),(653,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(654,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(655,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(656,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(657,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(658,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 08:04:08'),(659,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:04:53'),(660,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:04:53'),(661,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:04:53'),(662,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(663,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(664,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(665,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(666,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(667,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 08:04:54'),(668,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:10:44'),(669,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:10:44'),(670,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:10:44'),(671,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 08:10:45'),(672,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 08:10:45'),(673,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 08:10:45'),(674,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 08:10:46'),(675,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 08:10:46'),(676,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 08:10:46'),(677,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:12:23'),(678,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:12:23'),(679,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:12:23'),(680,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(681,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(682,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(683,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(684,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(685,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 08:12:24'),(686,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:19:51'),(687,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:19:52'),(688,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:19:52'),(689,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/assignment-synchronization/apply','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(690,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/cancel','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(691,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(692,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/holds/review-hold/release','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(693,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/lifecycle-corrections','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(694,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/C-1/actual-start/reconfirm','POST',410,'testclient',NULL,'2026-08-03 08:19:53'),(695,NULL,'api.mutation',NULL,NULL,'/api/config/message-templates/staff_switch_success','PUT',409,'testclient',NULL,'2026-08-03 08:24:41'),(696,NULL,'api.mutation',NULL,NULL,'/api/config/line-menus','PUT',409,'testclient',NULL,'2026-08-03 08:24:41'),(697,NULL,'api.mutation',NULL,NULL,'/api/config/message-schedules','PUT',409,'testclient',NULL,'2026-08-03 08:24:41'),(698,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-03 14:34:53'),(699,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-03 16:01:05'),(700,NULL,'api.mutation',NULL,NULL,'/api/v1/orders/115000015/caregiver-segment-availability/search','POST',200,'127.0.0.1',NULL,'2026-08-04 01:04:15');
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
INSERT INTO `anomaly_consumer_checkpoints` VALUES ('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000003:generation:1','scheduling-coverage:561d6fb51520b765f53b414a364b6d3ff309729d648df2074de403aff2759e9a',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000004:generation:1','scheduling-coverage:3d7587e3f398aa3397a494f135a9b25c5168894bfee34835993879323266ad24',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000007:generation:1','scheduling-coverage:8a49fbd8f93810d94d131558faa7d8cc8bb83e9b9d87be0ded8c16c8b684d953',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000008:generation:1','scheduling-coverage:92cdcbb12a2de51c7538ffafe50a92bbe0fc035a42e966d47b262244afa28a3e',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000009:generation:1','scheduling-coverage:e5fca4180bc554f3b4dc1df05949cefd2b354b4cf89afa7c963c2248c17b9756',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000010:generation:1','scheduling-coverage:edcac10469bdeffa8cc49915f77765547b427424cbf97acd6432f616379605fd',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000011:generation:1','scheduling-coverage:7299caaaa1cc81da2303fef26197fbfff694d0655761ff81712be3b8c70d897f',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000013:generation:1','scheduling-coverage:801cecedc0a39fa8d94b53cffdd13452cef3fc349a69ab79e8e5065ad1f26c9b',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000014:generation:1','scheduling-coverage:6de7bfbc35cda77980b20932c004871bdd852826315657e008e8d23ae3b2afb8',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000017:generation:1','scheduling-coverage:04dbb5e8f4ae0ad4e9d5aecbda1bc97a2897f86049637b887cfd19b7babd0a58',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000018:generation:1','scheduling-coverage:c7d1ece853e8bc2a03cd2f4e01370274704fb6a193f4881ffd9c5d61fb50adc6',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000019:generation:1','scheduling-coverage:db878e9edd856a07c2cff3455192b184bdd92eed6df34bacb5e0fa00e85ab53f',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000020:generation:1','scheduling-coverage:4a302873e2503793d895b2b8e1773503801990b8e955c3edad000cd7a82d8038',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000022:generation:1','scheduling-coverage:d5be19af429c1f4f383aa7ac479a3de97452ff01895913aa202f4e20c3720693',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000024:generation:1','scheduling-coverage:5498f7d4538cc838469a588ea4808b740f65325f6913a1028bec9cab79bf1d7c',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000026:generation:1','scheduling-coverage:af965ebca8b08b4f9d9c6915278e7dc8c7899f9bbfd0cb2723d30f1e7af5957f',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000027:generation:1','scheduling-coverage:7cd84f9d2f18bda3a8d41e062e757a6c7454f209b6eed60e8a3bbca173dc7b21',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000028:generation:1','scheduling-coverage:a5dc15b0a5dec31ee06a786b2e3429702ed3a3cea0a461d248694785898d742c',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000031:generation:1','scheduling-coverage:06af7c955e4c7bf9e14c429bc72d25ea1ac5a79fe4d5aa00e69f6cf6b24d22e0',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000034:generation:1','scheduling-coverage:b7d9634e10da3bd55f3ec0a31a1fa6b4434922ef474640b8c0913d0537368673',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000038:generation:1','scheduling-coverage:ba0578f5705fad89b35acafdaad4f1d5c865aef97ef1b245edcec3890d592279',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000040:generation:1','scheduling-coverage:f3ec21e02af1f367babdd404bdaf5e790b25af7037861be9127faeea09e175a4',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000043:generation:1','scheduling-coverage:89a9ae4f8c91a66dea0465b46bd6208b96355edae7df0c7f55f8369cc40d5cf4',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000044:generation:1','scheduling-coverage:653ff3c72fded2d4c979cf7836da7787241e99d44468e4db4ec795f23835b4be',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000045:generation:1','scheduling-coverage:09e15e8011c12d793370792462eafeb195d8e21863dac254398d28ce40dbca90',1,'2026-08-02 22:59:31'),('scheduling-coverage-anomaly-projector-v1','SCHEDULE-006:case:115000047:generation:1','scheduling-coverage:c3c97c280d3c5fad9f1dcad4f3929a2d1c798746ac4bb66f9a6bd2a39036b858',1,'2026-08-02 22:59:31');
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
INSERT INTO `application_command_claims` VALUES ('case-bootstrap-apply-411e9ffae9ee4cbe90cd987ec29acafb','case_architecture_bootstrap','115000002','ae6c6de74c6643fd84f20662a9be99d4426a12bf5d90b956dbd1d67bbec72871','case-bootstrap-apply-7ee7fac3337144ed9f028bc7c0a673ae','2026-08-03 02:03:20'),('case-bootstrap-apply-d8fd8b1d275e4be583d616e7a1da92b8','case_architecture_bootstrap','115000001','41eb5bfd0b26bed464f984e83cddc89a984af09412d92ce1f0a5f3746ca171da','case-bootstrap-apply-da846ad4bcb04f5dbdff35eed8a46803','2026-08-03 01:45:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `audit_logs`
--

LOCK TABLES `audit_logs` WRITE;
/*!40000 ALTER TABLE `audit_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `audit_logs` ENABLE KEYS */;
UNLOCK TABLES;

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
) ENGINE=InnoDB AUTO_INCREMENT=842 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `beclass_records`
--

LOCK TABLES `beclass_records` WRITE;
/*!40000 ALTER TABLE `beclass_records` DISABLE KEYS */;
INSERT INTO `beclass_records` VALUES (792,1,'115000001','06-04 23:58','楊洋玲','test_1802@example.com','1988-06-11','0993571802',NULL,NULL,'新竹市','300','新竹市竹東鎮和平街544號','8070014','700000000000','{\"有\": \"Y\", \"全酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□炒菜鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(793,2,'115000002','06-05 05:45','黃欣','test_5396@example.com','1994-10-24','0927885396',NULL,NULL,'新竹市','300','新竹市竹東鎮經國路764號','8070014','700000000001','{\"有\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(794,3,'115000003','07-20 22:00','李強','test_0598@example.com','1990-12-21','0975930598',NULL,NULL,'新竹市','300','新竹市東區光復路971號','8070014','700000000002','{\"有\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(795,4,'115000004','07-22 17:22','陳建建','test_9297@example.com','1995-06-26','0904429297',NULL,NULL,'新竹市','300','新竹市北區中華路45號','8070014','700000000003','{\"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(796,5,'115000005','06-06 05:11','張建涵','test_6012@example.com','1984-06-10','0977396012',NULL,NULL,'新竹市','300','新竹市東區和平街551號','8070014','700000000004','{\"有\": \"Y\", \"全酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(797,6,'115000006','06-08 18:40','林奕','test_4788@example.com','1998-09-23','0996104788',NULL,NULL,'新竹市','300','新竹市北區中山路382號','8070014','700000000005','{\"性別\": \"女\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(798,7,'115000007','06-18 02:07','高芳','test_1449@example.com','1991-08-13','0913581449',NULL,NULL,'新竹市','300','新竹市竹北市和平街407號','8070014','700000000006','{\"全酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(799,8,'115000008','06-07 22:29','楊強','test_4893@example.com','1998-04-20','0954814893',NULL,NULL,'新竹市','300','新竹市北區民權路984號','8070014','700000000007','{\"有\": \"Y\", \"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(800,9,'115000009','06-23 11:34','周茹宥','test_5529@example.com','1983-10-07','0949625529','03-5301346',NULL,'新竹市','300','新竹市竹東鎮經國路495號','8070014','700000000008','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(801,10,'115000010','06-26 08:31','王廷','test_2545@example.com','1983-11-10','0979342545','03-5482568',NULL,'新竹市','300','新竹市香山區和平街931號','8070014','700000000009','{\"有\": \"Y\", \"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(802,11,'115000011','06-26 10:39','李英廷','test_2010@example.com','1995-11-27','0914652010','03-5278284',NULL,'新竹市','300','新竹市香山區中華路198號','8070014','700000000010','{\"全酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(803,12,'115000012','06-10 12:53','周俊晴','test_3958@example.com','1995-03-28','0968553958','03-5598416',NULL,'新竹市','300','新竹市香山區中華路849號','8070014','700000000011','{\"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"[其它].5\": \"無\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(804,13,'115000013','06-28 12:59','吳翔','test_2013@example.com','1986-05-23','0957162013',NULL,NULL,'新竹市','300','新竹市竹東鎮中央路791號','8070014','700000000012','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(805,14,'115000014','06-21 05:07','楊安','test_6690@example.com','1990-08-08','0933776690',NULL,NULL,'新竹市','300','新竹市湖口鄉和平街571號','8070014','700000000013','{\"半酒\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□薑水\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"洗澡水準備：\": \"□中藥包\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(806,15,'115000015','07-15 21:08','徐豪奕','test_9478@example.com','1991-01-01','0987389478',NULL,NULL,'新竹市','300','新竹市竹北市民權路967號','8070014','700000000014','{\"全酒\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(807,16,'115000016','06-13 23:27','陳萱奕','test_4666@example.com','1987-04-07','0928514666','03-5990989',NULL,'新竹市','300','新竹市湖口鄉測試路759號','8070014','700000000015','{\"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□洗碗機\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(808,17,'115000017','07-21 00:00','吳宏','test_3793@example.com','1999-10-08','0919603793',NULL,NULL,'新竹市','300','新竹市竹北市光復路913號','8070014','700000000016','{\"有\": \"Y\", \"全酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□熱奶器\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(809,18,'115000018','07-01 05:12','蔡俊','test_0311@example.com','1980-04-15','0959730311',NULL,NULL,'新竹市','300','新竹市香山區和平街818號','8070014','700000000017','{\"全酒\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(810,19,'115000019','07-16 14:34','高英明','test_1587@example.com','1982-04-18','0928091587','03-5574309',NULL,'新竹市','300','新竹市香山區測試路93號','8070014','700000000018','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(811,20,'115000020','06-15 16:23','胡華','test_9316@example.com','1987-12-08','0928989316',NULL,NULL,'新竹市','300','新竹市香山區測試路351號','8070014','700000000019','{\"有\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(812,21,'115000021','06-02 17:57','吳雅強','test_4299@example.com','1983-07-25','0985664299','03-5714325',NULL,'新竹市','300','新竹市北區測試路120號','8070014','700000000020','{\"有\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(813,22,'115000022','06-14 18:51','高廷晴','test_6571@example.com','1981-06-19','0906946571','03-5459600',NULL,'新竹市','300','新竹市湖口鄉中山路545號','8070014','700000000021','{\"有\": \"Y\", \"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□薑水\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(814,23,'115000023','05-29 23:53','蔡廷晴','test_3877@example.com','1998-06-06','0938953877',NULL,NULL,'新竹市','300','新竹市北區民權路860號','8070014','700000000022','{\"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(815,24,'115000024','07-11 12:18','許華雅','test_7086@example.com','1985-04-17','0949197086','03-5994822',NULL,'新竹市','300','新竹市東區經國路681號','8070014','700000000023','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"IP位址\": \"HC115011\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(816,25,'115000025','07-20 17:41','賴威','test_4080@example.com','1981-08-02','0941604080',NULL,NULL,'新竹市','300','新竹市湖口鄉經國路25號','8070014','700000000024','{\"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(817,26,'115000026','06-21 23:36','賴琪','test_4597@example.com','1996-06-02','0907264597',NULL,NULL,'新竹市','300','新竹市湖口鄉中央路147號','8070014','700000000025','{\"有\": \"Y\", \"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(818,27,'115000027','07-15 16:53','徐涵晴','test_4290@example.com','1990-12-22','0911104290','03-5802614',NULL,'新竹市','300','新竹市湖口鄉民權路835號','8070014','700000000026','{\"有\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(819,28,'115000028','06-12 10:35','張宏','test_0489@example.com','1991-08-10','0994000489','03-5667167',NULL,'新竹市','300','新竹市竹東鎮光復路523號','8070014','700000000027','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□橄欖油\": \"Y\", \"□炒菜鍋\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(820,29,'115000029','06-29 02:16','陳涵','test_2448@example.com','1991-09-20','0940662448',NULL,NULL,'新竹市','300','新竹市北區光復路938號','8070014','700000000028','{\"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(821,30,'115000030','06-19 15:16','高美','test_3881@example.com','1983-04-03','0927603881',NULL,NULL,'新竹市','300','新竹市湖口鄉民權路912號','8070014','700000000029','{\"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(822,31,'115000031','06-01 19:50','陳洋玲','test_3017@example.com','1985-02-06','0918503017',NULL,NULL,'新竹市','300','新竹市香山區光復路248號','8070014','700000000030','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(823,32,'115000032','07-02 04:59','徐涵豪','test_6446@example.com','1989-10-05','0904446446','03-5112843',NULL,'新竹市','300','新竹市竹東鎮經國路468號','8070014','700000000031','{\"有\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(824,33,'115000033','06-10 04:27','林安','test_0757@example.com','1988-03-25','0991170757','03-5788214',NULL,'新竹市','300','新竹市竹北市中山路114號','8070014','700000000032','{\"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(825,34,'115000034','06-25 02:22','蔡翔','test_3420@example.com','1994-09-28','0970933420','03-5712908',NULL,'新竹市','300','新竹市湖口鄉民權路807號','8070014','700000000033','{\"有\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(826,35,'115000035','06-23 09:15','劉婷晴','test_7640@example.com','1984-06-19','0903357640',NULL,NULL,'新竹市','300','新竹市香山區經國路735號','8070014','700000000034','{\"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(827,36,'115000036','07-16 12:06','趙豪','test_3589@example.com','1994-09-22','0988753589',NULL,NULL,'新竹市','300','新竹市竹北市中央路336號','8070014','700000000035','{\"半酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(828,37,'115000037','05-26 05:17','蔡嘉','test_7454@example.com','1985-05-10','0902107454',NULL,NULL,'新竹市','300','新竹市香山區經國路147號','8070014','700000000036','{\"有\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(829,38,'115000038','06-13 19:55','李安','test_4450@example.com','1992-12-09','0921824450',NULL,NULL,'新竹市','300','新竹市香山區中央路9號','8070014','700000000037','{\"有\": \"Y\", \"全酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(830,39,'115000039','06-20 23:00','吳宇','test_8885@example.com','1989-07-26','0943898885','03-5901866',NULL,'新竹市','300','新竹市竹北市和平街834號','8070014','700000000038','{\"有\": \"Y\", \"全酒\": \"Y\", \"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(831,40,'115000040','06-17 20:38','吳萱晴','test_2430@example.com','1988-07-10','0920212430',NULL,NULL,'新竹市','300','新竹市竹東鎮光復路459號','8070014','700000000039','{\"全酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(832,41,'115000041','06-25 09:20','劉婷','test_4385@example.com','2000-07-12','0945294385','03-5419367',NULL,'新竹市','300','新竹市湖口鄉中央路318號','8070014','700000000040','{\"有\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(833,42,'115000042','07-18 16:47','楊婷奕','test_1676@example.com','1989-01-16','0951481676',NULL,NULL,'新竹市','300','新竹市竹東鎮中央路36號','8070014','700000000041','{\"有\": \"Y\", \"全酒\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}',NULL,'2026-07-22 07:46:27','2026-07-22 07:46:27'),(834,43,'115000043','07-19 05:57','李宏','test_9576@example.com','1993-11-26','0900649576','03-5816978',NULL,'新竹市','300','新竹市東區測試路632號','8070014','700000000042','{\"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(835,44,'115000044','07-16 05:31','賴宇俊','test_1249@example.com','1998-04-05','0939601249',NULL,NULL,'新竹市','300','新竹市湖口鄉和平街98號','8070014','700000000043','{\"有\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□中藥壺\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□一般食用油\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(836,45,'115000045','06-09 17:11','王玲','test_0942@example.com','1997-04-15','0996230942',NULL,NULL,'新竹市','300','新竹市竹東鎮中華路916號','8070014','700000000044','{\"有\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"IP位址\": \"HC115011\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"無(願意負擔停車費用)\": \"Y\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(837,46,'115000046','07-07 12:49','蔡強廷','test_1894@example.com','1988-12-15','0902121894',NULL,NULL,'新竹市','300','新竹市北區民權路109號','8070014','700000000045','{\"有\": \"Y\", \"性別\": \"男\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□烤箱\": \"Y\", \"[其它].5\": \"無\", \"□洗碗機\": \"Y\", \"□炒菜鍋\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□一般食用油\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(838,47,'115000047','06-26 23:48','林英宏','test_8704@example.com','1995-04-10','0981258704','03-5806460',NULL,'新竹市','300','新竹市東區中山路466號','8070014','700000000046','{\"有\": \"Y\", \"半酒\": \"Y\", \"性別\": \"女\", \"素食\": \"Y\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□母乳\": \"Y\", \"□鐵鍋\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□中藥壺\": \"Y\", \"□橄欖油\": \"Y\", \"□炒菜鍋\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□大同電鍋\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','需要提早','2026-07-22 07:46:27','2026-07-22 07:46:27'),(839,48,'115000048','07-11 21:37','張宏強','test_5273@example.com','1993-04-13','0976295273',NULL,NULL,'新竹市','300','新竹市湖口鄉測試路458號','8070014','700000000047','{\"有\": \"Y\", \"性別\": \"女\", \"葷食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□洗碗機\": \"Y\", \"□熱奶器\": \"Y\", \"□電子鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"□果汁機/調理棒\": \"Y\", \"□苦茶油(前兩週)\": \"Y\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','大寶1歲','2026-07-22 07:46:27','2026-07-22 07:46:27'),(840,49,'115000049','07-23 15:30','王冠','test_7113@example.com','1999-09-10','0989477113',NULL,NULL,'新竹市','300','新竹市北區和平街881號','8070014','700000000048','{\"有\": \"Y\", \"半酒\": \"Y\", \"性別\": \"男\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"[其它].5\": \"無\", \"□微波爐\": \"Y\", \"□橄欖油\": \"Y\", \"□熱奶器\": \"Y\", \"□配方奶\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□燉鍋/砂鍋\": \"Y\", \"□奶瓶消毒鍋\": \"Y\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"□母乳+配方奶\": \"Y\", \"□麻油(後兩週)\": \"Y\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27'),(841,50,'115000050','06-20 20:33','王嘉美','test_9572@example.com','2000-01-28','0906729572',NULL,NULL,'新竹市','300','新竹市湖口鄉中山路437號','8070014','700000000049','{\"性別\": \"男\", \"素食\": \"Y\", \"IP位址\": \"HC115011\", \"□烤箱\": \"Y\", \"□薑水\": \"Y\", \"□鐵鍋\": \"Y\", \"米酒水\": \"Y\", \"[其它].5\": \"無\", \"□中藥包\": \"Y\", \"□微波爐\": \"Y\", \"□炒菜鍋\": \"Y\", \"烹煮工具\": \"□炒菜鍋、□大同電鍋、□微波爐、□烤箱、□熱奶器、□奶瓶消毒鍋\", \"無酒料理\": \"Y\", \"□一般熱水\": \"Y\", \"哺乳方式：\": \"□母乳+配方奶\", \"身分證字號\": \"女\", \"□萬用壓力鍋\": \"Y\", \"洗澡水準備：\": \"□中藥包\", \"餐點喜忌備註：\": \"口味不想重複\", \"2．餐飲含酒比例：\": \"半酒\", \"□保溫壺(媽咪飲水)\": \"Y\", \"大樓公寓無樓層問題\": \"Y\", \"5媽咪有無過敏體質：\": \"□無\", \"※已確實詳閱退費原則：\": \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。、補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶、我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)、需自行負擔銀行轉帳手續費\", \"提供服務人員轎車停車位\": \"有\", \"特殊照護時應注意事項：\": \"依需求協助\", \"3．料理用油：(可接受種類)\": \"□苦茶油(前兩週)、□麻油(後兩週)、□橄欖油、□一般食用油\", \"服務時間內是否有其他寶寶\": \"1-2歲大寶\", \"需自行負擔銀行轉帳手續費\": \"Y\", \"月子餐點調理喜好/飲食習慣：\": \"葷食、可以接受中藥補品：□茶飲 □藥飲 □藥膳\", \"透天服務樓層方式(會加收樓層費)\": \"大樓公寓無樓層問題\", \"□(煮/泡 洗澡大豐草/艾草水) 的鍋或盆\": \"Y\", \"可以接受中藥補品：□茶飲 □藥飲 □藥膳\": \"Y\", \"特殊計費:甲方同意需另支付當日薪資1倍予乙方。\": \"[其它]無\", \"呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？\": \"無法接受\", \"我確實了解並願意遵照辦理以上相關規定，說明及退費原則(勾選後等同簽名確認)\": \"Y\", \"補助款退款作業:服務完成後,繳回相關服務日誌由工會協助提出申請, 新竹市政府核發後轉入雇主帳戶\": \"Y\", \"補助費用計費方式:自115年1月1日起接受本市到宅月子服務並向本府媒合平台提出申請且審核通過者,每日最高補助4小時：每一天到宅服務最多補助4小時。每戶最高補助40小時：整個坐月子期間（依服務日數計算），總補助時數上限為40小時。\": \"Y\"}','二寶出生','2026-07-22 07:46:27','2026-07-22 07:46:27');
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_architecture_bootstrap_events`
--

LOCK TABLES `case_architecture_bootstrap_events` WRITE;
/*!40000 ALTER TABLE `case_architecture_bootstrap_events` DISABLE KEYS */;
INSERT INTO `case_architecture_bootstrap_events` VALUES (1,'115000001',0,1,'client-approved-v1',300,'approved-rates-v1','citizen',300,'一般市民','e2e07afb77ddf8146f1d70c0d272fe177cac6411d31c9914158387ed1a82b9ba','case-bootstrap-apply-d8fd8b1d275e4be583d616e7a1da92b8','development-bypass','既有案件採用已核准架構與政策。','case-bootstrap-apply-da846ad4bcb04f5dbdff35eed8a46803','2026-08-03 01:45:20'),(2,'115000002',0,2,'client-approved-v1',300,'approved-rates-v1','citizen',300,'一般市民','9a389fc6c4e7c73a1c5cc6e881422b5e0310c52d25ff89849a07108f62f20b37','case-bootstrap-apply-411e9ffae9ee4cbe90cd987ec29acafb','development-bypass','既有案件採用已核准架構與政策。','case-bootstrap-apply-7ee7fac3337144ed9f028bc7c0a673ae','2026-08-03 02:03:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_architecture_bootstrap_receipts`
--

LOCK TABLES `case_architecture_bootstrap_receipts` WRITE;
/*!40000 ALTER TABLE `case_architecture_bootstrap_receipts` DISABLE KEYS */;
INSERT INTO `case_architecture_bootstrap_receipts` VALUES (1,'case-bootstrap-apply-d8fd8b1d275e4be583d616e7a1da92b8','41eb5bfd0b26bed464f984e83cddc89a984af09412d92ce1f0a5f3746ca171da','e2e07afb77ddf8146f1d70c0d272fe177cac6411d31c9914158387ed1a82b9ba','115000001',1,0,0,0,0,0,1,'{\"case_no\": \"115000001\", \"order_version\": 0, \"payroll_version\": 0, \"bootstrap_created\": true, \"bootstrap_event_id\": 1, \"scheduling_version\": 0, \"scheduling_generation\": 0, \"client_finance_version\": 0}','2026-08-03 01:45:20'),(2,'case-bootstrap-apply-411e9ffae9ee4cbe90cd987ec29acafb','ae6c6de74c6643fd84f20662a9be99d4426a12bf5d90b956dbd1d67bbec72871','9a389fc6c4e7c73a1c5cc6e881422b5e0310c52d25ff89849a07108f62f20b37','115000002',2,0,0,0,0,0,1,'{\"case_no\": \"115000002\", \"order_version\": 0, \"payroll_version\": 0, \"bootstrap_created\": true, \"bootstrap_event_id\": 2, \"scheduling_version\": 0, \"scheduling_generation\": 0, \"client_finance_version\": 0}','2026-08-03 02:03:20');
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
INSERT INTO `case_payroll_rate_policy_snapshots` VALUES ('115000001','approved-rates-v1','citizen',300,'一般市民',1,'2026-08-03 01:45:20'),('115000002','approved-rates-v1','citizen',300,'一般市民',2,'2026-08-03 02:03:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=344 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `case_staff_assignments`
--

LOCK TABLES `case_staff_assignments` WRITE;
/*!40000 ALTER TABLE `case_staff_assignments` DISABLE KEYS */;
INSERT INTO `case_staff_assignments` VALUES (227,'115000003',1,'115000003:g1:a1',565,1,'2026-07-17','2026-07-30','2026-07-17','2026-07-30',80.00,80.00,250.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(228,'115000003',1,'115000003:g1:a2',550,2,'2026-07-31','2026-08-13','2026-07-31','2026-08-13',80.00,80.00,250.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(229,'115000004',2,'115000004:g1:a1',573,1,'2026-06-01','2026-06-16','2026-06-01','2026-06-16',96.00,96.00,275.00,240.00,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(230,'115000004',2,'115000004:g1:a2',576,2,'2026-06-17','2026-07-03','2026-06-17','2026-07-03',104.00,104.00,275.00,260.00,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(231,'115000007',3,'115000007:g1:a1',566,1,'2026-07-20','2026-08-07','2026-07-20','2026-08-07',135.00,135.00,275.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(232,'115000008',4,'115000008:g1:a1',532,1,'2026-07-21','2026-07-31','2026-07-21','2026-07-31',90.00,90.00,300.00,333.33,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(233,'115000008',4,'115000008:g1:a2',572,2,'2026-08-01','2026-08-12','2026-08-01','2026-08-12',90.00,90.00,300.00,333.33,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(234,'115000008',4,'115000008:g1:a3',558,3,'2026-08-13','2026-08-24','2026-08-13','2026-08-24',90.00,90.00,300.00,333.34,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(235,'115000009',5,'115000009:g1:a1',563,1,'2026-06-08','2026-06-19','2026-06-08','2026-06-19',80.00,80.00,250.00,166.67,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(236,'115000009',5,'115000009:g1:a2',555,2,'2026-06-20','2026-07-03','2026-06-20','2026-07-03',80.00,80.00,250.00,166.67,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(237,'115000009',5,'115000009:g1:a3',540,3,'2026-07-04','2026-07-17','2026-07-04','2026-07-17',80.00,80.00,250.00,166.66,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(238,'115000010',6,'115000010:g1:a1',566,1,'2026-05-28','2026-06-16','2026-05-28','2026-06-16',480.00,480.00,275.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(239,'115000011',7,'115000011:g1:a1',532,1,'2026-06-27','2026-07-20','2026-06-27','2026-07-20',180.00,180.00,300.00,500.00,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(240,'115000013',8,'115000013:g1:a1',570,1,'2026-07-14','2026-08-17','2026-07-14','2026-08-17',200.00,200.00,275.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(241,'115000014',9,'115000014:g1:a1',548,1,'2026-06-09','2026-07-06','2026-06-09','2026-07-06',180.00,180.00,300.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:33','2026-08-02 16:23:56'),(242,'115000017',10,'115000017:g1:a1',574,1,'2026-05-23','2026-06-20','2026-05-23','2026-06-20',225.00,225.00,300.00,500.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(243,'115000018',11,'115000018:g1:a1',574,1,'2026-07-17','2026-08-14','2026-07-17','2026-08-14',200.00,200.00,250.00,500.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(244,'115000019',12,'115000019:g1:a1',565,1,'2026-06-18','2026-07-07','2026-06-18','2026-07-07',180.00,180.00,275.00,500.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(245,'115000020',13,'115000020:g1:a1',550,1,'2026-05-29','2026-07-09','2026-05-29','2026-07-09',720.00,720.00,300.00,500.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(246,'115000022',14,'115000022:g1:a1',541,1,'2026-05-25','2026-06-19','2026-05-25','2026-06-19',180.00,180.00,275.00,500.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(247,'115000024',15,'115000024:g1:a1',575,1,'2026-06-17','2026-07-21','2026-06-17','2026-07-21',200.00,200.00,250.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(248,'115000026',16,'115000026:g1:a1',531,1,'2026-06-05','2026-07-03','2026-06-05','2026-07-03',225.00,225.00,300.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(249,'115000027',17,'115000027:g1:a1',578,1,'2026-05-13','2026-06-16','2026-05-13','2026-06-16',720.00,720.00,250.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(250,'115000028',18,'115000028:g1:a1',536,1,'2026-07-20','2026-08-08','2026-07-20','2026-08-08',180.00,180.00,275.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(251,'115000031',19,'115000031:g1:a1',557,1,'2026-07-13','2026-08-15','2026-07-13','2026-08-15',270.00,270.00,275.00,1000.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(252,'115000034',20,'115000034:g1:a1',573,1,'2026-07-15','2026-08-12','2026-07-15','2026-08-12',600.00,600.00,275.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(253,'115000038',21,'115000038:g1:a1',563,1,'2026-07-15','2026-08-11','2026-07-15','2026-08-11',480.00,480.00,300.00,1000.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(254,'115000040',22,'115000040:g1:a1',535,1,'2026-07-21','2026-08-06','2026-07-21','2026-08-06',135.00,135.00,275.00,1000.00,'active',NULL,NULL,'2026-07-22 07:46:34','2026-08-02 16:23:56'),(255,'115000043',23,'115000043:g1:a1',547,1,'2026-05-29','2026-07-02','2026-05-29','2026-07-02',240.00,240.00,275.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:35','2026-08-02 16:23:56'),(256,'115000044',24,'115000044:g1:a1',537,1,'2026-06-01','2026-07-03','2026-06-01','2026-07-03',225.00,225.00,300.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:35','2026-08-02 16:23:56'),(257,'115000045',25,'115000045:g1:a1',549,1,'2026-07-15','2026-08-18','2026-07-15','2026-08-18',270.00,270.00,250.00,0.00,'active',NULL,NULL,'2026-07-22 07:46:35','2026-08-02 16:23:56'),(258,'115000047',26,'115000047:g1:a1',564,1,'2026-06-08','2026-07-03','2026-06-08','2026-07-03',160.00,160.00,300.00,0.00,'completed',NULL,NULL,'2026-07-22 07:46:35','2026-08-02 16:23:56'),(259,'115000048',NULL,NULL,551,1,'2026-07-20','2026-08-07','2026-07-20','2026-08-07',120.00,120.00,250.00,1000.00,'active',NULL,NULL,'2026-07-22 07:46:35','2026-07-30 10:53:06');
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
INSERT INTO `client_finance_accounts` VALUES ('115000001',0,'2026-08-03 01:45:20'),('115000002',0,'2026-08-03 02:03:20');
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
  `entry_type` enum('receipt','refund','adjustment','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  CONSTRAINT `chk_client_ledger_reversal_shape` CHECK ((((`entry_type` = _utf8mb4'reversal') and (`reversal_of_entry_id` is not null)) or ((`entry_type` <> _utf8mb4'reversal') and (`reversal_of_entry_id` is null))))
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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
INSERT INTO `client_payment_terms` VALUES ('115000001','client-approved-v1',300,5,'2026-06-07','2026-10-02',NULL,1,'2026-08-03 01:45:20'),('115000002','client-approved-v1',300,5,'2026-06-08','2026-10-10',NULL,2,'2026-08-03 02:03:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payment_terms_events`
--

LOCK TABLES `client_payment_terms_events` WRITE;
/*!40000 ALTER TABLE `client_payment_terms_events` DISABLE KEYS */;
INSERT INTO `client_payment_terms_events` VALUES (1,'115000001','client-approved-v1',300,5,'2026-06-07','2026-10-02',NULL,0,'case-bootstrap:e2e07afb77ddf8146f1d70c0d272fe177cac6411d31c9914158387ed1a82b9ba','bootstrap-terms:e2e07afb77ddf8146f1d70c0d272fe177cac6411d31c9914158387ed1a82b9ba','development-bypass','既有案件採用已核准架構與政策。','2026-08-03 01:45:20'),(2,'115000002','client-approved-v1',300,5,'2026-06-08','2026-10-10',NULL,0,'case-bootstrap:9a389fc6c4e7c73a1c5cc6e881422b5e0310c52d25ff89849a07108f62f20b37','bootstrap-terms:9a389fc6c4e7c73a1c5cc6e881422b5e0310c52d25ff89849a07108f62f20b37','development-bypass','既有案件採用已核准架構與政策。','2026-08-03 02:03:20');
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
) ENGINE=InnoDB AUTO_INCREMENT=2142 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payment_transactions`
--

LOCK TABLES `client_payment_transactions` WRITE;
/*!40000 ALTER TABLE `client_payment_transactions` DISABLE KEYS */;
INSERT INTO `client_payment_transactions` VALUES (2066,1403,'115000002','deposit','receipt','succeeded',18000.00,'2026-08-03','fake:115000002:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:29','2026-07-22 07:46:29'),(2067,1404,'115000003','deposit','receipt','succeeded',5600.00,'2026-07-14','fake:115000003:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2068,1404,'115000003','first_payment','receipt','succeeded',25200.00,'2026-07-22','fake:115000003:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2069,1405,'115000004','deposit','receipt','succeeded',6050.00,'2026-05-29','fake:115000004:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2070,1405,'115000004','first_payment','receipt','succeeded',27225.00,'2026-06-06','fake:115000004:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2071,1405,'115000004','second_payment','receipt','succeeded',27225.00,'2026-07-03','fake:115000004:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2072,1407,'115000006','deposit','receipt','succeeded',4200.00,'2026-08-05','fake:115000006:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2073,1408,'115000007','deposit','receipt','succeeded',4050.00,'2026-07-17','fake:115000007:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2074,1408,'115000007','first_payment','receipt','succeeded',18225.00,'2026-07-25','fake:115000007:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2075,1409,'115000008','deposit','receipt','succeeded',8200.00,'2026-07-18','fake:115000008:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2076,1409,'115000008','first_payment','receipt','succeeded',36900.00,'2026-07-26','fake:115000008:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2077,1410,'115000009','deposit','receipt','succeeded',7250.00,'2026-06-05','fake:115000009:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2078,1410,'115000009','first_payment','receipt','succeeded',32625.00,'2026-06-13','fake:115000009:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2079,1410,'115000009','second_payment','receipt','succeeded',32625.00,'2026-07-17','fake:115000009:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2080,1411,'115000010','deposit','receipt','succeeded',14400.00,'2026-05-25','fake:115000010:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2081,1411,'115000010','first_payment','receipt','succeeded',64800.00,'2026-06-02','fake:115000010:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2082,1411,'115000010','second_payment','receipt','succeeded',64800.00,'2026-06-16','fake:115000010:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2083,1412,'115000011','deposit','receipt','succeeded',6350.00,'2026-06-24','fake:115000011:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2084,1412,'115000011','first_payment','receipt','succeeded',28575.00,'2026-07-02','fake:115000011:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2085,1413,'115000012','deposit','receipt','succeeded',7925.00,'2026-07-26','fake:115000012:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:30','2026-07-22 07:46:30'),(2086,1414,'115000013','deposit','receipt','succeeded',6000.00,'2026-07-11','fake:115000013:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2088,1415,'115000014','deposit','receipt','succeeded',6300.00,'2026-06-06','fake:115000014:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2089,1415,'115000014','first_payment','receipt','succeeded',28350.00,'2026-06-14','fake:115000014:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2091,1418,'115000017','deposit','receipt','succeeded',7925.00,'2026-05-20','fake:115000017:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2092,1418,'115000017','first_payment','receipt','succeeded',35662.00,'2026-05-28','fake:115000017:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2093,1418,'115000017','second_payment','receipt','succeeded',35663.00,'2026-06-20','fake:115000017:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2094,1419,'115000018','deposit','receipt','succeeded',7050.00,'2026-07-14','fake:115000018:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2095,1419,'115000018','first_payment','receipt','succeeded',31725.00,'2026-07-22','fake:115000018:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2096,1420,'115000019','deposit','receipt','succeeded',6350.00,'2026-06-15','fake:115000019:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2097,1420,'115000019','first_payment','receipt','succeeded',28575.00,'2026-06-23','fake:115000019:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2098,1421,'115000020','deposit','receipt','succeeded',21650.00,'2026-05-26','fake:115000020:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2099,1421,'115000020','first_payment','receipt','succeeded',97425.00,'2026-06-03','fake:115000020:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2100,1421,'115000020','second_payment','receipt','succeeded',97425.00,'2026-07-09','fake:115000020:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2101,1423,'115000022','deposit','receipt','succeeded',5450.00,'2026-05-22','fake:115000022:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2102,1423,'115000022','first_payment','receipt','succeeded',24525.00,'2026-05-30','fake:115000022:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2103,1423,'115000022','second_payment','receipt','succeeded',24525.00,'2026-06-19','fake:115000022:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2104,1425,'115000024','deposit','receipt','succeeded',6000.00,'2026-06-14','fake:115000024:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2105,1425,'115000024','first_payment','receipt','succeeded',27000.00,'2026-06-22','fake:115000024:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2106,1425,'115000024','second_payment','receipt','succeeded',27000.00,'2026-07-21','fake:115000024:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2107,1427,'115000026','deposit','receipt','succeeded',7875.00,'2026-06-02','fake:115000026:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2108,1427,'115000026','first_payment','receipt','succeeded',35437.00,'2026-06-10','fake:115000026:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:31','2026-07-22 07:46:31'),(2109,1428,'115000027','deposit','receipt','succeeded',25200.00,'2026-05-10','fake:115000027:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2110,1428,'115000027','first_payment','receipt','succeeded',113400.00,'2026-05-18','fake:115000027:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2111,1428,'115000027','second_payment','receipt','succeeded',113400.00,'2026-06-16','fake:115000027:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2112,1429,'115000028','deposit','receipt','succeeded',6300.00,'2026-07-17','fake:115000028:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2113,1429,'115000028','first_payment','receipt','succeeded',28350.00,'2026-07-25','fake:115000028:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2114,1432,'115000031','deposit','receipt','succeeded',9550.00,'2026-07-10','fake:115000031:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2115,1432,'115000031','first_payment','receipt','succeeded',42975.00,'2026-07-18','fake:115000031:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2116,1433,'115000032','deposit','receipt','succeeded',21650.00,'2026-08-27','fake:115000032:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2117,1434,'115000033','deposit','receipt','succeeded',7875.00,'2026-07-29','fake:115000033:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2118,1435,'115000034','deposit','receipt','succeeded',21000.00,'2026-07-12','fake:115000034:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2119,1435,'115000034','first_payment','receipt','succeeded',94500.00,'2026-07-20','fake:115000034:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2120,1439,'115000038','deposit','receipt','succeeded',16900.00,'2026-07-12','fake:115000038:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2121,1439,'115000038','first_payment','receipt','succeeded',76050.00,'2026-07-20','fake:115000038:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2122,1441,'115000040','deposit','receipt','succeeded',4825.00,'2026-07-18','fake:115000040:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2123,1441,'115000040','first_payment','receipt','succeeded',21712.00,'2026-07-26','fake:115000040:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2124,1442,'115000041','deposit','receipt','succeeded',7875.00,'2026-08-08','fake:115000041:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2125,1444,'115000043','deposit','receipt','succeeded',8400.00,'2026-05-26','fake:115000043:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2126,1444,'115000043','first_payment','receipt','succeeded',37800.00,'2026-06-03','fake:115000043:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2127,1445,'115000044','deposit','receipt','succeeded',7875.00,'2026-05-29','fake:115000044:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2128,1445,'115000044','first_payment','receipt','succeeded',35437.00,'2026-06-06','fake:115000044:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2129,1445,'115000044','second_payment','receipt','succeeded',35438.00,'2026-07-03','fake:115000044:second_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2130,1446,'115000045','deposit','receipt','succeeded',9450.00,'2026-07-12','fake:115000045:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2131,1446,'115000045','first_payment','receipt','succeeded',42525.00,'2026-07-20','fake:115000045:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2132,1448,'115000047','deposit','receipt','succeeded',5600.00,'2026-06-05','fake:115000047:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2133,1448,'115000047','first_payment','receipt','succeeded',25200.00,'2026-06-13','fake:115000047:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2134,1449,'115000048','deposit','receipt','succeeded',3700.00,'2026-07-17','fake:115000048:deposit',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2135,1449,'115000048','first_payment','receipt','succeeded',16650.00,'2026-07-25','fake:115000048:first_payment',NULL,NULL,'假資料產生器建立的收款明細','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2136,1414,'115000013','first_payment','receipt','succeeded',1000.00,'2026-07-20','fake:115000013:boundary:first-1',NULL,NULL,'boundary: first payment partial receipt then overpay','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2137,1414,'115000013','first_payment','receipt','succeeded',1000.00,'2026-07-21','fake:115000013:boundary:first-2',NULL,NULL,'boundary: first payment partial receipt then overpay','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2138,1414,'115000013','first_payment','receipt','succeeded',1000.00,'2026-07-22','fake:115000013:boundary:first-3',NULL,NULL,'boundary: first payment partial receipt then overpay','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2139,1415,'115000014','second_payment','receipt','succeeded',3000.00,'2026-07-21','fake:115000014:boundary:second-overpay',NULL,NULL,'boundary: single second-payment overpay','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2140,1406,'115000005','deposit','receipt','succeeded',1000.00,'2026-07-18','fake:115000005:boundary:cancel-deposit',NULL,NULL,'boundary: cancelled order deposit receipt','2026-07-22 07:46:32','2026-07-22 07:46:32'),(2141,1406,'115000005','deposit','refund','succeeded',1000.00,'2026-07-19','fake:115000005:boundary:cancel-refund',NULL,NULL,'boundary: refund target 8070014/700000000004','2026-07-22 07:46:32','2026-07-22 07:46:32');
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
) ENGINE=InnoDB AUTO_INCREMENT=1452 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `client_payments`
--

LOCK TABLES `client_payments` WRITE;
/*!40000 ALTER TABLE `client_payments` DISABLE KEYS */;
INSERT INTO `client_payments` VALUES (1402,'115000001',10800.00,0.00,'2026-08-04',NULL,48600.00,0.00,NULL,NULL,48600.00,0.00,NULL,NULL,108000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','客戶改由家人照護，取消服務。 [BOUNDARY_CROSS_MONTH] [lifecycle_fixture]','2026-08-01 00:00:00','2026-07-22 07:46:29'),(1403,'115000002',18000.00,18000.00,'2026-08-03','2026-08-03',81000.00,0.00,NULL,NULL,81000.00,0.00,NULL,NULL,180000.00,18000.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','服務開始前一天請月嫂先電話聯繫客戶。 [BOUNDARY_WEEKEND_HOLIDAY] [lifecycle_fixture]','2026-07-31 00:00:00','2026-07-22 07:46:29'),(1404,'115000003',5600.00,5600.00,'2026-07-14','2026-07-14',25200.00,25200.00,'2026-07-17','2026-07-22',25200.00,0.00,NULL,NULL,56000.00,30800.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-11 00:00:00','2026-07-22 07:46:29'),(1405,'115000004',6050.00,6050.00,'2026-05-29','2026-05-29',27225.00,27225.00,'2026-06-01','2026-06-06',27225.00,27225.00,'2026-06-21','2026-07-03',60500.00,60500.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','客戶滿意度回訪完成。 [lifecycle_fixture]','2026-05-26 00:00:00','2026-07-22 07:46:30'),(1406,'115000005',1000.00,0.00,'2026-07-29',NULL,30375.00,0.00,NULL,NULL,30375.00,0.00,NULL,NULL,67500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已退款','預產期變動，暫停本次申請。 [lifecycle_fixture]','2026-07-26 00:00:00','2026-07-22 07:46:32'),(1407,'115000006',4200.00,4200.00,'2026-08-05','2026-08-05',18900.00,0.00,NULL,NULL,18900.00,0.00,NULL,NULL,42000.00,4200.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','服務開始前一天請月嫂先電話聯繫客戶。 [lifecycle_fixture]','2026-08-02 00:00:00','2026-07-22 07:46:30'),(1408,'115000007',4050.00,4050.00,'2026-07-17','2026-07-17',18225.00,18225.00,'2026-07-20','2026-07-25',18225.00,0.00,NULL,NULL,40500.00,22275.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-14 00:00:00','2026-07-22 07:46:30'),(1409,'115000008',8200.00,8200.00,'2026-07-18','2026-07-18',36900.00,36900.00,'2026-07-21','2026-07-26',36900.00,0.00,NULL,NULL,82000.00,45100.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-15 00:00:00','2026-07-22 07:46:30'),(1410,'115000009',7250.00,7250.00,'2026-06-05','2026-06-05',32625.00,32625.00,'2026-06-08','2026-06-13',32625.00,32625.00,'2026-06-28','2026-07-17',72500.00,72500.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','客戶滿意度回訪完成。 [lifecycle_fixture]','2026-06-02 00:00:00','2026-07-22 07:46:30'),(1411,'115000010',14400.00,14400.00,'2026-05-25','2026-05-25',64800.00,64800.00,'2026-05-28','2026-06-02',64800.00,64800.00,'2026-06-16','2026-06-16',144000.00,144000.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','客戶滿意度回訪完成。 [lifecycle_fixture]','2026-05-22 00:00:00','2026-07-22 07:46:30'),(1412,'115000011',6350.00,6350.00,'2026-06-24','2026-06-24',28575.00,28575.00,'2026-06-27','2026-07-02',28575.00,0.00,'2026-07-17',NULL,63500.00,34925.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','服務已完成，待客戶確認尾款匯入。 [lifecycle_fixture]','2026-06-21 00:00:00','2026-07-22 07:46:30'),(1413,'115000012',7925.00,7925.00,'2026-07-26','2026-07-26',35662.00,0.00,NULL,NULL,35663.00,0.00,NULL,NULL,79250.00,7925.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','服務開始前一天請月嫂先電話聯繫客戶。 [lifecycle_fixture]','2026-07-23 00:00:00','2026-07-22 07:46:30'),(1414,'115000013',6000.00,6000.00,'2026-07-11','2026-07-11',2500.00,3000.00,'2026-07-14','2026-07-22',27000.00,0.00,NULL,NULL,60000.00,9000.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待對帳超收','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-08 00:00:00','2026-07-22 07:46:32'),(1415,'115000014',6300.00,6300.00,'2026-06-06','2026-06-06',28350.00,28350.00,'2026-06-09','2026-06-14',2500.00,3000.00,'2026-06-29','2026-07-21',63000.00,37650.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待對帳超收','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-06-03 00:00:00','2026-07-22 07:46:32'),(1416,'115000015',12650.00,0.00,'2026-08-27',NULL,56925.00,0.00,NULL,NULL,56925.00,0.00,NULL,NULL,126500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','等待客戶補齊地址及家庭需求。 [lifecycle_fixture]','2026-08-24 00:00:00','2026-07-22 07:46:31'),(1417,'115000016',7875.00,0.00,'2026-09-12',NULL,35437.00,0.00,NULL,NULL,35438.00,0.00,NULL,NULL,78750.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','客戶初次來電，待確認服務天數與預產期。 [lifecycle_fixture]','2026-09-09 00:00:00','2026-07-22 07:46:31'),(1418,'115000017',7925.00,7925.00,'2026-05-20','2026-05-20',35662.00,35662.00,'2026-05-23','2026-05-28',35663.00,35663.00,'2026-06-12','2026-06-20',79250.00,79250.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-05-17 00:00:00','2026-07-22 07:46:31'),(1419,'115000018',7050.00,7050.00,'2026-07-14','2026-07-14',31725.00,31725.00,'2026-07-17','2026-07-22',31725.00,0.00,NULL,NULL,70500.00,38775.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','客戶反映寶寶夜間作息不穩，已請月嫂加強紀錄。 [lifecycle_fixture]','2026-07-11 00:00:00','2026-07-22 07:46:31'),(1420,'115000019',6350.00,6350.00,'2026-06-15','2026-06-15',28575.00,28575.00,'2026-06-18','2026-06-23',28575.00,0.00,'2026-07-07',NULL,63500.00,34925.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','月嫂費預計次月 15 日撥款。 [lifecycle_fixture]','2026-06-12 00:00:00','2026-07-22 07:46:31'),(1421,'115000020',21650.00,21650.00,'2026-05-26','2026-05-26',97425.00,97425.00,'2026-05-29','2026-06-03',97425.00,97425.00,'2026-06-18','2026-07-09',216500.00,216500.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-05-23 00:00:00','2026-07-22 07:46:31'),(1422,'115000021',9500.00,0.00,'2026-08-29',NULL,42750.00,0.00,NULL,NULL,42750.00,0.00,NULL,NULL,95000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','等待客戶補齊地址及家庭需求。 [lifecycle_fixture]','2026-08-26 00:00:00','2026-07-22 07:46:31'),(1423,'115000022',5450.00,5450.00,'2026-05-22','2026-05-22',24525.00,24525.00,'2026-05-25','2026-05-30',24525.00,24525.00,'2026-06-14','2026-06-19',54500.00,54500.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-05-19 00:00:00','2026-07-22 07:46:31'),(1424,'115000023',4850.00,0.00,'2026-08-25',NULL,21825.00,0.00,NULL,NULL,21825.00,0.00,NULL,NULL,48500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','客戶初次來電，待確認服務天數與預產期。 [lifecycle_fixture]','2026-08-22 00:00:00','2026-07-22 07:46:31'),(1425,'115000024',6000.00,6000.00,'2026-06-14','2026-06-14',27000.00,27000.00,'2026-06-17','2026-06-22',27000.00,27000.00,'2026-07-07','2026-07-21',60000.00,60000.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-06-11 00:00:00','2026-07-22 07:46:31'),(1426,'115000025',25200.00,0.00,'2026-08-24',NULL,113400.00,0.00,NULL,NULL,113400.00,0.00,NULL,NULL,252000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','[lifecycle_fixture]','2026-08-21 00:00:00','2026-07-22 07:46:31'),(1427,'115000026',7875.00,7875.00,'2026-06-02','2026-06-02',35437.00,35437.00,'2026-06-05','2026-06-10',35438.00,0.00,'2026-06-25',NULL,78750.00,43312.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','月嫂費預計次月 15 日撥款。 [lifecycle_fixture]','2026-05-30 00:00:00','2026-07-22 07:46:31'),(1428,'115000027',25200.00,25200.00,'2026-05-10','2026-05-10',113400.00,113400.00,'2026-05-13','2026-05-18',113400.00,113400.00,'2026-06-02','2026-06-16',252000.00,252000.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','客戶滿意度回訪完成。 [lifecycle_fixture]','2026-05-07 00:00:00','2026-07-22 07:46:32'),(1429,'115000028',6300.00,6300.00,'2026-07-17','2026-07-17',28350.00,28350.00,'2026-07-20','2026-07-25',28350.00,0.00,NULL,NULL,63000.00,34650.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','客戶反映寶寶夜間作息不穩，已請月嫂加強紀錄。 [lifecycle_fixture]','2026-07-14 00:00:00','2026-07-22 07:46:32'),(1430,'115000029',8100.00,0.00,'2026-07-21',NULL,36450.00,0.00,NULL,NULL,36450.00,0.00,NULL,NULL,81000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','客戶改由家人照護，取消服務。 [lifecycle_fixture]','2026-07-18 00:00:00','2026-07-22 07:46:32'),(1431,'115000030',4200.00,0.00,'2026-08-22',NULL,18900.00,0.00,NULL,NULL,18900.00,0.00,NULL,NULL,42000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','等待客戶補齊地址及家庭需求。 [lifecycle_fixture]','2026-08-19 00:00:00','2026-07-22 07:46:32'),(1432,'115000031',9550.00,9550.00,'2026-07-10','2026-07-10',42975.00,42975.00,'2026-07-13','2026-07-18',42975.00,0.00,NULL,NULL,95500.00,52525.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-07 00:00:00','2026-07-22 07:46:32'),(1433,'115000032',21650.00,21650.00,'2026-08-27','2026-08-27',97425.00,0.00,NULL,NULL,97425.00,0.00,NULL,NULL,216500.00,21650.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','服務開始前一天請月嫂先電話聯繫客戶。 [lifecycle_fixture]','2026-08-24 00:00:00','2026-07-22 07:46:32'),(1434,'115000033',7875.00,7875.00,'2026-07-29','2026-07-29',35437.00,0.00,NULL,NULL,35438.00,0.00,NULL,NULL,78750.00,7875.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','已收訂金，待產期前一週再次確認。 [lifecycle_fixture]','2026-07-26 00:00:00','2026-07-22 07:46:32'),(1435,'115000034',21000.00,21000.00,'2026-07-12','2026-07-12',94500.00,94500.00,'2026-07-15','2026-07-20',94500.00,0.00,NULL,NULL,210000.00,115500.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-09 00:00:00','2026-07-22 07:46:32'),(1436,'115000035',9550.00,0.00,'2026-08-07',NULL,42975.00,0.00,NULL,NULL,42975.00,0.00,NULL,NULL,95500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','已發送多位月嫂媒合邀請，等待回覆。 [lifecycle_fixture]','2026-08-04 00:00:00','2026-07-22 07:46:32'),(1437,'115000036',7200.00,0.00,'2026-08-20',NULL,32400.00,0.00,NULL,NULL,32400.00,0.00,NULL,NULL,72000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','已發送多位月嫂媒合邀請，等待回覆。 [lifecycle_fixture]','2026-08-17 00:00:00','2026-07-22 07:46:32'),(1438,'115000037',6050.00,0.00,'2026-08-14',NULL,27225.00,0.00,NULL,NULL,27225.00,0.00,NULL,NULL,60500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','等待客戶補齊地址及家庭需求。 [lifecycle_fixture]','2026-08-11 00:00:00','2026-07-22 07:46:32'),(1439,'115000038',16900.00,16900.00,'2026-07-12','2026-07-12',76050.00,76050.00,'2026-07-15','2026-07-20',76050.00,0.00,NULL,NULL,169000.00,92950.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-09 00:00:00','2026-07-22 07:46:32'),(1440,'115000039',12650.00,0.00,'2026-09-15',NULL,56925.00,0.00,NULL,NULL,56925.00,0.00,NULL,NULL,126500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','等待客戶補齊地址及家庭需求。 [lifecycle_fixture]','2026-09-12 00:00:00','2026-07-22 07:46:32'),(1441,'115000040',4825.00,4825.00,'2026-07-18','2026-07-18',21712.00,21712.00,'2026-07-21','2026-07-26',21713.00,0.00,NULL,NULL,48250.00,26537.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [lifecycle_fixture]','2026-07-15 00:00:00','2026-07-22 07:46:32'),(1442,'115000041',7875.00,7875.00,'2026-08-08','2026-08-08',35437.00,0.00,NULL,NULL,35438.00,0.00,NULL,NULL,78750.00,7875.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收訂金','服務開始前一天請月嫂先電話聯繫客戶。 [lifecycle_fixture]','2026-08-05 00:00:00','2026-07-22 07:46:32'),(1443,'115000042',21100.00,0.00,'2026-09-01',NULL,94950.00,0.00,NULL,NULL,94950.00,0.00,NULL,NULL,211000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','客戶偏好具雙胞胎照護經驗的服務人員。 [lifecycle_fixture]','2026-08-29 00:00:00','2026-07-22 07:46:32'),(1444,'115000043',8400.00,8400.00,'2026-05-26','2026-05-26',37800.00,37800.00,'2026-05-29','2026-06-03',37800.00,0.00,'2026-06-18',NULL,84000.00,46200.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','服務已完成，待客戶確認尾款匯入。 [lifecycle_fixture]','2026-05-23 00:00:00','2026-07-22 07:46:32'),(1445,'115000044',7875.00,7875.00,'2026-05-29','2026-05-29',35437.00,35437.00,'2026-06-01','2026-06-06',35438.00,35438.00,'2026-06-21','2026-07-03',78750.00,78750.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已結案','帳務與服務紀錄均已確認，案件結案。 [lifecycle_fixture]','2026-05-26 00:00:00','2026-07-22 07:46:32'),(1446,'115000045',9450.00,9450.00,'2026-07-12','2026-07-12',42525.00,42525.00,'2026-07-15','2026-07-20',42525.00,0.00,NULL,NULL,94500.00,51975.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','客戶反映寶寶夜間作息不穩，已請月嫂加強紀錄。 [lifecycle_fixture]','2026-07-09 00:00:00','2026-07-22 07:46:32'),(1447,'115000046',6800.00,0.00,'2026-08-21',NULL,30600.00,0.00,NULL,NULL,30600.00,0.00,NULL,NULL,68000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','[lifecycle_fixture]','2026-08-18 00:00:00','2026-07-22 07:46:32'),(1448,'115000047',5600.00,5600.00,'2026-06-05','2026-06-05',25200.00,25200.00,'2026-06-08','2026-06-13',25200.00,0.00,'2026-06-28',NULL,56000.00,30800.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','服務已完成，待客戶確認尾款匯入。 [lifecycle_fixture]','2026-06-02 00:00:00','2026-07-22 07:46:32'),(1449,'115000048',3700.00,3700.00,'2026-07-17','2026-07-17',16650.00,16650.00,'2026-07-20','2026-07-25',16650.00,0.00,NULL,NULL,37000.00,20350.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'已收一期款','國定假日由月嫂自主出勤，依規則計薪。 [CONFLICT_TEST_EXCLUDED_FROM_NORMAL_SCHEDULE] [lifecycle_fixture]','2026-07-14 00:00:00','2026-07-22 07:46:32'),(1450,'115000049',9500.00,0.00,'2026-08-20',NULL,42750.00,0.00,NULL,NULL,42750.00,0.00,NULL,NULL,95000.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','已發送多位月嫂媒合邀請，等待回覆。 [lifecycle_fixture]','2026-08-17 00:00:00','2026-07-22 07:46:32'),(1451,'115000050',6850.00,0.00,'2026-08-08',NULL,30825.00,0.00,NULL,NULL,30825.00,0.00,NULL,NULL,68500.00,0.00,0.00,0.00,NULL,NULL,0.00,0.00,NULL,NULL,NULL,NULL,'待收訂金','已發送多位月嫂媒合邀請，等待回覆。 [lifecycle_fixture]','2026-08-05 00:00:00','2026-07-22 07:46:32');
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
  `correction_type` enum('refund','reversal') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=10004 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `clients`
--

LOCK TABLES `clients` WRITE;
/*!40000 ALTER TABLE `clients` DISABLE KEYS */;
INSERT INTO `clients` VALUES (1011,1,NULL,'115000001','2026-06-04 23:58:49','100.100.139.242','楊洋玲(修改測試)','男','0993571802','新竹縣','新竹市竹東鎮和平街544號','一般市民','9小時','2026/09/24','2026/10/02','_x000D_',20,'公寓','自然產','週休2日','第二胎','user_422657',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-08-03 15:15:18'),(1012,2,NULL,'115000002','2026-06-05 05:45:45','100.100.201.209','黃欣','男','0927885396','新竹縣','新竹市竹東鎮經國路764號','一般市民','9小時','2026/10/05','2026/10/10','_x000D_',30,'公寓','剖腹產','週休1日','雙胞胎','user_793664',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:29'),(1013,3,NULL,'115000003','2026-07-20 22:00:24','100.100.24.206','李強','男','0975930598','新竹縣','新竹市東區光復路971號','低收入戶','24小時','2026/08/29','2026/09/02','_x000D_',30,'公寓','剖腹產','週休2日','雙胞胎','user_404471',NULL,'fixture_type=boundary; boundary_type=two_caregiver_active_handoff; owner_module=GenerateFakeData; expected=國定假日由月嫂自主出勤，依規則計薪。','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1014,4,NULL,'115000004','2026-07-22 17:22:35','100.100.120.226','陳建建','女','0904429297','新竹市','新竹市北區中華路45號','一般市民','24小時','2026/11/16','2026/11/23','_x000D_',20,'透天','自然產','週休2日','第一胎','user_179349',NULL,'fixture_type=boundary; boundary_type=two_caregiver_completed_handoff; owner_module=GenerateFakeData; expected=客戶滿意度回訪完成。','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1015,5,NULL,'115000005','2026-06-06 05:11:24','100.100.85.9','張建涵','女','0977396012','新竹縣','新竹市東區和平街551號','非市民','9小時','2026/11/20','2026/11/30','_x000D_',30,'透天','自然產','週休2日','第一胎','user_230620',NULL,'fixture_type=boundary; boundary_type=cancelled_deposit_refund; owner_module=GenerateFakeData; expected=預產期變動，暫停本次申請。','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1016,6,'資格不符測試','115000006','2026-06-08 18:40:05','100.100.45.170','林奕','女','0996104788','苗栗縣','新竹市北區中山路382號','中低收入戶','24小時','2026/10/22','2026/10/30','_x000D_',20,'大樓','自然產','連續服務','雙胞胎','user_104426',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1017,7,NULL,'115000007','2026-06-18 02:07:53','100.100.174.59','高芳','女','0913581449','新竹縣','新竹市竹北市和平街407號','一般市民','9小時','2026/12/05','2026/12/14','_x000D_',20,'透天','自然產','週休2日','雙胞胎','user_645747',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1018,8,'資格不符測試','115000008','2026-06-07 22:29:56','100.100.207.121','楊強','女','0954814893','苗栗縣','新竹市北區民權路984號','低收入戶','9小時','2026/08/28','2026/09/05','_x000D_',20,'大樓','剖腹產','週休1日','第一胎','user_629517',NULL,'fixture_type=boundary; boundary_type=three_caregiver_active_handoff; owner_module=GenerateFakeData; expected=國定假日由月嫂自主出勤，依規則計薪。','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1019,9,NULL,'115000009','2026-06-23 11:34:24','100.100.44.30','周茹宥','男','0949625529','苗栗縣','新竹市竹東鎮經國路495號','低收入戶','24小時','2026/08/26','2026/09/02','_x000D_',20,'公寓','剖腹產','週休2日','雙胞胎','user_721167',NULL,'fixture_type=boundary; boundary_type=three_caregiver_completed_prorated; owner_module=GenerateFakeData; expected=客戶滿意度回訪完成。','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1020,10,NULL,'115000010','2026-06-26 08:31:50','100.100.215.148','王廷','男','0979342545','苗栗縣','新竹市香山區和平街931號','一般市民','8小時','2026/11/20','2026/11/25','_x000D_',15,'公寓','剖腹產','連續服務','雙胞胎','user_586180',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1021,11,NULL,'115000011','2026-06-26 10:39:31','100.100.149.157','李英廷','男','0914652010','新竹市','新竹市香山區中華路198號','中低收入戶','24小時','2026/10/05','2026/10/15','_x000D_',30,'透天','自然產','週休1日','第二胎','user_758396',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1022,12,'資格不符測試','115000012','2026-06-10 12:53:27','100.100.76.186','周俊晴','女','0968553958','新竹縣','新竹市香山區中華路849號','低收入戶','24小時','2026/09/05','2026/09/10','_x000D_',20,'透天','剖腹產','連續服務','第一胎','user_837337',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:30'),(1023,13,NULL,'115000013','2026-06-28 12:59:29','100.100.26.188','吳翔','男','0957162013','新竹縣','新竹市竹東鎮中央路791號','中低收入戶','8小時','2026/11/13','2026/11/19','_x000D_',20,'透天','自然產','週休2日','第二胎','user_196973',NULL,'fixture_type=boundary; boundary_type=first_payment_partial_then_overpay; owner_module=GenerateFakeData; expected=國定假日由月嫂自主出勤，依規則計薪。','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1024,14,'資格不符測試','115000014','2026-06-21 05:07:20','100.100.198.136','楊安','女','0933776690','苗栗縣','新竹市湖口鄉和平街571號','一般市民','8小時','2026/10/28','2026/10/31','_x000D_',15,'透天','自然產','週休2日','雙胞胎','user_816632',NULL,'fixture_type=boundary; boundary_type=second_payment_single_overpay; owner_module=GenerateFakeData; expected=帳務與服務紀錄均已確認，案件結案。','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1025,15,NULL,'115000015','2026-07-15 21:08:54','100.100.120.123','徐豪奕','女','0987389478','苗栗縣','新竹市竹北市民權路967號','一般市民','8小時','2026/12/02','2026/12/06','_x000D_',30,'公寓','剖腹產','連續服務','第二胎','user_203330',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1026,16,NULL,'115000016','2026-06-13 23:27:48','100.100.10.104','陳萱奕','女','0928514666','新竹市','新竹市湖口鄉測試路759號','中低收入戶','9小時','2026/10/10','2026/10/20','_x000D_',30,'公寓','剖腹產','連續服務','第一胎','user_449936',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1027,17,NULL,'115000017','2026-07-21 00:00:12','100.100.104.200','吳宏','男','0919603793','新竹縣','新竹市竹北市光復路913號','非市民','24小時','2026/08/22','2026/08/30','_x000D_',30,'透天','剖腹產','週休1日','第一胎','user_321078',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1028,18,NULL,'115000018','2026-07-01 05:12:06','100.100.137.80','蔡俊','女','0959730311','新竹縣','新竹市香山區和平街818號','一般市民','9小時','2026/10/28','2026/11/03','_x000D_',30,'大樓','剖腹產','週休1日','第一胎','user_623347',NULL,'fixture_type=boundary; boundary_type=double_pay_schedule_day; owner_module=GenerateFakeData; expected=客戶反映寶寶夜間作息不穩，已請月嫂加強紀錄。','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1029,19,'資格不符測試','115000019','2026-07-16 14:34:18','100.100.212.104','高英明','女','0928091587','新竹市','新竹市香山區測試路93號','一般市民','8小時','2026/09/06','2026/09/12','_x000D_',20,'公寓','自然產','連續服務','雙胞胎','user_333085',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1030,20,'資格不符測試','115000020','2026-06-15 16:23:27','100.100.211.122','胡華','女','0928989316','新竹縣','新竹市香山區測試路351號','一般市民','9小時','2026/11/05','2026/11/08','_x000D_',20,'大樓','自然產','週休2日','雙胞胎','user_155113',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1031,21,NULL,'115000021','2026-06-02 17:57:28','100.100.56.72','吳雅強','女','0985664299','新竹縣','新竹市北區測試路120號','一般市民','24小時','2026/09/13','2026/09/21','_x000D_',15,'大樓','自然產','連續服務','雙胞胎','user_508536',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1032,22,'資格不符測試','115000022','2026-06-14 18:51:39','100.100.79.213','高廷晴','男','0906946571','苗栗縣','新竹市湖口鄉中山路545號','非市民','9小時','2027/01/09','2027/01/14','_x000D_',15,'大樓','自然產','週休2日','雙胞胎','user_938857',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1033,23,'資格不符測試','115000023','2026-05-29 23:53:35','100.100.77.150','蔡廷晴','男','0938953877','苗栗縣','新竹市北區民權路860號','低收入戶','9小時','2026/11/02','2026/11/08','_x000D_',20,'公寓','自然產','連續服務','第二胎','user_979411',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1034,24,NULL,'115000024','2026-07-11 12:18:53','100.100.185.118','許華雅','女','0949197086','新竹市','新竹市東區經國路681號','一般市民','9小時','2026/08/26','2026/08/29','_x000D_',15,'大樓','剖腹產','週休2日','雙胞胎','user_651404',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1035,25,NULL,'115000025','2026-07-20 17:41:14','100.100.185.13','賴威','男','0941604080','新竹市','新竹市湖口鄉經國路25號','低收入戶','9小時','2026/09/26','2026/10/02','_x000D_',40,'大樓','剖腹產','週休1日','第一胎','user_422861',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:31'),(1036,26,NULL,'115000026','2026-06-21 23:36:28','100.100.110.17','賴琪','男','0907264597','新竹市','新竹市湖口鄉中央路147號','一般市民','9小時','2026/09/06','2026/09/14','_x000D_',15,'大樓','剖腹產','週休1日','雙胞胎','user_588252',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1037,27,NULL,'115000027','2026-07-15 16:53:27','100.100.81.75','徐涵晴','男','0911104290','新竹市','新竹市湖口鄉民權路835號','低收入戶','24小時','2027/01/04','2027/01/12','_x000D_',40,'公寓','剖腹產','週休1日','第一胎','user_909293',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1038,28,'資格不符測試','115000028','2026-06-12 10:35:25','100.100.214.8','張宏','女','0994000489','新竹市','新竹市竹東鎮光復路523號','非市民','9小時','2026/12/07','2026/12/12','_x000D_',30,'透天','剖腹產','連續服務','雙胞胎','user_171450',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1039,29,'資格不符測試','115000029','2026-06-29 02:16:09','100.100.183.183','陳涵','女','0940662448','新竹縣','新竹市北區光復路938號','一般市民','9小時','2026/10/31','2026/11/09','_x000D_',20,'透天','自然產','週休2日','第一胎','user_169389',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1040,30,'資格不符測試','115000030','2026-06-19 15:16:15','100.100.140.4','高美','男','0927603881','新竹市','新竹市湖口鄉民權路912號','一般市民','8小時','2026/12/22','2026/12/27','_x000D_',30,'大樓','剖腹產','週休2日','第二胎','user_968352',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1041,31,'資格不符測試','115000031','2026-06-01 19:50:23','100.100.151.228','陳洋玲','男','0918503017','苗栗縣','新竹市香山區光復路248號','中低收入戶','24小時','2026/12/15','2026/12/24','_x000D_',30,'大樓','剖腹產','週休1日','第二胎','user_780801',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1042,32,'資格不符測試','115000032','2026-07-02 04:59:43','100.100.44.238','徐涵豪','女','0904446446','新竹市','新竹市竹東鎮經國路468號','一般市民','8小時','2026/09/24','2026/09/30','_x000D_',40,'透天','剖腹產','週休2日','第一胎','user_956274',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1043,33,NULL,'115000033','2026-06-10 04:27:54','100.100.112.29','林安','男','0991170757','新竹縣','新竹市竹北市中山路114號','一般市民','8小時','2026/11/24','2026/11/29','_x000D_',30,'透天','自然產','週休1日','雙胞胎','user_394505',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1044,34,NULL,'115000034','2026-06-25 02:22:52','100.100.169.123','蔡翔','女','0970933420','新竹縣','新竹市湖口鄉民權路807號','非市民','8小時','2026/11/14','2026/11/23','_x000D_',40,'公寓','剖腹產','週休1日','第二胎','user_613652',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1045,35,NULL,'115000035','2026-06-23 09:15:14','100.100.3.33','劉婷晴','女','0903357640','新竹市','新竹市香山區經國路735號','一般市民','9小時','2026/08/29','2026/09/03','_x000D_',15,'透天','剖腹產','連續服務','第二胎','user_424550',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1046,36,NULL,'115000036','2026-07-16 12:06:00','100.100.16.159','趙豪','男','0988753589','新竹縣','新竹市竹北市中央路336號','一般市民','24小時','2026/08/23','2026/09/02','_x000D_',20,'大樓','剖腹產','連續服務','第二胎','user_902116',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1047,37,NULL,'115000037','2026-05-26 05:17:38','100.100.66.146','蔡嘉','男','0902107454','新竹市','新竹市香山區經國路147號','低收入戶','9小時','2026/10/26','2026/11/01','_x000D_',40,'透天','剖腹產','週休1日','第一胎','user_844684',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1048,38,NULL,'115000038','2026-06-13 19:55:13','100.100.32.245','李安','女','0921824450','新竹縣','新竹市香山區中央路9號','一般市民','9小時','2026/11/05','2026/11/13','_x000D_',15,'大樓','自然產','週休2日','第二胎','user_292643',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1049,39,NULL,'115000039','2026-06-20 23:00:13','100.100.23.117','吳宇','男','0943898885','苗栗縣','新竹市竹北市和平街834號','一般市民','9小時','2026/11/20','2026/11/27','_x000D_',30,'公寓','自然產','週休2日','第一胎','user_493770',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1050,40,NULL,'115000040','2026-06-17 20:38:17','100.100.41.219','吳萱晴','男','0920212430','苗栗縣','新竹市竹東鎮光復路459號','一般市民','8小時','2026/11/07','2026/11/16','_x000D_',20,'公寓','剖腹產','週休1日','雙胞胎','user_290099',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1051,41,NULL,'115000041','2026-06-25 09:20:32','100.100.177.212','劉婷','男','0945294385','新竹縣','新竹市湖口鄉中央路318號','一般市民','9小時','2026/10/19','2026/10/29','_x000D_',30,'大樓','剖腹產','週休2日','雙胞胎','user_501319',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1052,42,'資格不符測試','115000042','2026-07-18 16:47:13','100.100.105.174','楊婷奕','女','0951481676','新竹縣','新竹市竹東鎮中央路36號','一般市民','8小時','2026/12/07','2026/12/11','_x000D_',20,'透天','自然產','週休1日','第一胎','user_415080',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1053,43,NULL,'115000043','2026-07-19 05:57:07','100.100.19.204','李宏','男','0900649576','新竹縣','新竹市東區測試路632號','非市民','24小時','2026/11/07','2026/11/12','_x000D_',15,'透天','剖腹產','週休1日','第一胎','user_454592',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1054,44,'資格不符測試','115000044','2026-07-16 05:31:47','100.100.35.81','賴宇俊','男','0939601249','新竹縣','新竹市湖口鄉和平街98號','一般市民','24小時','2027/01/08','2027/01/15','_x000D_',30,'透天','自然產','週休2日','第一胎','user_904543',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1055,45,NULL,'115000045','2026-06-09 17:11:44','100.100.36.240','王玲','女','0996230942','新竹縣','新竹市竹東鎮中華路916號','低收入戶','9小時','2026/11/21','2026/11/28','_x000D_',20,'公寓','自然產','週休1日','第一胎','user_558845',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1056,46,'資格不符測試','115000046','2026-07-07 12:49:49','100.100.126.146','蔡強廷','女','0902121894','新竹市','新竹市北區民權路109號','低收入戶','8小時','2026/10/30','2026/11/06','_x000D_',30,'透天','自然產','連續服務','雙胞胎','user_124866',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1057,47,NULL,'115000047','2026-06-26 23:48:54','100.100.37.228','林英宏','男','0981258704','新竹市','新竹市東區中山路466號','非市民','8小時','2027/01/16','2027/01/20','_x000D_',30,'透天','自然產','週休2日','雙胞胎','user_615247',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1058,48,NULL,'115000048','2026-07-11 21:37:16','100.100.243.28','張宏強','男','0976295273','新竹市','新竹市湖口鄉測試路458號','一般市民','9小時','2027/01/01','2027/01/05','_x000D_',40,'大樓','剖腹產','週休2日','第二胎','user_745785',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1059,49,NULL,'115000049','2026-07-23 15:30:35','100.100.12.94','王冠','男','0989477113','新竹縣','新竹市北區和平街881號','非市民','9小時','2026/11/11','2026/11/17','_x000D_',15,'透天','剖腹產','週休1日','雙胞胎','user_835564',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32'),(1060,50,NULL,'115000050','2026-06-20 20:33:48','100.100.86.45','王嘉美','男','0906729572','新竹縣','新竹市湖口鄉中山路437號','一般市民','9小時','2026/11/28','2026/12/04','_x000D_',40,'透天','自然產','週休1日','第一胎','user_436520',NULL,'fixture_type=normal; boundary_type=none','2026-07-22 07:46:27','2026-07-22 07:46:32');
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
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_batches`
--

LOCK TABLES `finance_import_batches` WRITE;
/*!40000 ALTER TABLE `finance_import_batches` DISABLE KEYS */;
INSERT INTO `finance_import_batches` VALUES (16,'taishin','fixture_duplicate_a.xlsx','交易明細查詢',16,1,'staged',NULL,'2026-07-22 07:46:35',NULL),(17,'taishin','fixture_duplicate_b.xlsx','交易明細查詢',16,1,'staged',NULL,'2026-07-22 07:46:35',NULL);
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
  `classification_type` enum('client_receipt','client_subsidy_return','government_subsidy','staff_payout','non_business_review') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=79 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_occurrences`
--

LOCK TABLES `finance_import_occurrences` WRITE;
/*!40000 ALTER TABLE `finance_import_occurrences` DISABLE KEYS */;
INSERT INTO `finance_import_occurrences` VALUES (70,16,67,'fixture_duplicate_a.xlsx','交易明細查詢',17,'[\"fixture_duplicate_import\"]','2026-07-22 07:46:35'),(71,17,67,'fixture_duplicate_b.xlsx','交易明細查詢',23,'[\"fixture_duplicate_import\"]','2026-07-22 07:46:35');
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
  `intent_type` enum('dispatch_completed','manual_correction_completed','initial_classification_recorded') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
) ENGINE=InnoDB AUTO_INCREMENT=77 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `finance_import_rows`
--

LOCK TABLES `finance_import_rows` WRITE;
/*!40000 ALTER TABLE `finance_import_rows` DISABLE KEYS */;
INSERT INTO `finance_import_rows` VALUES (67,'0957889518baba65266be9a6b67369f15f4b05eddedab61bace9520b5b4b0cc3',16,'taishin','fixture_duplicate_a.xlsx','8120000000000000','交易明細查詢',17,NULL,'2026-07-15','09:08:07','2026-07-15',NULL,1200.00,NULL,'outgoing',8000.00,'TWD','假資料重複匯入測試','同一筆流水跨檔重複匯入',NULL,'0012345678901234',NULL,NULL,'{\"amount\": \"1200.00\", \"sequence\": \"fixture-duplicate\"}','[\"fixture_duplicate_import\"]','{\"備註\": \"跨檔重複匯入假資料\", \"支出金額\": \"1200.00\"}','[]','non_business_review','counterparty_account_no_match',NULL,'pending',NULL,NULL,'2026-07-22 07:46:35');
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
  `intent_type` enum('government_subsidy_receipt_applied','government_subsidy_reversal_applied','government_subsidy_anomaly_root_changed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
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
  `is_double_pay_default` tinyint(1) DEFAULT '1' COMMENT '是否預設為雙倍薪資日',
  PRIMARY KEY (`holiday_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `holidays`
--

LOCK TABLES `holidays` WRITE;
/*!40000 ALTER TABLE `holidays` DISABLE KEYS */;
INSERT INTO `holidays` VALUES ('2026-01-01','中華民國開國紀念日(元旦)',1),('2026-02-17','農曆除夕',1),('2026-02-18','春節初一',1),('2026-02-19','春節初二',1),('2026-02-20','春節初三',1),('2026-02-21','春節初四',1),('2026-02-22','春節初五',1),('2026-02-27','和平紀念日(補假)',1),('2026-02-28','和平紀念日',1),('2026-04-03','兒童節',1),('2026-04-04','清明節/民族掃墓節',1),('2026-06-19','端午節',1),('2026-09-25','中秋節',1),('2026-10-09','國慶日(補假)',1),('2026-10-10','國慶日',1);
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
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `line_rich_menu_publications`
--

LOCK TABLES `line_rich_menu_publications` WRITE;
/*!40000 ALTER TABLE `line_rich_menu_publications` DISABLE KEYS */;
INSERT INTO `line_rich_menu_publications` VALUES (1,'default_menu','customer','65090c49e5cef0da5d24e68207f5ae63b5a6713134deda5345fb2e6bcc6777d2','{\"id\": \"default_menu\", \"name\": \"一般用戶選單\", \"size\": {\"width\": 2500, \"height\": 843}, \"buttons\": [{\"id\": \"order_query\", \"label\": \"訂單查詢\", \"action\": {\"uri\": null, \"data\": null, \"text\": null, \"type\": \"uri\", \"uri_source\": \"liff\"}, \"bounds\": {\"x\": 0, \"y\": 0, \"width\": 1250, \"height\": 843}, \"text_color\": \"#FFFFFF\", \"background_color\": \"#1E3A8A\"}, {\"id\": \"contact_staff\", \"label\": \"尋找專員\", \"action\": {\"uri\": null, \"data\": null, \"text\": \"尋找專員\", \"type\": \"message\", \"uri_source\": \"literal\"}, \"bounds\": {\"x\": 1250, \"y\": 0, \"width\": 1250, \"height\": 843}, \"text_color\": \"#FFFFFF\", \"background_color\": \"#3B82F6\"}], \"enabled\": true, \"selected\": true, \"appearance\": {\"image_mode\": \"generated\", \"image_path\": \"line/default_menu.jpg\", \"image_asset_id\": null, \"background_color\": \"#F5F5F5\"}, \"audience_role\": \"customer\", \"chat_bar_text\": \"用戶選單\", \"set_as_default\": true}','published','richmenu-cba8ed923308c60cfe2276efa2471ddb',NULL,NULL,NULL,0,3,NULL,NULL,1,NULL,NULL,'2026-07-29 06:49:37',NULL,'2026-07-29 06:49:37',NULL,'2026-07-29 06:49:37'),(2,'staff_menu','staff','65090c49e5cef0da5d24e68207f5ae63b5a6713134deda5345fb2e6bcc6777d2','{\"id\": \"staff_menu\", \"name\": \"月嫂專屬選單\", \"size\": {\"width\": 2500, \"height\": 843}, \"buttons\": [{\"id\": \"order_query\", \"label\": \"訂單查詢\", \"action\": {\"uri\": null, \"data\": null, \"text\": \"訂單查詢\", \"type\": \"message\", \"uri_source\": \"literal\"}, \"bounds\": {\"x\": 0, \"y\": 0, \"width\": 1250, \"height\": 843}, \"text_color\": \"#FFFFFF\", \"background_color\": \"#BE123C\"}, {\"id\": \"schedule_query\", \"label\": \"班表查詢\", \"action\": {\"uri\": null, \"data\": null, \"text\": \"班表查詢\", \"type\": \"message\", \"uri_source\": \"literal\"}, \"bounds\": {\"x\": 1250, \"y\": 0, \"width\": 1250, \"height\": 843}, \"text_color\": \"#FFFFFF\", \"background_color\": \"#F43F5E\"}], \"enabled\": true, \"selected\": true, \"appearance\": {\"image_mode\": \"generated\", \"image_path\": \"line/staff_menu.jpg\", \"image_asset_id\": null, \"background_color\": \"#FFF1F2\"}, \"audience_role\": \"staff\", \"chat_bar_text\": \"月嫂專區\", \"set_as_default\": false}','published','richmenu-e27e6ba07582ea87c6c57ab75a124aa5',NULL,NULL,NULL,0,3,NULL,NULL,1,NULL,NULL,'2026-07-29 06:49:37',NULL,'2026-07-29 06:49:37',NULL,'2026-07-30 14:44:28');
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
  `sent_resume_at` datetime DEFAULT NULL COMMENT '履歷發送給客戶的時間；NULL 表示無明確發送事實',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_matching_case_staff` (`case_no`,`staff_id`),
  KEY `staff_id` (`staff_id`),
  CONSTRAINT `fk_matching_case_no` FOREIGN KEY (`case_no`) REFERENCES `orders` (`case_no`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `matching_records_ibfk_1` FOREIGN KEY (`staff_id`) REFERENCES `staff` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=248 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `matching_records`
--

LOCK TABLES `matching_records` WRITE;
/*!40000 ALTER TABLE `matching_records` DISABLE KEYS */;
INSERT INTO `matching_records` VALUES (223,'115000035',552,1,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(224,'115000035',573,NULL,'2026-07-22 07:46:32',NULL,NULL,NULL,NULL),(225,'115000036',580,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(226,'115000036',536,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(227,'115000036',537,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(228,'115000036',577,NULL,'2026-07-22 07:46:32',NULL,NULL,NULL,NULL),(229,'115000036',541,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(230,'115000042',560,NULL,'2026-07-22 07:46:32',NULL,NULL,NULL,NULL),(231,'115000042',561,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(232,'115000049',548,NULL,'2026-07-22 07:46:32',NULL,NULL,NULL,NULL),(233,'115000049',560,NULL,'2026-07-22 07:46:32',NULL,NULL,NULL,NULL),(234,'115000050',536,0,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(235,'115000050',533,1,'2026-07-22 07:46:32','2026-07-22 07:46:32',NULL,NULL,NULL),(236,'115000015',531,NULL,'2026-07-26 12:27:23',NULL,'2026-07-26 12:27:25',NULL,NULL),(240,'115000042',532,NULL,'2026-07-31 06:28:25',NULL,'2026-07-31 06:28:27',NULL,NULL),(241,'115000042',535,NULL,'2026-07-31 06:28:29',NULL,'2026-07-31 06:28:32',NULL,NULL),(242,'115000042',534,NULL,'2026-07-31 06:28:34',NULL,'2026-07-31 06:28:36',NULL,NULL),(243,'115000042',533,NULL,'2026-07-31 06:28:39',NULL,'2026-07-31 06:28:41',NULL,NULL),(244,'115000042',531,NULL,'2026-07-31 06:28:44',NULL,'2026-07-31 06:28:46',NULL,NULL),(245,'115000042',540,NULL,'2026-07-31 06:28:48',NULL,'2026-07-31 06:28:50',NULL,NULL),(246,'115000015',532,NULL,'2026-08-02 16:24:01',NULL,'2026-08-02 16:25:32',NULL,NULL),(247,'115000015',534,NULL,'2026-08-02 16:24:06',NULL,'2026-08-02 16:25:36',NULL,NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `order_lifecycle_control_events`
--

LOCK TABLES `order_lifecycle_control_events` WRITE;
/*!40000 ALTER TABLE `order_lifecycle_control_events` DISABLE KEYS */;
INSERT INTO `order_lifecycle_control_events` VALUES (1,'115000001','cancellation','order_cancelled','order','activate','migration:order_lifecycle_control_facts_v1','客戶改由家人照護，取消服務',0,'migration:legacy_status_bootstrap:115000001','dcd99e8d1bbe2b24fe50f81a8311fcddf6a2472306d35b5511fc7f97b5df8f9d','{\"reason\": \"客戶改由家人照護，取消服務\", \"case_no\": \"115000001\", \"migration\": \"order_lifecycle_control_facts_v1\", \"provenance\": \"legacy_status_bootstrap\", \"cancellation_date\": null}','2026-08-01 05:22:07.031190'),(2,'115000005','cancellation','order_cancelled','order','activate','migration:order_lifecycle_control_facts_v1','客戶改由家人照護，取消服務',0,'migration:legacy_status_bootstrap:115000005','62605025705513391d27001aacad833b0928a6360eabd6b2021d0542a9e16343','{\"reason\": \"客戶改由家人照護，取消服務\", \"case_no\": \"115000005\", \"migration\": \"order_lifecycle_control_facts_v1\", \"provenance\": \"legacy_status_bootstrap\", \"cancellation_date\": null}','2026-08-01 05:22:07.034017'),(3,'115000029','cancellation','order_cancelled','order','activate','migration:order_lifecycle_control_facts_v1','客戶改由家人照護，取消服務',0,'migration:legacy_status_bootstrap:115000029','eeb2f8127348e478155a3843df5018edc3aac7c56fc03971eb93771051f439e0','{\"reason\": \"客戶改由家人照護，取消服務\", \"case_no\": \"115000029\", \"migration\": \"order_lifecycle_control_facts_v1\", \"provenance\": \"legacy_status_bootstrap\", \"cancellation_date\": null}','2026-08-01 05:22:07.036817');
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
INSERT INTO `order_lifecycle_control_state` VALUES ('115000001','cancellation','order_cancelled','order','active',1,NULL,NULL,NULL,NULL,'客戶改由家人照護，取消服務','migration:order_lifecycle_control_facts_v1','2026-08-01 05:22:07.032229'),('115000005','cancellation','order_cancelled','order','active',2,NULL,NULL,NULL,NULL,'客戶改由家人照護，取消服務','migration:order_lifecycle_control_facts_v1','2026-08-01 05:22:07.034935'),('115000029','cancellation','order_cancelled','order','active',3,NULL,NULL,NULL,NULL,'客戶改由家人照護，取消服務','migration:order_lifecycle_control_facts_v1','2026-08-01 05:22:07.037775');
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
INSERT INTO `orders` VALUES ('115000001',1011,NULL,'訂單取消',0,'客戶改由家人照護，取消服務',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,15,24,0.00,NULL,NULL,'2026-10-02','2026-10-23',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000002',1012,537,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,24,0.00,NULL,NULL,'2026-10-10','2026-11-09',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000003',1013,565,'服務中',0,NULL,NULL,'2026-07-17','2026-08-13',NULL,NULL,NULL,NULL,NULL,20,8,0.00,NULL,NULL,'2026-09-02','2026-09-30',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000004',1014,573,'訂單完成',0,NULL,NULL,'2026-06-01','2026-07-03',NULL,NULL,NULL,NULL,NULL,25,8,500.00,NULL,NULL,'2026-11-23','2026-12-25',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000005',1015,NULL,'訂單取消',0,'客戶改由家人照護，取消服務',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2026-11-30','2027-01-01',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000006',1016,550,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,15,8,0.00,NULL,NULL,'2026-10-30','2026-11-13',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000007',1017,566,'服務中',0,NULL,NULL,'2026-07-20','2026-08-07',NULL,NULL,NULL,NULL,NULL,15,9,0.00,NULL,NULL,'2026-12-14','2027-01-01',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000008',1018,532,'服務中',0,NULL,NULL,'2026-07-21','2026-08-24',NULL,NULL,NULL,NULL,NULL,30,9,1000.00,NULL,NULL,'2026-09-05','2026-10-13',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000009',1019,563,'訂單完成',0,NULL,NULL,'2026-06-08','2026-07-17',NULL,NULL,NULL,NULL,NULL,30,8,500.00,NULL,NULL,'2026-09-02','2026-10-15',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000010',1020,566,'訂單完成',0,NULL,NULL,'2026-05-28','2026-06-16',NULL,NULL,NULL,NULL,NULL,20,24,0.00,NULL,NULL,'2026-11-25','2026-12-14',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000011',1021,532,'訂單完成',0,NULL,NULL,'2026-06-27','2026-07-20',NULL,NULL,NULL,NULL,NULL,20,9,500.00,NULL,NULL,'2026-10-15','2026-11-06',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000012',1022,542,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,500.00,NULL,NULL,'2026-09-10','2026-10-05',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000013',1023,570,'服務中',0,NULL,NULL,'2026-07-14','2026-08-17',NULL,NULL,NULL,NULL,NULL,25,8,0.00,NULL,NULL,'2026-11-19','2026-12-23',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000014',1024,548,'訂單完成',0,NULL,NULL,'2026-06-09','2026-07-06',NULL,NULL,NULL,NULL,NULL,20,9,0.00,NULL,NULL,'2026-10-31','2026-11-27',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000015',1025,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,15,24,500.00,NULL,NULL,'2026-12-06','2026-12-20',NULL,'2026-07-22 07:46:27','2026-07-30 14:44:34'),('115000016',1026,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2026-10-20','2026-11-13',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000017',1027,574,'訂單完成',0,NULL,NULL,'2026-05-23','2026-06-20',NULL,NULL,NULL,NULL,NULL,25,9,500.00,NULL,NULL,'2026-08-30','2026-09-29',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000018',1028,574,'服務中',0,NULL,NULL,'2026-07-17','2026-08-14',NULL,NULL,NULL,NULL,NULL,25,8,500.00,NULL,NULL,'2026-11-03','2026-12-01',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000019',1029,565,'訂單完成',0,NULL,NULL,'2026-06-18','2026-07-07',NULL,NULL,NULL,NULL,NULL,20,9,500.00,NULL,NULL,'2026-09-12','2026-10-02',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000020',1030,550,'訂單完成',0,NULL,NULL,'2026-05-29','2026-07-09',NULL,NULL,NULL,NULL,NULL,30,24,500.00,NULL,NULL,'2026-11-08','2026-12-18',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000021',1031,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,9,500.00,NULL,NULL,'2026-09-21','2026-10-23',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000022',1032,541,'訂單完成',0,NULL,NULL,'2026-05-25','2026-06-19',NULL,NULL,NULL,NULL,NULL,20,9,500.00,NULL,NULL,'2027-01-14','2027-02-10',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000023',1033,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,20,8,500.00,NULL,NULL,'2026-11-08','2026-11-27',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000024',1034,575,'訂單完成',0,NULL,NULL,'2026-06-17','2026-07-21',NULL,NULL,NULL,NULL,NULL,25,8,0.00,NULL,NULL,'2026-08-29','2026-10-05',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000025',1035,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,24,0.00,NULL,NULL,'2026-10-02','2026-11-07',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000026',1036,531,'訂單完成',0,NULL,NULL,'2026-06-05','2026-07-03',NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2026-09-14','2026-10-15',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000027',1037,578,'訂單完成',0,NULL,NULL,'2026-05-13','2026-06-16',NULL,NULL,NULL,NULL,NULL,30,24,0.00,NULL,NULL,'2027-01-12','2027-02-15',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000028',1038,536,'服務中',0,NULL,NULL,'2026-07-20','2026-08-08',NULL,NULL,NULL,NULL,NULL,20,9,0.00,NULL,NULL,'2026-12-12','2026-12-31',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000029',1039,NULL,'訂單取消',0,'客戶改由家人照護，取消服務',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,9,0.00,NULL,NULL,'2026-11-09','2026-12-18',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000030',1040,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,15,8,0.00,NULL,NULL,'2026-12-27','2027-01-15',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000031',1041,557,'服務中',0,NULL,NULL,'2026-07-13','2026-08-15',NULL,NULL,NULL,NULL,NULL,30,9,1000.00,NULL,NULL,'2026-12-24','2027-01-27',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000032',1042,580,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,24,500.00,NULL,NULL,'2026-09-30','2026-11-11',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000033',1043,576,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2026-11-29','2026-12-28',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000034',1044,573,'服務中',0,NULL,NULL,'2026-07-15','2026-08-12',NULL,NULL,NULL,NULL,NULL,25,24,0.00,NULL,NULL,'2026-11-23','2026-12-21',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000035',1045,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,9,1000.00,NULL,NULL,'2026-09-03','2026-10-03',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000036',1046,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,8,0.00,NULL,NULL,'2026-09-02','2026-10-02',NULL,'2026-07-22 07:46:27','2026-07-24 04:14:18'),('115000037',1047,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,8,500.00,NULL,NULL,'2026-11-01','2026-11-30',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000038',1048,563,'服務中',0,NULL,NULL,'2026-07-15','2026-08-11',NULL,NULL,NULL,NULL,NULL,20,24,1000.00,NULL,NULL,'2026-11-13','2026-12-10',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000039',1049,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,15,24,500.00,NULL,NULL,'2026-11-27','2026-12-17',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000040',1050,535,'服務中',0,NULL,NULL,'2026-07-21','2026-08-06',NULL,NULL,NULL,NULL,NULL,15,9,1000.00,NULL,NULL,'2026-11-16','2026-12-02',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000041',1051,564,'訂單成立',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2026-10-29','2026-12-02',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000042',1052,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,24,1000.00,NULL,NULL,'2026-12-11','2027-01-08',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000043',1053,547,'訂單完成',0,NULL,NULL,'2026-05-29','2026-07-02',NULL,NULL,NULL,NULL,NULL,30,8,0.00,NULL,NULL,'2026-11-12','2026-12-16',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000044',1054,537,'訂單完成',0,NULL,NULL,'2026-06-01','2026-07-03',NULL,NULL,NULL,NULL,NULL,25,9,0.00,NULL,NULL,'2027-01-15','2027-02-18',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000045',1055,549,'服務中',0,NULL,NULL,'2026-07-15','2026-08-18',NULL,NULL,NULL,NULL,NULL,30,9,0.00,NULL,NULL,'2026-11-28','2027-01-01',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000046',1056,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,500.00,NULL,NULL,'2026-11-06','2026-11-30',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000047',1057,564,'訂單完成',0,NULL,NULL,'2026-06-08','2026-07-03',NULL,NULL,NULL,NULL,NULL,20,8,0.00,NULL,NULL,'2027-01-20','2027-02-16',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000048',1058,551,'服務中',0,NULL,NULL,'2026-07-20','2026-08-07',NULL,NULL,NULL,NULL,NULL,15,8,1000.00,NULL,NULL,'2027-01-05','2027-01-25',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000049',1059,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,30,9,500.00,NULL,NULL,'2026-11-17','2026-12-21',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20'),('115000050',1060,NULL,'洽談中',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,25,9,1000.00,NULL,NULL,'2026-12-04','2027-01-01',NULL,'2026-07-22 07:46:27','2026-07-24 00:37:20');
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
INSERT INTO `payroll_case_accounts` VALUES ('115000001',0,'2026-08-03 01:45:20'),('115000002',0,'2026-08-03 02:03:20');
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
INSERT INTO `payroll_rate_policies` VALUES ('approved-rates-v1','citizen',300,'1900-01-01',NULL,'2026-08-02 16:25:56'),('approved-rates-v1','subsidized_citizen',350,'1900-01-01',NULL,'2026-08-02 16:25:56'),('approved-rates-v1','non_citizen',320,'1900-01-01',NULL,'2026-08-02 16:25:56');
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
INSERT INTO `scheduling_aggregates` VALUES ('115000001',0,0,NULL,'2026-08-03 01:45:20','2026-08-03 01:45:20'),('115000002',0,0,NULL,'2026-08-03 02:03:20','2026-08-03 02:03:20'),('115000003',1,1,1,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000004',1,1,2,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000007',1,1,3,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000008',1,1,4,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000009',1,1,5,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000010',1,1,6,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000011',1,1,7,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000013',1,1,8,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000014',1,1,9,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000017',1,1,10,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000018',1,1,11,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000019',1,1,12,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000020',1,1,13,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000022',1,1,14,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000024',1,1,15,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000026',1,1,16,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000027',1,1,17,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000028',1,1,18,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000031',1,1,19,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000034',1,1,20,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000038',1,1,21,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000040',1,1,22,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000043',1,1,23,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000044',1,1,24,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000045',1,1,25,'2026-08-02 16:23:56','2026-08-02 16:23:56'),('115000047',1,1,26,'2026-08-02 16:23:56','2026-08-02 16:23:56');
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
) ENGINE=InnoDB AUTO_INCREMENT=88 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_bootstrap_review_events`
--

LOCK TABLES `scheduling_bootstrap_review_events` WRITE;
/*!40000 ALTER TABLE `scheduling_bootstrap_review_events` DISABLE KEYS */;
INSERT INTO `scheduling_bootstrap_review_events` VALUES (1,'115000048','SCHED-BOOT-006','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-006\", \"SCHED-BOOT-007\", \"SCHED-BOOT-008\"], \"schedule_count\": 0, \"assignment_count\": 1}','2026-08-02 16:23:56'),(2,'115000048','SCHED-BOOT-007','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-006\", \"SCHED-BOOT-007\", \"SCHED-BOOT-008\"], \"schedule_count\": 0, \"assignment_count\": 1}','2026-08-02 16:23:56'),(3,'115000048','SCHED-BOOT-008','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-006\", \"SCHED-BOOT-007\", \"SCHED-BOOT-008\"], \"schedule_count\": 0, \"assignment_count\": 1}','2026-08-02 16:23:56'),(62,'115000003','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 28, \"assignment_count\": 2}','2026-08-02 17:45:11'),(63,'115000004','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 33, \"assignment_count\": 2}','2026-08-02 17:45:11'),(64,'115000007','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 19, \"assignment_count\": 1}','2026-08-02 17:45:11'),(65,'115000008','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 3}','2026-08-02 17:45:11'),(66,'115000009','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 40, \"assignment_count\": 3}','2026-08-02 17:45:11'),(67,'115000010','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 20, \"assignment_count\": 1}','2026-08-02 17:45:11'),(68,'115000011','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 24, \"assignment_count\": 1}','2026-08-02 17:45:11'),(69,'115000013','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 1}','2026-08-02 17:45:11'),(70,'115000014','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 28, \"assignment_count\": 1}','2026-08-02 17:45:11'),(71,'115000017','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 29, \"assignment_count\": 1}','2026-08-02 17:45:11'),(72,'115000018','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 29, \"assignment_count\": 1}','2026-08-02 17:45:11'),(73,'115000019','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 20, \"assignment_count\": 1}','2026-08-02 17:45:11'),(74,'115000020','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 42, \"assignment_count\": 1}','2026-08-02 17:45:11'),(75,'115000022','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 26, \"assignment_count\": 1}','2026-08-02 17:45:11'),(76,'115000024','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 1}','2026-08-02 17:45:11'),(77,'115000026','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 29, \"assignment_count\": 1}','2026-08-02 17:45:11'),(78,'115000027','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 1}','2026-08-02 17:45:11'),(79,'115000028','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 20, \"assignment_count\": 1}','2026-08-02 17:45:11'),(80,'115000031','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 34, \"assignment_count\": 1}','2026-08-02 17:45:11'),(81,'115000034','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 29, \"assignment_count\": 1}','2026-08-02 17:45:11'),(82,'115000038','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 28, \"assignment_count\": 1}','2026-08-02 17:45:11'),(83,'115000040','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 17, \"assignment_count\": 1}','2026-08-02 17:45:11'),(84,'115000043','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 1}','2026-08-02 17:45:11'),(85,'115000044','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 33, \"assignment_count\": 1}','2026-08-02 17:45:11'),(86,'115000045','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 35, \"assignment_count\": 1}','2026-08-02 17:45:11'),(87,'115000047','SCHED-BOOT-010','migration:scheduling_generation_bootstrap_v1','{\"issue_codes\": [\"SCHED-BOOT-010\"], \"schedule_count\": 26, \"assignment_count\": 1}','2026-08-02 17:45:11');
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
INSERT INTO `scheduling_effective_occupancy` VALUES (531,'2026-06-05',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-06',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-07',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-08',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-09',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-10',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-11',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-12',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-13',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-14',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-15',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-16',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-17',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-18',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-19',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-20',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-21',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-22',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-23',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-24',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-25',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-26',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-27',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-28',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-29',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-06-30',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-07-01',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-07-02',16,248,'assignment_interval','2026-08-02 16:23:56'),(531,'2026-07-03',16,248,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-06-27',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-06-28',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-06-29',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-06-30',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-01',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-02',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-03',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-04',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-05',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-06',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-07',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-08',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-09',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-10',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-11',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-12',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-13',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-14',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-15',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-16',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-17',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-18',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-19',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-20',7,239,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-21',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-22',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-23',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-24',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-25',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-26',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-27',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-28',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-29',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-30',4,232,'assignment_interval','2026-08-02 16:23:56'),(532,'2026-07-31',4,232,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-21',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-22',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-23',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-24',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-25',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-26',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-27',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-28',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-29',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-30',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-07-31',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-01',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-02',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-03',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-04',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-05',22,254,'assignment_interval','2026-08-02 16:23:56'),(535,'2026-08-06',22,254,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-20',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-21',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-22',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-23',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-24',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-25',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-26',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-27',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-28',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-29',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-30',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-07-31',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-01',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-02',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-03',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-04',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-05',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-06',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-07',18,250,'assignment_interval','2026-08-02 16:23:56'),(536,'2026-08-08',18,250,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-01',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-02',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-03',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-04',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-05',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-06',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-07',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-08',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-09',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-10',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-11',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-12',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-13',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-14',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-15',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-16',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-17',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-18',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-19',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-20',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-21',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-22',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-23',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-24',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-25',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-26',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-27',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-28',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-29',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-06-30',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-07-01',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-07-02',24,256,'assignment_interval','2026-08-02 16:23:56'),(537,'2026-07-03',24,256,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-04',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-05',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-06',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-07',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-08',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-09',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-10',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-11',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-12',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-13',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-14',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-15',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-16',5,237,'assignment_interval','2026-08-02 16:23:56'),(540,'2026-07-17',5,237,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-25',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-26',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-27',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-28',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-29',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-30',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-05-31',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-01',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-02',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-03',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-04',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-05',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-06',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-07',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-08',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-09',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-10',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-11',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-12',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-13',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-14',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-15',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-16',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-17',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-18',14,246,'assignment_interval','2026-08-02 16:23:56'),(541,'2026-06-19',14,246,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-05-29',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-05-30',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-05-31',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-01',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-02',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-03',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-04',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-05',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-06',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-07',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-08',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-09',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-10',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-11',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-12',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-13',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-14',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-15',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-16',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-17',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-18',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-19',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-20',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-21',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-22',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-23',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-24',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-25',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-26',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-27',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-28',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-29',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-06-30',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-07-01',23,255,'assignment_interval','2026-08-02 16:23:56'),(547,'2026-07-02',23,255,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-09',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-10',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-11',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-12',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-13',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-14',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-15',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-16',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-17',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-18',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-19',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-20',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-21',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-22',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-23',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-24',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-25',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-26',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-27',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-28',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-29',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-06-30',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-01',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-02',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-03',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-04',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-05',9,241,'assignment_interval','2026-08-02 16:23:56'),(548,'2026-07-06',9,241,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-15',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-16',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-17',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-18',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-19',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-20',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-21',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-22',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-23',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-24',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-25',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-26',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-27',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-28',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-29',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-30',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-07-31',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-01',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-02',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-03',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-04',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-05',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-06',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-07',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-08',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-09',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-10',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-11',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-12',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-13',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-14',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-15',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-16',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-17',25,257,'assignment_interval','2026-08-02 16:23:56'),(549,'2026-08-18',25,257,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-05-29',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-05-30',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-05-31',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-01',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-02',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-03',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-04',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-05',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-06',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-07',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-08',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-09',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-10',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-11',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-12',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-13',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-14',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-15',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-16',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-17',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-18',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-19',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-20',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-21',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-22',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-23',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-24',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-25',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-26',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-27',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-28',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-29',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-06-30',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-01',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-02',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-03',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-04',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-05',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-06',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-07',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-08',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-09',13,245,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-07-31',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-01',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-02',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-03',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-04',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-05',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-06',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-07',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-08',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-09',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-10',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-11',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-12',1,228,'assignment_interval','2026-08-02 16:23:56'),(550,'2026-08-13',1,228,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-20',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-21',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-22',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-23',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-24',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-25',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-26',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-27',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-28',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-29',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-06-30',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-07-01',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-07-02',5,236,'assignment_interval','2026-08-02 16:23:56'),(555,'2026-07-03',5,236,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-13',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-14',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-15',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-16',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-17',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-18',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-19',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-20',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-21',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-22',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-23',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-24',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-25',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-26',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-27',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-28',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-29',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-30',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-07-31',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-01',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-02',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-03',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-04',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-05',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-06',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-07',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-08',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-09',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-10',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-11',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-12',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-13',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-14',19,251,'assignment_interval','2026-08-02 16:23:56'),(557,'2026-08-15',19,251,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-13',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-14',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-15',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-16',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-17',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-18',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-19',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-20',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-21',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-22',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-23',4,234,'assignment_interval','2026-08-02 16:23:56'),(558,'2026-08-24',4,234,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-08',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-09',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-10',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-11',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-12',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-13',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-14',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-15',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-16',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-17',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-18',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-06-19',5,235,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-15',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-16',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-17',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-18',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-19',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-20',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-21',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-22',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-23',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-24',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-25',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-26',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-27',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-28',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-29',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-30',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-07-31',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-01',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-02',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-03',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-04',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-05',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-06',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-07',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-08',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-09',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-10',21,253,'assignment_interval','2026-08-02 16:23:56'),(563,'2026-08-11',21,253,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-08',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-09',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-10',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-11',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-12',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-13',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-14',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-15',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-16',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-17',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-18',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-19',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-20',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-21',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-22',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-23',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-24',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-25',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-26',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-27',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-28',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-29',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-06-30',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-07-01',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-07-02',26,258,'assignment_interval','2026-08-02 16:23:56'),(564,'2026-07-03',26,258,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-18',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-19',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-20',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-21',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-22',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-23',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-24',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-25',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-26',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-27',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-28',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-29',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-06-30',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-01',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-02',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-03',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-04',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-05',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-06',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-07',12,244,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-17',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-18',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-19',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-20',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-21',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-22',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-23',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-24',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-25',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-26',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-27',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-28',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-29',1,227,'assignment_interval','2026-08-02 16:23:56'),(565,'2026-07-30',1,227,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-05-28',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-05-29',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-05-30',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-05-31',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-01',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-02',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-03',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-04',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-05',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-06',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-07',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-08',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-09',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-10',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-11',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-12',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-13',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-14',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-15',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-06-16',6,238,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-20',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-21',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-22',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-23',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-24',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-25',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-26',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-27',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-28',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-29',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-30',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-07-31',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-01',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-02',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-03',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-04',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-05',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-06',3,231,'assignment_interval','2026-08-02 16:23:56'),(566,'2026-08-07',3,231,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-14',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-15',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-16',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-17',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-18',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-19',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-20',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-21',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-22',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-23',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-24',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-25',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-26',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-27',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-28',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-29',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-30',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-07-31',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-01',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-02',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-03',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-04',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-05',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-06',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-07',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-08',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-09',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-10',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-11',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-12',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-13',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-14',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-15',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-16',8,240,'assignment_interval','2026-08-02 16:23:56'),(570,'2026-08-17',8,240,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-01',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-02',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-03',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-04',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-05',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-06',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-07',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-08',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-09',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-10',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-11',4,233,'assignment_interval','2026-08-02 16:23:56'),(572,'2026-08-12',4,233,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-01',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-02',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-03',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-04',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-05',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-06',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-07',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-08',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-09',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-10',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-11',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-12',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-13',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-14',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-15',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-06-16',2,229,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-15',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-16',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-17',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-18',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-19',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-20',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-21',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-22',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-23',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-24',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-25',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-26',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-27',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-28',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-29',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-30',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-07-31',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-01',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-02',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-03',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-04',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-05',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-06',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-07',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-08',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-09',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-10',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-11',20,252,'assignment_interval','2026-08-02 16:23:56'),(573,'2026-08-12',20,252,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-23',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-24',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-25',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-26',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-27',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-28',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-29',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-30',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-05-31',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-01',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-02',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-03',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-04',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-05',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-06',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-07',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-08',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-09',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-10',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-11',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-12',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-13',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-14',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-15',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-16',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-17',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-18',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-19',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-06-20',10,242,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-17',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-18',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-19',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-20',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-21',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-22',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-23',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-24',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-25',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-26',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-27',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-28',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-29',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-30',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-07-31',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-01',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-02',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-03',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-04',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-05',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-06',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-07',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-08',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-09',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-10',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-11',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-12',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-13',11,243,'assignment_interval','2026-08-02 16:23:56'),(574,'2026-08-14',11,243,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-17',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-18',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-19',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-20',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-21',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-22',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-23',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-24',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-25',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-26',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-27',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-28',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-29',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-06-30',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-01',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-02',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-03',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-04',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-05',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-06',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-07',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-08',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-09',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-10',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-11',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-12',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-13',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-14',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-15',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-16',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-17',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-18',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-19',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-20',15,247,'assignment_interval','2026-08-02 16:23:56'),(575,'2026-07-21',15,247,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-17',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-18',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-19',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-20',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-21',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-22',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-23',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-24',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-25',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-26',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-27',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-28',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-29',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-06-30',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-07-01',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-07-02',2,230,'assignment_interval','2026-08-02 16:23:56'),(576,'2026-07-03',2,230,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-13',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-14',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-15',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-16',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-17',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-18',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-19',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-20',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-21',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-22',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-23',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-24',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-25',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-26',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-27',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-28',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-29',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-30',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-05-31',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-01',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-02',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-03',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-04',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-05',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-06',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-07',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-08',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-09',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-10',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-11',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-12',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-13',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-14',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-15',17,249,'assignment_interval','2026-08-02 16:23:56'),(578,'2026-06-16',17,249,'assignment_interval','2026-08-02 16:23:56');
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
) ENGINE=InnoDB AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduling_generations`
--

LOCK TABLES `scheduling_generations` WRITE;
/*!40000 ALTER TABLE `scheduling_generations` DISABLE KEYS */;
INSERT INTO `scheduling_generations` VALUES (1,'115000003',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(2,'115000004',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(3,'115000007',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(4,'115000008',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(5,'115000009',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(6,'115000010',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(7,'115000011',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(8,'115000013',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(9,'115000014',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(10,'115000017',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(11,'115000018',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(12,'115000019',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(13,'115000020',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(14,'115000022',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(15,'115000024',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(16,'115000026',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(17,'115000027',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(18,'115000028',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(19,'115000031',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(20,'115000034',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(21,'115000038',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(22,'115000040',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(23,'115000043',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(24,'115000044',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(25,'115000045',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL),(26,'115000047',1,1,'effective',1,'migration:scheduling_generation_bootstrap_v1','Metadata-only bootstrap from verified legacy assignment ownership.','2026-08-02 16:23:56',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=8885 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff`
--

LOCK TABLES `staff` WRITE;
/*!40000 ALTER TABLE `staff` DISABLE KEYS */;
INSERT INTO `staff` VALUES (531,'2026-06-11 23:00:14','E100','郭萱','K225599902','0955849530','03-5571195',NULL,'test_9530@example.com','1970-01-15','新竹市','300','新竹市竹北市中山路213號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:51'),(532,'2026-05-30 18:27:34','E101','王明欣','B225550489','0956079789','03-5839813',NULL,'test_9789@example.com','1993-09-16','苗栗縣','350','新竹市湖口鄉中央路644號',0,'active',NULL,'[]',2,'[\"北區\", \"香山區\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:51'),(533,'2026-06-28 17:17:24','E102','楊豪','N211235004','0901295374',NULL,NULL,'test_5374@example.com','1966-06-23','苗栗縣','350','新竹市香山區中華路342號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"新竹縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:51'),(534,'2026-07-14 07:50:34','E103','許茹','A266615579','0937567022',NULL,NULL,'test_7022@example.com','1971-05-20','苗栗縣','350','新竹市北區中央路809號',1,'active',NULL,'[]',2,'[\"北區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(535,'2026-07-21 09:16:09','E104','楊華','D248164545','0976454689','03-5529568',NULL,'test_4689@example.com','1990-03-20','苗栗縣','350','新竹市竹東鎮測試路969號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"東區\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(536,'2026-07-01 14:43:39','E105','王洋','L259290874','0917379206',NULL,NULL,'test_9206@example.com','1993-04-04','新竹縣','302','新竹市竹北市民權路654號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"香山區\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(537,'2026-07-02 20:27:00','E106','趙安冠','S244218768','0934684683','03-5792788',NULL,'test_4683@example.com','1995-11-02','新竹市','300','新竹市香山區和平街112號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"東區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(538,'2026-07-03 17:29:09','E107','王建','F199137565','0949834796','03-5984192',NULL,'test_4796@example.com','1975-01-17','新竹市','300','新竹市北區測試路431號',1,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(539,'2026-05-24 03:29:56','E108','黃俊','K206753557','0937631499','03-5285109',NULL,'test_1499@example.com','1974-06-08','新竹市','300','新竹市湖口鄉民權路713號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"新竹縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(540,'2026-07-20 08:33:43','E109','周嘉美','I274367879','0903298549',NULL,NULL,'test_8549@example.com','1991-01-19','苗栗縣','350','新竹市香山區民權路699號',0,'active',NULL,'[]',2,'[\"香山區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(541,'2026-07-05 01:46:45','E110','吳玲嘉','O149631329','0915355878','03-5618861',NULL,'test_5878@example.com','1979-06-02','新竹縣','302','新竹市竹東鎮測試路726號',1,'active',NULL,'[\"Sunday\"]',1,'[\"東區\", \"香山區\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(542,'2026-05-26 06:32:50','E111','高玲欣','U175062830','0980865343','03-5203546',NULL,'test_5343@example.com','1993-12-18','新竹縣','302','新竹市湖口鄉測試路202號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"北區\", \"香山區\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(543,'2026-07-01 23:50:43','E112','吳建','R121931863','0994348511','03-5182490',NULL,'test_8511@example.com','1986-05-15','新竹縣','302','新竹市湖口鄉經國路330號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(544,'2026-07-16 19:48:19','E113','胡翔英','E122581527','0965188390',NULL,NULL,'test_8390@example.com','1970-09-13','新竹縣','302','新竹市東區和平街289號',0,'active',NULL,'[\"Sunday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(545,'2026-07-12 12:43:18','E114','張翔','J291918885','0904492495',NULL,NULL,'test_2495@example.com','1977-10-23','新竹縣','302','新竹市湖口鄉測試路202號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"東區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(546,'2026-05-26 00:58:42','E115','楊涵','X271024471','0914473778',NULL,NULL,'test_3778@example.com','1987-09-27','新竹市','300','新竹市竹東鎮中華路772號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"新竹縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(547,'2026-07-11 13:00:32','E116','黃君','Q109746903','0996787264','03-5387372',NULL,'test_7264@example.com','1977-09-13','新竹縣','302','新竹市湖口鄉經國路831號',0,'active',NULL,'[]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(548,'2026-07-10 08:02:01','E117','張婷','H184211396','0972559027',NULL,NULL,'test_9027@example.com','1993-08-19','新竹市','300','新竹市竹東鎮測試路499號',1,'active',NULL,'[\"Sunday\"]',1,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\"]','[\"葷食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(549,'2026-06-16 01:16:33','E118','周芳','L237766262','0993899921','03-5992178',NULL,'test_9921@example.com','1979-07-03','新竹縣','302','新竹市竹北市經國路546號',0,'active',NULL,'[\"Sunday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(550,'2026-05-31 11:01:27','E119','許威','V282665871','0945382860',NULL,NULL,'test_2860@example.com','1963-09-24','新竹市','300','新竹市竹北市和平街589號',0,'active',NULL,'[]',2,'[\"北區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(551,'2026-06-08 19:34:34','E120','高翔晴','E200086347','0901520578',NULL,NULL,'test_0578@example.com','1961-10-07','新竹市','300','新竹市香山區光復路35號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:52'),(552,'2026-05-23 16:07:45','E121','張安','X286547874','0963150251','03-5883982',NULL,'test_0251@example.com','1963-10-26','苗栗縣','350','新竹市香山區和平街143號',1,'active',NULL,'[\"Saturday\", \"Sunday\"]',1,'[\"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(553,'2026-06-12 16:29:17','E122','許華','O174644183','0978484440',NULL,NULL,'test_4440@example.com','1977-01-02','新竹縣','302','新竹市竹北市和平街911號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"東區\", \"香山區\", \"新竹縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(554,'2026-07-18 19:45:09','E123','黃豪','K151542575','0953592531','03-5832675',NULL,'test_2531@example.com','1977-07-21','新竹市','300','新竹市香山區光復路699號',1,'active',NULL,'[\"Sunday\"]',1,'[\"北區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(555,'2026-05-27 14:46:38','E124','張芳','U223900058','0904056014','03-5538337',NULL,'test_6014@example.com','1964-03-22','新竹市','300','新竹市湖口鄉和平街94號',0,'active',NULL,'[\"Sunday\"]',2,'[\"北區\", \"香山區\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(556,'2026-06-27 16:39:34','E125','張豪','E147602545','0922627413','03-5708828',NULL,'test_7413@example.com','1974-04-10','新竹縣','302','新竹市北區測試路111號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(557,'2026-06-14 19:41:41','E126','趙廷','X166247648','0908601608','03-5240429',NULL,'test_1608@example.com','1990-05-24','新竹市','300','新竹市竹北市和平街816號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"香山區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(558,'2026-06-24 02:47:38','E127','胡欣','Y111722348','0945043645',NULL,NULL,'test_3645@example.com','1965-10-10','新竹縣','302','新竹市竹北市中央路772號',0,'active',NULL,'[\"Sunday\"]',2,'[\"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(559,'2026-06-07 13:18:17','E128','陳宏','Z117332733','0903294796','03-5190787',NULL,'test_4796@example.com','1982-06-09','新竹縣','302','新竹市香山區民權路469號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(560,'2026-07-07 08:47:38','E129','賴萱茹','J102008469','0975326655','03-5916365',NULL,'test_6655@example.com','1963-06-25','新竹縣','302','新竹市北區中華路500號',1,'active',NULL,'[]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(561,'2026-07-21 18:11:18','E130','楊安冠','L255012221','0925770125','03-5917309',NULL,'test_0125@example.com','1990-09-19','新竹縣','302','新竹市竹東鎮中山路73號',0,'active',NULL,'[]',2,'[\"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(562,'2026-07-09 23:14:03','E131','吳君雅','T299850673','0996319901','03-5894461',NULL,'test_9901@example.com','1987-04-09','新竹市','300','新竹市湖口鄉和平街820號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"香山區\"]','[\"葷食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(563,'2026-06-04 16:59:06','E132','蔡翔','H205846444','0921890017','03-5319350',NULL,'test_0017@example.com','1968-08-26','新竹縣','302','新竹市香山區民權路213號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(564,'2026-06-13 15:00:15','E133','劉婷婷','W250274660','0966611244',NULL,NULL,'test_1244@example.com','1992-09-20','苗栗縣','350','新竹市香山區中華路79號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"東區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\"]','2026-07-22 07:46:28','2026-07-23 14:30:53'),(565,'2026-05-25 16:54:59','E134','趙玲','E234434277','0984622925','03-5640984',NULL,'test_2925@example.com','1991-11-05','苗栗縣','350','新竹市東區經國路93號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(566,'2026-06-03 07:13:11','E135','楊茹','P116108083','0907292146','03-5507710',NULL,'test_2146@example.com','1995-12-28','新竹市','300','新竹市竹北市光復路765號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(567,'2026-07-16 13:32:25','E136','陳建','C170541733','0972852780','03-5321986',NULL,'test_2780@example.com','1992-01-12','新竹市','300','新竹市東區中央路586號',1,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(568,'2026-06-10 09:04:39','E137','吳安','U140215412','0919398046',NULL,NULL,'test_8046@example.com','1971-11-04','新竹市','300','新竹市香山區和平街275號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',2,'[\"北區\", \"東區\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(569,'2026-05-23 16:36:55','E138','徐偉','V226321569','0954964969','03-5398620',NULL,'test_4969@example.com','1968-09-24','新竹市','300','新竹市竹北市中央路227號',0,'active',NULL,'[\"Saturday\", \"Sunday\"]',1,'[\"北區\"]','[\"葷食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(570,'2026-07-18 22:11:17','E139','黃豪','C146009235','0967316204','03-5720257',NULL,'test_6204@example.com','1974-09-09','新竹市','300','新竹市湖口鄉中央路243號',1,'active',NULL,'[\"Saturday\", \"Sunday\"]',1,'[\"東區\", \"新竹縣\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:53'),(571,'2026-06-30 09:15:50','E140','胡欣','G231554710','0943079473',NULL,NULL,'test_9473@example.com','1971-11-11','新竹縣','302','新竹市香山區光復路209號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"北區\", \"東區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(572,'2026-07-18 01:37:06','E141','高威','Y100461361','0991323378',NULL,NULL,'test_3378@example.com','1994-04-23','新竹縣','302','新竹市東區光復路64號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"東區\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(573,'2026-07-11 17:32:45','E142','劉偉','V126966897','0926018791',NULL,NULL,'test_8791@example.com','1986-11-05','苗栗縣','350','新竹市東區測試路908號',0,'active',NULL,'[\"Sunday\"]',2,'[\"新竹縣\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(574,'2026-06-08 14:45:50','E143','陳琪威','Q218194339','0955549874',NULL,NULL,'test_9874@example.com','1989-01-12','苗栗縣','350','新竹市東區民權路429號',0,'active',NULL,'[]',2,'[\"北區\", \"香山區\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(575,'2026-06-16 18:52:39','E144','蔡宇豪','J131791848','0934768387',NULL,NULL,'test_8387@example.com','1975-05-01','新竹市','300','新竹市竹東鎮光復路967號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(576,'2026-07-14 06:45:33','E145','蔡華奕','X241520308','0988635471','03-5491299',NULL,'test_5471@example.com','1989-02-13','苗栗縣','350','新竹市北區和平街893號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',2,'[\"北區\", \"香山區\", \"新竹縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(577,'2026-05-24 17:14:31','E146','高強','C274605552','0994844148','03-5892576',NULL,'test_4148@example.com','1996-08-24','苗栗縣','350','新竹市湖口鄉和平街494號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"北區\", \"東區\", \"新竹縣\", \"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(578,'2026-06-20 04:23:45','E147','黃翔','S130812792','0940979237',NULL,NULL,'test_9237@example.com','1980-12-06','新竹市','300','新竹市湖口鄉和平街615號',0,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"苗栗縣\"]','[\"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(579,'2026-07-06 04:43:05','E148','蔡冠','Z122466040','0992756211',NULL,NULL,'test_6211@example.com','1971-11-22','新竹縣','302','新竹市竹東鎮經國路330號',1,'active',NULL,'[]',2,'[\"東區\", \"香山區\", \"新竹縣\", \"苗栗縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54'),(580,'2026-07-13 23:01:48','E149','王華','W141784231','0947042565','03-5569245',NULL,'test_2565@example.com','1991-06-15','新竹縣','302','新竹市香山區經國路804號',1,'active',NULL,'[\"Sunday\", \"Saturday\"]',1,'[\"北區\", \"東區\", \"香山區\", \"新竹縣\"]','[\"葷食\", \"素食\"]','2026-07-22 07:46:29','2026-07-23 14:30:54');
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
) ENGINE=InnoDB AUTO_INCREMENT=118 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_actual_transfers`
--

LOCK TABLES `staff_actual_transfers` WRITE;
/*!40000 ALTER TABLE `staff_actual_transfers` DISABLE KEYS */;
INSERT INTO `staff_actual_transfers` VALUES (100,111,573,'normal','transfer','succeeded',26640.00,'2026-07-22','合作社','03201800231313','800000000042','fake:settlement:111',NULL,'fixture:settlement:111','confirmed','2026-07-22 07:46:35'),(101,112,576,'normal','transfer','succeeded',28860.00,'2026-07-22','合作社','03201800231313','800000000045','fake:settlement:112',NULL,'fixture:settlement:112','confirmed','2026-07-22 07:46:35'),(102,113,563,'normal','transfer','succeeded',30166.67,'2026-07-22','合作社','03201800231313','800000000032','fake:settlement:113',NULL,'fixture:settlement:113','confirmed','2026-07-22 07:46:35'),(103,114,555,'normal','transfer','succeeded',30166.67,'2026-07-22','合作社','03201800231313','800000000024','fake:settlement:114',NULL,'fixture:settlement:114','confirmed','2026-07-22 07:46:35'),(104,115,540,'normal','transfer','succeeded',30166.66,'2026-07-22','合作社','03201800231313','800000000009','fake:settlement:115',NULL,'fixture:settlement:115','confirmed','2026-07-22 07:46:35'),(105,116,566,'normal','transfer','succeeded',132000.00,'2026-07-22','合作社','03201800231313','800000000035','fake:settlement:116',NULL,'fixture:settlement:116','confirmed','2026-07-22 07:46:35'),(106,117,532,'normal','transfer','succeeded',54500.00,'2026-07-22','合作社','03201800231313','800000000001','fake:settlement:117',NULL,'fixture:settlement:117','confirmed','2026-07-22 07:46:35'),(107,118,548,'normal','transfer','succeeded',54000.00,'2026-07-22','合作社','03201800231313','800000000017','fake:settlement:118',NULL,'fixture:settlement:118','confirmed','2026-07-22 07:46:35'),(108,119,574,'normal','transfer','succeeded',68000.00,'2026-07-22','合作社','03201800231313','800000000043','fake:settlement:119',NULL,'fixture:settlement:119','confirmed','2026-07-22 07:46:35'),(109,120,565,'normal','transfer','succeeded',50000.00,'2026-07-22','合作社','03201800231313','800000000034','fake:settlement:120',NULL,'fixture:settlement:120','confirmed','2026-07-22 07:46:35'),(110,121,550,'normal','transfer','succeeded',216500.00,'2026-07-22','合作社','03201800231313','800000000019','fake:settlement:121',NULL,'fixture:settlement:121','confirmed','2026-07-22 07:46:35'),(111,122,541,'normal','transfer','succeeded',50000.00,'2026-07-22','合作社','03201800231313','800000000010','fake:settlement:122',NULL,'fixture:settlement:122','confirmed','2026-07-22 07:46:35'),(112,123,575,'normal','transfer','succeeded',50000.00,'2026-07-22','合作社','03201800231313','800000000044','fake:settlement:123',NULL,'fixture:settlement:123','confirmed','2026-07-22 07:46:35'),(113,124,531,'normal','transfer','succeeded',67500.00,'2026-07-22','合作社','03201800231313','800000000000','fake:settlement:124',NULL,'fixture:settlement:124','confirmed','2026-07-22 07:46:35'),(114,125,578,'normal','transfer','succeeded',180000.00,'2026-07-22','合作社','03201800231313','800000000047','fake:settlement:125',NULL,'fixture:settlement:125','confirmed','2026-07-22 07:46:35'),(115,126,547,'normal','transfer','succeeded',66000.00,'2026-07-22','合作社','03201800231313','800000000016','fake:settlement:126',NULL,'fixture:settlement:126','confirmed','2026-07-22 07:46:35'),(116,127,537,'normal','transfer','succeeded',67500.00,'2026-07-22','合作社','03201800231313','800000000006','fake:settlement:127',NULL,'fixture:settlement:127','confirmed','2026-07-22 07:46:35'),(117,128,564,'normal','transfer','succeeded',48000.00,'2026-07-22','合作社','03201800231313','800000000033','fake:settlement:128',NULL,'fixture:settlement:128','confirmed','2026-07-22 07:46:35');
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
INSERT INTO `staff_baby_types` VALUES (531,'雙胞胎',NULL),(532,'雙胞胎',NULL),(533,'單胞胎',NULL),(534,'單胞胎',NULL),(534,'雙胞胎',NULL),(535,'雙胞胎',NULL),(536,'雙胞胎',NULL),(537,'單胞胎',NULL),(537,'雙胞胎',NULL),(538,'雙胞胎',NULL),(539,'單胞胎',NULL),(539,'雙胞胎',NULL),(540,'單胞胎',NULL),(540,'雙胞胎',NULL),(541,'單胞胎',NULL),(542,'單胞胎',NULL),(543,'雙胞胎',NULL),(544,'單胞胎',NULL),(544,'雙胞胎',NULL),(545,'單胞胎',NULL),(546,'單胞胎',NULL),(546,'雙胞胎',NULL),(547,'雙胞胎',NULL),(548,'單胞胎',NULL),(549,'雙胞胎',NULL),(550,'雙胞胎',NULL),(551,'單胞胎',NULL),(551,'雙胞胎',NULL),(552,'單胞胎',NULL),(553,'單胞胎',NULL),(553,'雙胞胎',NULL),(554,'單胞胎',NULL),(555,'單胞胎',NULL),(555,'雙胞胎',NULL),(556,'單胞胎',NULL),(556,'雙胞胎',NULL),(557,'單胞胎',NULL),(557,'雙胞胎',NULL),(558,'單胞胎',NULL),(558,'雙胞胎',NULL),(559,'雙胞胎',NULL),(560,'單胞胎',NULL),(560,'雙胞胎',NULL),(561,'單胞胎',NULL),(561,'雙胞胎',NULL),(562,'單胞胎',NULL),(562,'雙胞胎',NULL),(563,'單胞胎',NULL),(563,'雙胞胎',NULL),(564,'單胞胎',NULL),(564,'雙胞胎',NULL),(565,'雙胞胎',NULL),(566,'單胞胎',NULL),(566,'雙胞胎',NULL),(567,'單胞胎',NULL),(567,'雙胞胎',NULL),(568,'雙胞胎',NULL),(569,'單胞胎',NULL),(570,'單胞胎',NULL),(571,'單胞胎',NULL),(572,'單胞胎',NULL),(572,'雙胞胎',NULL),(573,'單胞胎',NULL),(573,'雙胞胎',NULL),(574,'單胞胎',NULL),(574,'雙胞胎',NULL),(575,'單胞胎',NULL),(575,'雙胞胎',NULL),(576,'雙胞胎',NULL),(577,'單胞胎',NULL),(578,'單胞胎',NULL),(579,'單胞胎',NULL),(579,'雙胞胎',NULL),(580,'單胞胎',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=477 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_bank_accounts`
--

LOCK TABLES `staff_bank_accounts` WRITE;
/*!40000 ALTER TABLE `staff_bank_accounts` DISABLE KEYS */;
INSERT INTO `staff_bank_accounts` VALUES (427,531,'807','0014','800000000000',1),(428,532,'807','0014','800000000001',1),(429,533,'807','0014','800000000002',1),(430,534,'807','0014','800000000003',1),(431,535,'807','0014','800000000004',1),(432,536,'807','0014','800000000005',1),(433,537,'807','0014','800000000006',1),(434,538,'807','0014','800000000007',1),(435,539,'807','0014','800000000008',1),(436,540,'807','0014','800000000009',1),(437,541,'807','0014','800000000010',1),(438,542,'807','0014','800000000011',1),(439,543,'807','0014','800000000012',1),(440,544,'807','0014','800000000013',1),(441,545,'807','0014','800000000014',1),(442,546,'807','0014','800000000015',1),(443,547,'807','0014','800000000016',1),(444,548,'807','0014','800000000017',1),(445,549,'807','0014','800000000018',1),(446,550,'807','0014','800000000019',1),(447,551,'807','0014','800000000020',1),(448,552,'807','0014','800000000021',1),(449,553,'807','0014','800000000022',1),(450,554,'807','0014','800000000023',1),(451,555,'807','0014','800000000024',1),(452,556,'807','0014','800000000025',1),(453,557,'807','0014','800000000026',1),(454,558,'807','0014','800000000027',1),(455,559,'807','0014','800000000028',1),(456,560,'807','0014','800000000029',1),(457,561,'807','0014','800000000030',1),(458,562,'807','0014','800000000031',1),(459,563,'807','0014','800000000032',1),(460,564,'807','0014','800000000033',1),(461,565,'807','0014','800000000034',1),(462,566,'807','0014','800000000035',1),(463,567,'807','0014','800000000036',1),(464,568,'807','0014','800000000037',1),(465,569,'807','0014','800000000038',1),(466,570,'807','0014','800000000039',1),(467,571,'807','0014','800000000040',1),(468,572,'807','0014','800000000041',1),(469,573,'807','0014','800000000042',1),(470,574,'807','0014','800000000043',1),(471,575,'807','0014','800000000044',1),(472,576,'807','0014','800000000045',1),(473,577,'807','0014','800000000046',1),(474,578,'807','0014','800000000047',1),(475,579,'807','0014','800000000048',1),(476,580,'807','0014','800000000049',1);
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
INSERT INTO `staff_cooking_skills` VALUES (531,'素食',NULL),(532,'素食',NULL),(533,'素食',NULL),(533,'葷食',NULL),(534,'素食',NULL),(534,'葷食',NULL),(535,'素食',NULL),(536,'素食',NULL),(537,'素食',NULL),(537,'葷食',NULL),(538,'素食',NULL),(538,'葷食',NULL),(539,'素食',NULL),(540,'素食',NULL),(540,'葷食',NULL),(541,'素食',NULL),(542,'素食',NULL),(542,'葷食',NULL),(543,'葷食',NULL),(544,'素食',NULL),(544,'葷食',NULL),(545,'素食',NULL),(545,'葷食',NULL),(546,'素食',NULL),(546,'葷食',NULL),(547,'素食',NULL),(547,'葷食',NULL),(548,'葷食',NULL),(549,'葷食',NULL),(550,'素食',NULL),(551,'素食',NULL),(551,'葷食',NULL),(552,'素食',NULL),(552,'葷食',NULL),(553,'素食',NULL),(554,'素食',NULL),(554,'葷食',NULL),(555,'素食',NULL),(555,'葷食',NULL),(556,'素食',NULL),(556,'葷食',NULL),(557,'素食',NULL),(557,'葷食',NULL),(558,'素食',NULL),(559,'素食',NULL),(560,'素食',NULL),(560,'葷食',NULL),(561,'素食',NULL),(562,'葷食',NULL),(563,'素食',NULL),(563,'葷食',NULL),(564,'葷食',NULL),(565,'素食',NULL),(565,'葷食',NULL),(566,'素食',NULL),(567,'素食',NULL),(567,'葷食',NULL),(568,'素食',NULL),(568,'葷食',NULL),(569,'葷食',NULL),(570,'素食',NULL),(571,'素食',NULL),(571,'葷食',NULL),(572,'素食',NULL),(572,'葷食',NULL),(573,'素食',NULL),(574,'素食',NULL),(575,'素食',NULL),(575,'葷食',NULL),(576,'素食',NULL),(576,'葷食',NULL),(577,'素食',NULL),(578,'素食',NULL),(579,'素食',NULL),(579,'葷食',NULL),(580,'素食',NULL),(580,'葷食',NULL);
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
INSERT INTO `staff_holiday_availability` VALUES (531,'年節農曆過年初三',NULL),(532,'中秋節',NULL),(532,'國定假日必休',NULL),(532,'年節農曆過年初一',NULL),(532,'年節農曆過年初二',NULL),(532,'端午節',NULL),(533,'中秋節',NULL),(533,'國定假日必休',NULL),(533,'年節農曆過年初三',NULL),(533,'年節農曆過年初二',NULL),(534,'年節農曆過年初一',NULL),(535,'國定假日必休',NULL),(535,'年節農曆過年初一',NULL),(535,'年節農曆過年初二',NULL),(535,'端午節',NULL),(536,'中秋節',NULL),(536,'年節農曆過年初三',NULL),(536,'端午節',NULL),(537,'中秋節',NULL),(537,'國定假日必休',NULL),(537,'年節農曆過年初一',NULL),(537,'年節農曆過年初三',NULL),(537,'年節農曆過年初二',NULL),(537,'端午節',NULL),(538,'國定假日必休',NULL),(538,'年節農曆過年初二',NULL),(538,'端午節',NULL),(539,'國定假日必休',NULL),(539,'年節農曆過年初一',NULL),(539,'年節農曆過年初三',NULL),(540,'端午節',NULL),(541,'國定假日必休',NULL),(541,'年節農曆過年初一',NULL),(541,'年節農曆過年初三',NULL),(541,'年節農曆過年初二',NULL),(541,'端午節',NULL),(542,'中秋節',NULL),(542,'國定假日必休',NULL),(543,'中秋節',NULL),(543,'國定假日必休',NULL),(543,'年節農曆過年初一',NULL),(544,'中秋節',NULL),(544,'端午節',NULL),(545,'國定假日必休',NULL),(546,'年節農曆過年初三',NULL),(546,'年節農曆過年初二',NULL),(547,'國定假日必休',NULL),(547,'年節農曆過年初三',NULL),(547,'端午節',NULL),(548,'中秋節',NULL),(548,'年節農曆過年初三',NULL),(549,'中秋節',NULL),(549,'國定假日必休',NULL),(549,'年節農曆過年初一',NULL),(549,'年節農曆過年初三',NULL),(549,'年節農曆過年初二',NULL),(549,'端午節',NULL),(550,'中秋節',NULL),(550,'年節農曆過年初一',NULL),(551,'中秋節',NULL),(551,'國定假日必休',NULL),(551,'年節農曆過年初一',NULL),(551,'年節農曆過年初三',NULL),(551,'年節農曆過年初二',NULL),(552,'中秋節',NULL),(552,'國定假日必休',NULL),(552,'年節農曆過年初二',NULL),(553,'中秋節',NULL),(553,'國定假日必休',NULL),(553,'年節農曆過年初一',NULL),(553,'年節農曆過年初二',NULL),(553,'端午節',NULL),(554,'中秋節',NULL),(554,'國定假日必休',NULL),(554,'年節農曆過年初一',NULL),(554,'年節農曆過年初三',NULL),(554,'端午節',NULL),(555,'中秋節',NULL),(555,'國定假日必休',NULL),(555,'年節農曆過年初一',NULL),(555,'年節農曆過年初三',NULL),(555,'年節農曆過年初二',NULL),(555,'端午節',NULL),(556,'中秋節',NULL),(556,'年節農曆過年初一',NULL),(556,'年節農曆過年初三',NULL),(556,'端午節',NULL),(557,'中秋節',NULL),(557,'年節農曆過年初一',NULL),(557,'年節農曆過年初三',NULL),(557,'端午節',NULL),(558,'中秋節',NULL),(558,'國定假日必休',NULL),(558,'年節農曆過年初一',NULL),(558,'年節農曆過年初三',NULL),(558,'年節農曆過年初二',NULL),(558,'端午節',NULL),(559,'端午節',NULL),(560,'中秋節',NULL),(560,'年節農曆過年初一',NULL),(561,'國定假日必休',NULL),(561,'年節農曆過年初一',NULL),(561,'年節農曆過年初三',NULL),(561,'年節農曆過年初二',NULL),(561,'端午節',NULL),(562,'中秋節',NULL),(562,'國定假日必休',NULL),(562,'端午節',NULL),(563,'國定假日必休',NULL),(564,'端午節',NULL),(565,'年節農曆過年初三',NULL),(566,'年節農曆過年初三',NULL),(566,'年節農曆過年初二',NULL),(567,'中秋節',NULL),(567,'年節農曆過年初一',NULL),(567,'年節農曆過年初三',NULL),(567,'年節農曆過年初二',NULL),(568,'年節農曆過年初三',NULL),(568,'端午節',NULL),(569,'中秋節',NULL),(569,'年節農曆過年初三',NULL),(569,'年節農曆過年初二',NULL),(570,'年節農曆過年初三',NULL),(571,'國定假日必休',NULL),(571,'年節農曆過年初一',NULL),(571,'年節農曆過年初三',NULL),(571,'年節農曆過年初二',NULL),(571,'端午節',NULL),(572,'中秋節',NULL),(572,'國定假日必休',NULL),(572,'年節農曆過年初一',NULL),(572,'年節農曆過年初三',NULL),(572,'年節農曆過年初二',NULL),(572,'端午節',NULL),(573,'中秋節',NULL),(573,'國定假日必休',NULL),(573,'年節農曆過年初三',NULL),(573,'年節農曆過年初二',NULL),(573,'端午節',NULL),(574,'端午節',NULL),(575,'國定假日必休',NULL),(575,'年節農曆過年初一',NULL),(575,'年節農曆過年初二',NULL),(576,'年節農曆過年初三',NULL),(576,'年節農曆過年初二',NULL),(576,'端午節',NULL),(577,'中秋節',NULL),(577,'國定假日必休',NULL),(577,'年節農曆過年初一',NULL),(577,'年節農曆過年初三',NULL),(577,'年節農曆過年初二',NULL),(577,'端午節',NULL),(578,'中秋節',NULL),(578,'國定假日必休',NULL),(578,'年節農曆過年初一',NULL),(578,'年節農曆過年初三',NULL),(578,'年節農曆過年初二',NULL),(578,'端午節',NULL),(579,'中秋節',NULL),(580,'中秋節',NULL),(580,'國定假日必休',NULL),(580,'年節農曆過年初一',NULL),(580,'年節農曆過年初三',NULL),(580,'端午節',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=152 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_monthly_settlement_details`
--

LOCK TABLES `staff_monthly_settlement_details` WRITE;
/*!40000 ALTER TABLE `staff_monthly_settlement_details` DISABLE KEYS */;
INSERT INTO `staff_monthly_settlement_details` VALUES (134,111,199,'115000004',229,573,26400.00,0.00,240.00,0.00,26640.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(135,112,200,'115000004',230,576,28600.00,0.00,260.00,0.00,28860.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(136,113,205,'115000009',235,563,20000.00,10000.00,166.67,0.00,30166.67,'confirmed',0,'fixture subsidy prorated by actual service hours','2026-07-22 07:46:35'),(137,114,206,'115000009',236,555,20000.00,10000.00,166.67,0.00,30166.67,'confirmed',0,'fixture subsidy prorated by actual service hours','2026-07-22 07:46:35'),(138,115,207,'115000009',237,540,20000.00,10000.00,166.66,0.00,30166.66,'confirmed',0,'fixture subsidy prorated by actual service hours','2026-07-22 07:46:35'),(139,116,208,'115000010',238,566,132000.00,0.00,0.00,0.00,132000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(140,117,209,'115000011',239,532,54000.00,0.00,500.00,0.00,54500.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(141,118,211,'115000014',241,548,54000.00,0.00,0.00,0.00,54000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(142,119,212,'115000017',242,574,67500.00,0.00,500.00,0.00,68000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(143,120,214,'115000019',244,565,49500.00,0.00,500.00,0.00,50000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(144,121,215,'115000020',245,550,216000.00,0.00,500.00,0.00,216500.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(145,122,216,'115000022',246,541,49500.00,0.00,500.00,0.00,50000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(146,123,217,'115000024',247,575,50000.00,0.00,0.00,0.00,50000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(147,124,218,'115000026',248,531,67500.00,0.00,0.00,0.00,67500.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(148,125,219,'115000027',249,578,180000.00,0.00,0.00,0.00,180000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(149,126,225,'115000043',255,547,66000.00,0.00,0.00,0.00,66000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(150,127,226,'115000044',256,537,67500.00,0.00,0.00,0.00,67500.00,'not_applicable',0,NULL,'2026-07-22 07:46:35'),(151,128,228,'115000047',258,564,48000.00,0.00,0.00,0.00,48000.00,'not_applicable',0,NULL,'2026-07-22 07:46:35');
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
) ENGINE=InnoDB AUTO_INCREMENT=129 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_monthly_settlements`
--

LOCK TABLES `staff_monthly_settlements` WRITE;
/*!40000 ALTER TABLE `staff_monthly_settlements` DISABLE KEYS */;
INSERT INTO `staff_monthly_settlements` VALUES (111,573,'2026-06-01',1,26640.00,26640.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(112,576,'2026-07-01',1,28860.00,28860.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(113,563,'2026-06-01',1,30166.67,30166.67,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(114,555,'2026-07-01',1,30166.67,30166.67,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(115,540,'2026-07-01',1,30166.66,30166.66,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(116,566,'2026-06-01',1,132000.00,132000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(117,532,'2026-07-01',1,54500.00,54500.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(118,548,'2026-07-01',1,54000.00,54000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(119,574,'2026-06-01',1,68000.00,68000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(120,565,'2026-07-01',1,50000.00,50000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(121,550,'2026-07-01',1,216500.00,216500.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(122,541,'2026-06-01',1,50000.00,50000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(123,575,'2026-07-01',1,50000.00,50000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(124,531,'2026-07-01',1,67500.00,67500.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(125,578,'2026-06-01',1,180000.00,180000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(126,547,'2026-07-01',1,66000.00,66000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(127,537,'2026-07-01',1,67500.00,67500.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35'),(128,564,'2026-07-01',1,48000.00,48000.00,'paid','2026-07-22 00:00:00','2026-07-22 07:46:35','2026-07-22 07:46:35');
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
) ENGINE=InnoDB AUTO_INCREMENT=72 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payment_transactions`
--

LOCK TABLES `staff_payment_transactions` WRITE;
/*!40000 ALTER TABLE `staff_payment_transactions` DISABLE KEYS */;
INSERT INTO `staff_payment_transactions` VALUES (54,199,'115000004',573,'transfer','succeeded',26640.00,'2026-07-22','fake:staff-payment:229',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(55,200,'115000004',576,'transfer','succeeded',28860.00,'2026-07-22','fake:staff-payment:230',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(56,205,'115000009',563,'transfer','succeeded',20166.67,'2026-07-22','fake:staff-payment:235',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(57,206,'115000009',555,'transfer','succeeded',20166.67,'2026-07-22','fake:staff-payment:236',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(58,207,'115000009',540,'transfer','succeeded',20166.66,'2026-07-22','fake:staff-payment:237',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(59,208,'115000010',566,'transfer','succeeded',132000.00,'2026-07-22','fake:staff-payment:238',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(60,209,'115000011',532,'transfer','succeeded',54500.00,'2026-07-22','fake:staff-payment:239',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(61,211,'115000014',548,'transfer','succeeded',54000.00,'2026-07-22','fake:staff-payment:241',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(62,212,'115000017',574,'transfer','succeeded',68000.00,'2026-07-22','fake:staff-payment:242',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(63,214,'115000019',565,'transfer','succeeded',50000.00,'2026-07-22','fake:staff-payment:244',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(64,215,'115000020',550,'transfer','succeeded',216500.00,'2026-07-22','fake:staff-payment:245',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(65,216,'115000022',541,'transfer','succeeded',50000.00,'2026-07-22','fake:staff-payment:246',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(66,217,'115000024',575,'transfer','succeeded',50000.00,'2026-07-22','fake:staff-payment:247',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(67,218,'115000026',531,'transfer','succeeded',67500.00,'2026-07-22','fake:staff-payment:248',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(68,219,'115000027',578,'transfer','succeeded',180000.00,'2026-07-22','fake:staff-payment:249',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(69,225,'115000043',547,'transfer','succeeded',66000.00,'2026-07-22','fake:staff-payment:255',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(70,226,'115000044',537,'transfer','succeeded',67500.00,'2026-07-22','fake:staff-payment:256',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35'),(71,228,'115000047',564,'transfer','succeeded',48000.00,'2026-07-22','fake:staff-payment:258',NULL,'fixture completed assignment transfer projection','2026-07-22 07:46:35','2026-07-22 07:46:35');
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
) ENGINE=InnoDB AUTO_INCREMENT=230 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_payments`
--

LOCK TABLES `staff_payments` WRITE;
/*!40000 ALTER TABLE `staff_payments` DISABLE KEYS */;
INSERT INTO `staff_payments` VALUES (197,227,'115000003',565,80.00,250.00,20000.00,0.00,0.00,20000.00,0.00,'2026-08-14',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(198,228,'115000003',550,80.00,250.00,20000.00,0.00,0.00,20000.00,0.00,'2026-08-28',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(199,229,'115000004',573,96.00,275.00,26400.00,240.00,0.00,26640.00,26640.00,'2026-07-01','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(200,230,'115000004',576,104.00,275.00,28600.00,260.00,0.00,28860.00,28860.00,'2026-07-18','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(201,231,'115000007',566,135.00,275.00,37125.00,0.00,0.00,37125.00,0.00,'2026-08-22',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(202,232,'115000008',532,90.00,300.00,27000.00,333.33,0.00,27333.33,0.00,'2026-08-15',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(203,233,'115000008',572,90.00,300.00,27000.00,333.33,0.00,27333.33,0.00,'2026-08-27',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(204,234,'115000008',558,90.00,300.00,27000.00,333.34,0.00,27333.34,0.00,'2026-09-08',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(205,235,'115000009',563,80.00,250.00,20000.00,166.67,0.00,20166.67,20166.67,'2026-07-04','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(206,236,'115000009',555,80.00,250.00,20000.00,166.67,0.00,20166.67,20166.67,'2026-07-18','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(207,237,'115000009',540,80.00,250.00,20000.00,166.66,0.00,20166.66,20166.66,'2026-08-01','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(208,238,'115000010',566,480.00,275.00,132000.00,0.00,0.00,132000.00,132000.00,'2026-07-01','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(209,239,'115000011',532,180.00,300.00,54000.00,500.00,0.00,54500.00,54500.00,'2026-08-04','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(210,240,'115000013',570,200.00,275.00,55000.00,0.00,0.00,55000.00,0.00,'2026-09-01',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(211,241,'115000014',548,180.00,300.00,54000.00,0.00,0.00,54000.00,54000.00,'2026-07-21','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(212,242,'115000017',574,225.00,300.00,67500.00,500.00,0.00,68000.00,68000.00,'2026-07-05','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(213,243,'115000018',574,200.00,250.00,50000.00,500.00,2000.00,52500.00,0.00,'2026-08-29',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(214,244,'115000019',565,180.00,275.00,49500.00,500.00,0.00,50000.00,50000.00,'2026-07-22','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(215,245,'115000020',550,720.00,300.00,216000.00,500.00,0.00,216500.00,216500.00,'2026-07-24','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(216,246,'115000022',541,180.00,275.00,49500.00,500.00,0.00,50000.00,50000.00,'2026-07-04','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(217,247,'115000024',575,200.00,250.00,50000.00,0.00,0.00,50000.00,50000.00,'2026-08-05','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(218,248,'115000026',531,225.00,300.00,67500.00,0.00,0.00,67500.00,67500.00,'2026-07-18','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(219,249,'115000027',578,720.00,250.00,180000.00,0.00,0.00,180000.00,180000.00,'2026-07-01','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(220,250,'115000028',536,180.00,275.00,49500.00,0.00,0.00,49500.00,0.00,'2026-08-23',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(221,251,'115000031',557,270.00,275.00,74250.00,1000.00,0.00,75250.00,0.00,'2026-08-30',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(222,252,'115000034',573,600.00,275.00,165000.00,0.00,0.00,165000.00,0.00,'2026-08-27',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(223,253,'115000038',563,480.00,300.00,144000.00,1000.00,0.00,145000.00,0.00,'2026-08-26',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(224,254,'115000040',535,135.00,275.00,37125.00,1000.00,0.00,38125.00,0.00,'2026-08-21',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(225,255,'115000043',547,240.00,275.00,66000.00,0.00,0.00,66000.00,66000.00,'2026-07-17','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(226,256,'115000044',537,225.00,300.00,67500.00,0.00,0.00,67500.00,67500.00,'2026-07-18','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(227,257,'115000045',549,270.00,250.00,67500.00,0.00,0.00,67500.00,0.00,'2026-09-02',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(228,258,'115000047',564,160.00,300.00,48000.00,0.00,0.00,48000.00,48000.00,'2026-07-18','2026-07-22','paid','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35'),(229,259,'115000048',551,120.00,250.00,30000.00,1000.00,0.00,31000.00,0.00,'2026-08-22',NULL,'pending','fixture assignment payable','2026-07-22 07:46:35','2026-07-22 07:46:35');
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
INSERT INTO `staff_regions` VALUES (531,'北區',NULL),(531,'新竹縣',NULL),(531,'東區',NULL),(531,'苗栗縣',NULL),(531,'香山區',NULL),(532,'北區',NULL),(532,'苗栗縣',NULL),(532,'香山區',NULL),(533,'新竹縣',NULL),(534,'北區',NULL),(535,'北區',NULL),(535,'東區',NULL),(535,'苗栗縣',NULL),(536,'北區',NULL),(536,'苗栗縣',NULL),(536,'香山區',NULL),(537,'東區',NULL),(538,'新竹縣',NULL),(538,'苗栗縣',NULL),(539,'新竹縣',NULL),(540,'香山區',NULL),(541,'東區',NULL),(541,'香山區',NULL),(542,'北區',NULL),(542,'苗栗縣',NULL),(542,'香山區',NULL),(543,'北區',NULL),(543,'新竹縣',NULL),(543,'東區',NULL),(543,'苗栗縣',NULL),(543,'香山區',NULL),(544,'北區',NULL),(544,'新竹縣',NULL),(544,'東區',NULL),(544,'香山區',NULL),(545,'東區',NULL),(546,'北區',NULL),(546,'新竹縣',NULL),(547,'北區',NULL),(547,'新竹縣',NULL),(547,'東區',NULL),(547,'苗栗縣',NULL),(547,'香山區',NULL),(548,'北區',NULL),(548,'新竹縣',NULL),(548,'東區',NULL),(548,'香山區',NULL),(549,'北區',NULL),(549,'新竹縣',NULL),(549,'東區',NULL),(549,'苗栗縣',NULL),(549,'香山區',NULL),(550,'北區',NULL),(550,'新竹縣',NULL),(550,'苗栗縣',NULL),(551,'北區',NULL),(551,'新竹縣',NULL),(551,'東區',NULL),(551,'苗栗縣',NULL),(551,'香山區',NULL),(552,'新竹縣',NULL),(552,'東區',NULL),(552,'苗栗縣',NULL),(552,'香山區',NULL),(553,'新竹縣',NULL),(553,'東區',NULL),(553,'香山區',NULL),(554,'北區',NULL),(554,'新竹縣',NULL),(554,'苗栗縣',NULL),(554,'香山區',NULL),(555,'北區',NULL),(555,'苗栗縣',NULL),(555,'香山區',NULL),(556,'北區',NULL),(556,'新竹縣',NULL),(556,'苗栗縣',NULL),(556,'香山區',NULL),(557,'北區',NULL),(557,'香山區',NULL),(558,'新竹縣',NULL),(558,'東區',NULL),(558,'苗栗縣',NULL),(558,'香山區',NULL),(559,'北區',NULL),(559,'新竹縣',NULL),(559,'東區',NULL),(559,'苗栗縣',NULL),(559,'香山區',NULL),(560,'北區',NULL),(560,'新竹縣',NULL),(560,'東區',NULL),(560,'苗栗縣',NULL),(560,'香山區',NULL),(561,'苗栗縣',NULL),(562,'香山區',NULL),(563,'北區',NULL),(563,'新竹縣',NULL),(563,'東區',NULL),(563,'苗栗縣',NULL),(563,'香山區',NULL),(564,'北區',NULL),(564,'新竹縣',NULL),(564,'東區',NULL),(564,'苗栗縣',NULL),(565,'北區',NULL),(565,'新竹縣',NULL),(565,'東區',NULL),(565,'苗栗縣',NULL),(565,'香山區',NULL),(566,'北區',NULL),(566,'新竹縣',NULL),(566,'東區',NULL),(566,'苗栗縣',NULL),(566,'香山區',NULL),(567,'北區',NULL),(567,'苗栗縣',NULL),(568,'北區',NULL),(568,'東區',NULL),(568,'苗栗縣',NULL),(569,'北區',NULL),(570,'新竹縣',NULL),(570,'東區',NULL),(571,'北區',NULL),(571,'東區',NULL),(572,'東區',NULL),(573,'新竹縣',NULL),(574,'北區',NULL),(574,'香山區',NULL),(575,'北區',NULL),(575,'新竹縣',NULL),(575,'苗栗縣',NULL),(575,'香山區',NULL),(576,'北區',NULL),(576,'新竹縣',NULL),(576,'香山區',NULL),(577,'北區',NULL),(577,'新竹縣',NULL),(577,'東區',NULL),(577,'苗栗縣',NULL),(578,'苗栗縣',NULL),(579,'新竹縣',NULL),(579,'東區',NULL),(579,'苗栗縣',NULL),(579,'香山區',NULL),(580,'北區',NULL),(580,'新竹縣',NULL),(580,'東區',NULL),(580,'香山區',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=11955 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_schedule`
--

LOCK TABLES `staff_schedule` WRITE;
/*!40000 ALTER TABLE `staff_schedule` DISABLE KEYS */;
INSERT INTO `staff_schedule` VALUES (10489,'115000003',565,227,1,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10490,'115000003',565,227,1,'2026-07-18',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10491,'115000003',565,227,1,'2026-07-19',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10492,'115000003',565,227,1,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10493,'115000003',565,227,1,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10494,'115000003',565,227,1,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10495,'115000003',565,227,1,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10496,'115000003',565,227,1,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10497,'115000003',565,227,1,'2026-07-25',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10498,'115000003',565,227,1,'2026-07-26',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10499,'115000003',565,227,1,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10500,'115000003',565,227,1,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10501,'115000003',565,227,1,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10502,'115000003',565,227,1,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10503,'115000003',550,228,1,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10504,'115000003',550,228,1,'2026-08-01',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10505,'115000003',550,228,1,'2026-08-02',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10506,'115000003',550,228,1,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10507,'115000003',550,228,1,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10508,'115000003',550,228,1,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10509,'115000003',550,228,1,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10510,'115000003',550,228,1,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10511,'115000003',550,228,1,'2026-08-08',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10512,'115000003',550,228,1,'2026-08-09',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10513,'115000003',550,228,1,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10514,'115000003',550,228,1,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10515,'115000003',550,228,1,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10516,'115000003',550,228,1,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10517,'115000004',573,229,2,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10518,'115000004',573,229,2,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10519,'115000004',573,229,2,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10520,'115000004',573,229,2,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10521,'115000004',573,229,2,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10522,'115000004',573,229,2,'2026-06-06',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10523,'115000004',573,229,2,'2026-06-07',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10524,'115000004',573,229,2,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10525,'115000004',573,229,2,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10526,'115000004',573,229,2,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10527,'115000004',573,229,2,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10528,'115000004',573,229,2,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10529,'115000004',573,229,2,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10530,'115000004',573,229,2,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10531,'115000004',573,229,2,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10532,'115000004',573,229,2,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10533,'115000004',576,230,2,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10534,'115000004',576,230,2,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10535,'115000004',576,230,2,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10536,'115000004',576,230,2,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10537,'115000004',576,230,2,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10538,'115000004',576,230,2,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10539,'115000004',576,230,2,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10540,'115000004',576,230,2,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10541,'115000004',576,230,2,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10542,'115000004',576,230,2,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10543,'115000004',576,230,2,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10544,'115000004',576,230,2,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10545,'115000004',576,230,2,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10546,'115000004',576,230,2,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10547,'115000004',576,230,2,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10548,'115000004',576,230,2,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10549,'115000004',576,230,2,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10550,'115000007',566,231,3,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10551,'115000007',566,231,3,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10552,'115000007',566,231,3,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10553,'115000007',566,231,3,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10554,'115000007',566,231,3,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10555,'115000007',566,231,3,'2026-07-25',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10556,'115000007',566,231,3,'2026-07-26',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10557,'115000007',566,231,3,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10558,'115000007',566,231,3,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10559,'115000007',566,231,3,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10560,'115000007',566,231,3,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10561,'115000007',566,231,3,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10562,'115000007',566,231,3,'2026-08-01',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10563,'115000007',566,231,3,'2026-08-02',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10564,'115000007',566,231,3,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10565,'115000007',566,231,3,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10566,'115000007',566,231,3,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10567,'115000007',566,231,3,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10568,'115000007',566,231,3,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10569,'115000008',532,232,4,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10570,'115000008',532,232,4,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10571,'115000008',532,232,4,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10572,'115000008',532,232,4,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10573,'115000008',532,232,4,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10574,'115000008',532,232,4,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10575,'115000008',532,232,4,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10576,'115000008',532,232,4,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10577,'115000008',532,232,4,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10578,'115000008',532,232,4,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10579,'115000008',532,232,4,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10580,'115000008',572,233,4,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10581,'115000008',572,233,4,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10582,'115000008',572,233,4,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10583,'115000008',572,233,4,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10584,'115000008',572,233,4,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10585,'115000008',572,233,4,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10586,'115000008',572,233,4,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10587,'115000008',572,233,4,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10588,'115000008',572,233,4,'2026-08-09',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10589,'115000008',572,233,4,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10590,'115000008',572,233,4,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10591,'115000008',572,233,4,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10592,'115000008',558,234,4,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10593,'115000008',558,234,4,'2026-08-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10594,'115000008',558,234,4,'2026-08-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10595,'115000008',558,234,4,'2026-08-16',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10596,'115000008',558,234,4,'2026-08-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10597,'115000008',558,234,4,'2026-08-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10598,'115000008',558,234,4,'2026-08-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10599,'115000008',558,234,4,'2026-08-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10600,'115000008',558,234,4,'2026-08-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10601,'115000008',558,234,4,'2026-08-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10602,'115000008',558,234,4,'2026-08-23',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10603,'115000008',558,234,4,'2026-08-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10604,'115000009',563,235,5,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10605,'115000009',563,235,5,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10606,'115000009',563,235,5,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10607,'115000009',563,235,5,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10608,'115000009',563,235,5,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10609,'115000009',563,235,5,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10610,'115000009',563,235,5,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10611,'115000009',563,235,5,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10612,'115000009',563,235,5,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10613,'115000009',563,235,5,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10614,'115000009',563,235,5,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10615,'115000009',563,235,5,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10616,'115000009',555,236,5,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10617,'115000009',555,236,5,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10618,'115000009',555,236,5,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10619,'115000009',555,236,5,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10620,'115000009',555,236,5,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10621,'115000009',555,236,5,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10622,'115000009',555,236,5,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10623,'115000009',555,236,5,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10624,'115000009',555,236,5,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10625,'115000009',555,236,5,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10626,'115000009',555,236,5,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10627,'115000009',555,236,5,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10628,'115000009',555,236,5,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10629,'115000009',555,236,5,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10630,'115000009',540,237,5,'2026-07-04',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10631,'115000009',540,237,5,'2026-07-05',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10632,'115000009',540,237,5,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10633,'115000009',540,237,5,'2026-07-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10634,'115000009',540,237,5,'2026-07-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10635,'115000009',540,237,5,'2026-07-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10636,'115000009',540,237,5,'2026-07-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10637,'115000009',540,237,5,'2026-07-11',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10638,'115000009',540,237,5,'2026-07-12',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10639,'115000009',540,237,5,'2026-07-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10640,'115000009',540,237,5,'2026-07-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10641,'115000009',540,237,5,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10642,'115000009',540,237,5,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10643,'115000009',540,237,5,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10644,'115000010',566,238,6,'2026-05-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10645,'115000010',566,238,6,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10646,'115000010',566,238,6,'2026-05-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10647,'115000010',566,238,6,'2026-05-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10648,'115000010',566,238,6,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10649,'115000010',566,238,6,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10650,'115000010',566,238,6,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10651,'115000010',566,238,6,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10652,'115000010',566,238,6,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10653,'115000010',566,238,6,'2026-06-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10654,'115000010',566,238,6,'2026-06-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10655,'115000010',566,238,6,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10656,'115000010',566,238,6,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10657,'115000010',566,238,6,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10658,'115000010',566,238,6,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10659,'115000010',566,238,6,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10660,'115000010',566,238,6,'2026-06-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10661,'115000010',566,238,6,'2026-06-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10662,'115000010',566,238,6,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10663,'115000010',566,238,6,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10664,'115000011',532,239,7,'2026-06-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10665,'115000011',532,239,7,'2026-06-28',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10666,'115000011',532,239,7,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10667,'115000011',532,239,7,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10668,'115000011',532,239,7,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10669,'115000011',532,239,7,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10670,'115000011',532,239,7,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10671,'115000011',532,239,7,'2026-07-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10672,'115000011',532,239,7,'2026-07-05',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10673,'115000011',532,239,7,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10674,'115000011',532,239,7,'2026-07-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10675,'115000011',532,239,7,'2026-07-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10676,'115000011',532,239,7,'2026-07-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10677,'115000011',532,239,7,'2026-07-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10678,'115000011',532,239,7,'2026-07-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10679,'115000011',532,239,7,'2026-07-12',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10680,'115000011',532,239,7,'2026-07-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10681,'115000011',532,239,7,'2026-07-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10682,'115000011',532,239,7,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10683,'115000011',532,239,7,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10684,'115000011',532,239,7,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10685,'115000011',532,239,7,'2026-07-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10686,'115000011',532,239,7,'2026-07-19',0,0,1,'週休1日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10687,'115000011',532,239,7,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10688,'115000013',570,240,8,'2026-07-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10689,'115000013',570,240,8,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10690,'115000013',570,240,8,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10691,'115000013',570,240,8,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10692,'115000013',570,240,8,'2026-07-18',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10693,'115000013',570,240,8,'2026-07-19',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10694,'115000013',570,240,8,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10695,'115000013',570,240,8,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10696,'115000013',570,240,8,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10697,'115000013',570,240,8,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10698,'115000013',570,240,8,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10699,'115000013',570,240,8,'2026-07-25',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10700,'115000013',570,240,8,'2026-07-26',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10701,'115000013',570,240,8,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10702,'115000013',570,240,8,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10703,'115000013',570,240,8,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10704,'115000013',570,240,8,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10705,'115000013',570,240,8,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10706,'115000013',570,240,8,'2026-08-01',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10707,'115000013',570,240,8,'2026-08-02',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10708,'115000013',570,240,8,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10709,'115000013',570,240,8,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10710,'115000013',570,240,8,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10711,'115000013',570,240,8,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10712,'115000013',570,240,8,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10713,'115000013',570,240,8,'2026-08-08',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10714,'115000013',570,240,8,'2026-08-09',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10715,'115000013',570,240,8,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10716,'115000013',570,240,8,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10717,'115000013',570,240,8,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10718,'115000013',570,240,8,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10719,'115000013',570,240,8,'2026-08-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10720,'115000013',570,240,8,'2026-08-15',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10721,'115000013',570,240,8,'2026-08-16',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10722,'115000013',570,240,8,'2026-08-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10723,'115000014',548,241,9,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10724,'115000014',548,241,9,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10725,'115000014',548,241,9,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10726,'115000014',548,241,9,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10727,'115000014',548,241,9,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10728,'115000014',548,241,9,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10729,'115000014',548,241,9,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10730,'115000014',548,241,9,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10731,'115000014',548,241,9,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10732,'115000014',548,241,9,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:33','2026-08-02 16:23:56'),(10733,'115000014',548,241,9,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10734,'115000014',548,241,9,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10735,'115000014',548,241,9,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10736,'115000014',548,241,9,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10737,'115000014',548,241,9,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10738,'115000014',548,241,9,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10739,'115000014',548,241,9,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10740,'115000014',548,241,9,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10741,'115000014',548,241,9,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10742,'115000014',548,241,9,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10743,'115000014',548,241,9,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10744,'115000014',548,241,9,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10745,'115000014',548,241,9,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10746,'115000014',548,241,9,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10747,'115000014',548,241,9,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10748,'115000014',548,241,9,'2026-07-04',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10749,'115000014',548,241,9,'2026-07-05',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10750,'115000014',548,241,9,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10751,'115000017',574,242,10,'2026-05-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10752,'115000017',574,242,10,'2026-05-24',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10753,'115000017',574,242,10,'2026-05-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10754,'115000017',574,242,10,'2026-05-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10755,'115000017',574,242,10,'2026-05-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10756,'115000017',574,242,10,'2026-05-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10757,'115000017',574,242,10,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10758,'115000017',574,242,10,'2026-05-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10759,'115000017',574,242,10,'2026-05-31',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10760,'115000017',574,242,10,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10761,'115000017',574,242,10,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10762,'115000017',574,242,10,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10763,'115000017',574,242,10,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10764,'115000017',574,242,10,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10765,'115000017',574,242,10,'2026-06-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10766,'115000017',574,242,10,'2026-06-07',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10767,'115000017',574,242,10,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10768,'115000017',574,242,10,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10769,'115000017',574,242,10,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10770,'115000017',574,242,10,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10771,'115000017',574,242,10,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10772,'115000017',574,242,10,'2026-06-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10773,'115000017',574,242,10,'2026-06-14',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10774,'115000017',574,242,10,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10775,'115000017',574,242,10,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10776,'115000017',574,242,10,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10777,'115000017',574,242,10,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10778,'115000017',574,242,10,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10779,'115000017',574,242,10,'2026-06-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10780,'115000018',574,243,11,'2026-07-17',1,1,1,'boundary: double-pay service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10781,'115000018',574,243,11,'2026-07-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10782,'115000018',574,243,11,'2026-07-19',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10783,'115000018',574,243,11,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10784,'115000018',574,243,11,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10785,'115000018',574,243,11,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10786,'115000018',574,243,11,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10787,'115000018',574,243,11,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10788,'115000018',574,243,11,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10789,'115000018',574,243,11,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10790,'115000018',574,243,11,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10791,'115000018',574,243,11,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10792,'115000018',574,243,11,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10793,'115000018',574,243,11,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10794,'115000018',574,243,11,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10795,'115000018',574,243,11,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10796,'115000018',574,243,11,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10797,'115000018',574,243,11,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10798,'115000018',574,243,11,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10799,'115000018',574,243,11,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10800,'115000018',574,243,11,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10801,'115000018',574,243,11,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10802,'115000018',574,243,11,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10803,'115000018',574,243,11,'2026-08-09',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10804,'115000018',574,243,11,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10805,'115000018',574,243,11,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10806,'115000018',574,243,11,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10807,'115000018',574,243,11,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10808,'115000018',574,243,11,'2026-08-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10809,'115000019',565,244,12,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10810,'115000019',565,244,12,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10811,'115000019',565,244,12,'2026-06-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10812,'115000019',565,244,12,'2026-06-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10813,'115000019',565,244,12,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10814,'115000019',565,244,12,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10815,'115000019',565,244,12,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10816,'115000019',565,244,12,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10817,'115000019',565,244,12,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10818,'115000019',565,244,12,'2026-06-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10819,'115000019',565,244,12,'2026-06-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10820,'115000019',565,244,12,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10821,'115000019',565,244,12,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10822,'115000019',565,244,12,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10823,'115000019',565,244,12,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10824,'115000019',565,244,12,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10825,'115000019',565,244,12,'2026-07-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10826,'115000019',565,244,12,'2026-07-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10827,'115000019',565,244,12,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10828,'115000019',565,244,12,'2026-07-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10829,'115000020',550,245,13,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10830,'115000020',550,245,13,'2026-05-30',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10831,'115000020',550,245,13,'2026-05-31',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10832,'115000020',550,245,13,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10833,'115000020',550,245,13,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10834,'115000020',550,245,13,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10835,'115000020',550,245,13,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10836,'115000020',550,245,13,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10837,'115000020',550,245,13,'2026-06-06',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10838,'115000020',550,245,13,'2026-06-07',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10839,'115000020',550,245,13,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10840,'115000020',550,245,13,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10841,'115000020',550,245,13,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10842,'115000020',550,245,13,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10843,'115000020',550,245,13,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10844,'115000020',550,245,13,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10845,'115000020',550,245,13,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10846,'115000020',550,245,13,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10847,'115000020',550,245,13,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10848,'115000020',550,245,13,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10849,'115000020',550,245,13,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10850,'115000020',550,245,13,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10851,'115000020',550,245,13,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10852,'115000020',550,245,13,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10853,'115000020',550,245,13,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10854,'115000020',550,245,13,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10855,'115000020',550,245,13,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10856,'115000020',550,245,13,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10857,'115000020',550,245,13,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10858,'115000020',550,245,13,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10859,'115000020',550,245,13,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10860,'115000020',550,245,13,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10861,'115000020',550,245,13,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10862,'115000020',550,245,13,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10863,'115000020',550,245,13,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10864,'115000020',550,245,13,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10865,'115000020',550,245,13,'2026-07-04',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10866,'115000020',550,245,13,'2026-07-05',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10867,'115000020',550,245,13,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10868,'115000020',550,245,13,'2026-07-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10869,'115000020',550,245,13,'2026-07-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10870,'115000020',550,245,13,'2026-07-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10871,'115000022',541,246,14,'2026-05-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10872,'115000022',541,246,14,'2026-05-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10873,'115000022',541,246,14,'2026-05-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10874,'115000022',541,246,14,'2026-05-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10875,'115000022',541,246,14,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10876,'115000022',541,246,14,'2026-05-30',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10877,'115000022',541,246,14,'2026-05-31',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10878,'115000022',541,246,14,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10879,'115000022',541,246,14,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10880,'115000022',541,246,14,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10881,'115000022',541,246,14,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10882,'115000022',541,246,14,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10883,'115000022',541,246,14,'2026-06-06',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10884,'115000022',541,246,14,'2026-06-07',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10885,'115000022',541,246,14,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10886,'115000022',541,246,14,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10887,'115000022',541,246,14,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10888,'115000022',541,246,14,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10889,'115000022',541,246,14,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10890,'115000022',541,246,14,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10891,'115000022',541,246,14,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10892,'115000022',541,246,14,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10893,'115000022',541,246,14,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10894,'115000022',541,246,14,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10895,'115000022',541,246,14,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10896,'115000022',541,246,14,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10897,'115000024',575,247,15,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10898,'115000024',575,247,15,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10899,'115000024',575,247,15,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10900,'115000024',575,247,15,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10901,'115000024',575,247,15,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10902,'115000024',575,247,15,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10903,'115000024',575,247,15,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10904,'115000024',575,247,15,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10905,'115000024',575,247,15,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10906,'115000024',575,247,15,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10907,'115000024',575,247,15,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10908,'115000024',575,247,15,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10909,'115000024',575,247,15,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10910,'115000024',575,247,15,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10911,'115000024',575,247,15,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10912,'115000024',575,247,15,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10913,'115000024',575,247,15,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10914,'115000024',575,247,15,'2026-07-04',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10915,'115000024',575,247,15,'2026-07-05',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10916,'115000024',575,247,15,'2026-07-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10917,'115000024',575,247,15,'2026-07-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10918,'115000024',575,247,15,'2026-07-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10919,'115000024',575,247,15,'2026-07-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10920,'115000024',575,247,15,'2026-07-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10921,'115000024',575,247,15,'2026-07-11',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10922,'115000024',575,247,15,'2026-07-12',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10923,'115000024',575,247,15,'2026-07-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10924,'115000024',575,247,15,'2026-07-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10925,'115000024',575,247,15,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10926,'115000024',575,247,15,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10927,'115000024',575,247,15,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10928,'115000024',575,247,15,'2026-07-18',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10929,'115000024',575,247,15,'2026-07-19',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10930,'115000024',575,247,15,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10931,'115000024',575,247,15,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10932,'115000026',531,248,16,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10933,'115000026',531,248,16,'2026-06-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10934,'115000026',531,248,16,'2026-06-07',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10935,'115000026',531,248,16,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10936,'115000026',531,248,16,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10937,'115000026',531,248,16,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10938,'115000026',531,248,16,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10939,'115000026',531,248,16,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10940,'115000026',531,248,16,'2026-06-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10941,'115000026',531,248,16,'2026-06-14',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10942,'115000026',531,248,16,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10943,'115000026',531,248,16,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10944,'115000026',531,248,16,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10945,'115000026',531,248,16,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10946,'115000026',531,248,16,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10947,'115000026',531,248,16,'2026-06-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10948,'115000026',531,248,16,'2026-06-21',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10949,'115000026',531,248,16,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10950,'115000026',531,248,16,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10951,'115000026',531,248,16,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10952,'115000026',531,248,16,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10953,'115000026',531,248,16,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10954,'115000026',531,248,16,'2026-06-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10955,'115000026',531,248,16,'2026-06-28',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10956,'115000026',531,248,16,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10957,'115000026',531,248,16,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10958,'115000026',531,248,16,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10959,'115000026',531,248,16,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10960,'115000026',531,248,16,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10961,'115000027',578,249,17,'2026-05-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10962,'115000027',578,249,17,'2026-05-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10963,'115000027',578,249,17,'2026-05-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10964,'115000027',578,249,17,'2026-05-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10965,'115000027',578,249,17,'2026-05-17',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10966,'115000027',578,249,17,'2026-05-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10967,'115000027',578,249,17,'2026-05-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10968,'115000027',578,249,17,'2026-05-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10969,'115000027',578,249,17,'2026-05-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10970,'115000027',578,249,17,'2026-05-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10971,'115000027',578,249,17,'2026-05-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10972,'115000027',578,249,17,'2026-05-24',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10973,'115000027',578,249,17,'2026-05-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10974,'115000027',578,249,17,'2026-05-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10975,'115000027',578,249,17,'2026-05-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10976,'115000027',578,249,17,'2026-05-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10977,'115000027',578,249,17,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10978,'115000027',578,249,17,'2026-05-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10979,'115000027',578,249,17,'2026-05-31',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10980,'115000027',578,249,17,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10981,'115000027',578,249,17,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10982,'115000027',578,249,17,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10983,'115000027',578,249,17,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10984,'115000027',578,249,17,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10985,'115000027',578,249,17,'2026-06-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10986,'115000027',578,249,17,'2026-06-07',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10987,'115000027',578,249,17,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10988,'115000027',578,249,17,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10989,'115000027',578,249,17,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10990,'115000027',578,249,17,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10991,'115000027',578,249,17,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10992,'115000027',578,249,17,'2026-06-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10993,'115000027',578,249,17,'2026-06-14',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10994,'115000027',578,249,17,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10995,'115000027',578,249,17,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10996,'115000028',536,250,18,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10997,'115000028',536,250,18,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10998,'115000028',536,250,18,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(10999,'115000028',536,250,18,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11000,'115000028',536,250,18,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11001,'115000028',536,250,18,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11002,'115000028',536,250,18,'2026-07-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11003,'115000028',536,250,18,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11004,'115000028',536,250,18,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11005,'115000028',536,250,18,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11006,'115000028',536,250,18,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11007,'115000028',536,250,18,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11008,'115000028',536,250,18,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11009,'115000028',536,250,18,'2026-08-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11010,'115000028',536,250,18,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11011,'115000028',536,250,18,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11012,'115000028',536,250,18,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11013,'115000028',536,250,18,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11014,'115000028',536,250,18,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11015,'115000028',536,250,18,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11016,'115000031',557,251,19,'2026-07-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11017,'115000031',557,251,19,'2026-07-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11018,'115000031',557,251,19,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11019,'115000031',557,251,19,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11020,'115000031',557,251,19,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11021,'115000031',557,251,19,'2026-07-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11022,'115000031',557,251,19,'2026-07-19',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11023,'115000031',557,251,19,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11024,'115000031',557,251,19,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11025,'115000031',557,251,19,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11026,'115000031',557,251,19,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11027,'115000031',557,251,19,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11028,'115000031',557,251,19,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11029,'115000031',557,251,19,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11030,'115000031',557,251,19,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11031,'115000031',557,251,19,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11032,'115000031',557,251,19,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11033,'115000031',557,251,19,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11034,'115000031',557,251,19,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11035,'115000031',557,251,19,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11036,'115000031',557,251,19,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11037,'115000031',557,251,19,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11038,'115000031',557,251,19,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11039,'115000031',557,251,19,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11040,'115000031',557,251,19,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11041,'115000031',557,251,19,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11042,'115000031',557,251,19,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11043,'115000031',557,251,19,'2026-08-09',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11044,'115000031',557,251,19,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11045,'115000031',557,251,19,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11046,'115000031',557,251,19,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11047,'115000031',557,251,19,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11048,'115000031',557,251,19,'2026-08-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11049,'115000031',557,251,19,'2026-08-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11050,'115000034',573,252,20,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11051,'115000034',573,252,20,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11052,'115000034',573,252,20,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11053,'115000034',573,252,20,'2026-07-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11054,'115000034',573,252,20,'2026-07-19',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11055,'115000034',573,252,20,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11056,'115000034',573,252,20,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11057,'115000034',573,252,20,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11058,'115000034',573,252,20,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11059,'115000034',573,252,20,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11060,'115000034',573,252,20,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11061,'115000034',573,252,20,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11062,'115000034',573,252,20,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11063,'115000034',573,252,20,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11064,'115000034',573,252,20,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11065,'115000034',573,252,20,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11066,'115000034',573,252,20,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11067,'115000034',573,252,20,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11068,'115000034',573,252,20,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11069,'115000034',573,252,20,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11070,'115000034',573,252,20,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11071,'115000034',573,252,20,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11072,'115000034',573,252,20,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11073,'115000034',573,252,20,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11074,'115000034',573,252,20,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11075,'115000034',573,252,20,'2026-08-09',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11076,'115000034',573,252,20,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11077,'115000034',573,252,20,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11078,'115000034',573,252,20,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11079,'115000038',563,253,21,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11080,'115000038',563,253,21,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11081,'115000038',563,253,21,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11082,'115000038',563,253,21,'2026-07-18',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11083,'115000038',563,253,21,'2026-07-19',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11084,'115000038',563,253,21,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11085,'115000038',563,253,21,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11086,'115000038',563,253,21,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11087,'115000038',563,253,21,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11088,'115000038',563,253,21,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11089,'115000038',563,253,21,'2026-07-25',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11090,'115000038',563,253,21,'2026-07-26',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11091,'115000038',563,253,21,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11092,'115000038',563,253,21,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11093,'115000038',563,253,21,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11094,'115000038',563,253,21,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11095,'115000038',563,253,21,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11096,'115000038',563,253,21,'2026-08-01',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11097,'115000038',563,253,21,'2026-08-02',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11098,'115000038',563,253,21,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11099,'115000038',563,253,21,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11100,'115000038',563,253,21,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11101,'115000038',563,253,21,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11102,'115000038',563,253,21,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11103,'115000038',563,253,21,'2026-08-08',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11104,'115000038',563,253,21,'2026-08-09',0,0,1,'週休2日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11105,'115000038',563,253,21,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11106,'115000038',563,253,21,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11107,'115000040',535,254,22,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11108,'115000040',535,254,22,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11109,'115000040',535,254,22,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11110,'115000040',535,254,22,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11111,'115000040',535,254,22,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11112,'115000040',535,254,22,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11113,'115000040',535,254,22,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11114,'115000040',535,254,22,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11115,'115000040',535,254,22,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11116,'115000040',535,254,22,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11117,'115000040',535,254,22,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11118,'115000040',535,254,22,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11119,'115000040',535,254,22,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11120,'115000040',535,254,22,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11121,'115000040',535,254,22,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11122,'115000040',535,254,22,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11123,'115000040',535,254,22,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:34','2026-08-02 16:23:56'),(11124,'115000043',547,255,23,'2026-05-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11125,'115000043',547,255,23,'2026-05-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11126,'115000043',547,255,23,'2026-05-31',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11127,'115000043',547,255,23,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11128,'115000043',547,255,23,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11129,'115000043',547,255,23,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11130,'115000043',547,255,23,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11131,'115000043',547,255,23,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11132,'115000043',547,255,23,'2026-06-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11133,'115000043',547,255,23,'2026-06-07',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11134,'115000043',547,255,23,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11135,'115000043',547,255,23,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11136,'115000043',547,255,23,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11137,'115000043',547,255,23,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11138,'115000043',547,255,23,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11139,'115000043',547,255,23,'2026-06-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11140,'115000043',547,255,23,'2026-06-14',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11141,'115000043',547,255,23,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11142,'115000043',547,255,23,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11143,'115000043',547,255,23,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11144,'115000043',547,255,23,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11145,'115000043',547,255,23,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11146,'115000043',547,255,23,'2026-06-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11147,'115000043',547,255,23,'2026-06-21',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11148,'115000043',547,255,23,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11149,'115000043',547,255,23,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11150,'115000043',547,255,23,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11151,'115000043',547,255,23,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11152,'115000043',547,255,23,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11153,'115000043',547,255,23,'2026-06-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11154,'115000043',547,255,23,'2026-06-28',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11155,'115000043',547,255,23,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11156,'115000043',547,255,23,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11157,'115000043',547,255,23,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11158,'115000043',547,255,23,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11159,'115000044',537,256,24,'2026-06-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11160,'115000044',537,256,24,'2026-06-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11161,'115000044',537,256,24,'2026-06-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11162,'115000044',537,256,24,'2026-06-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11163,'115000044',537,256,24,'2026-06-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11164,'115000044',537,256,24,'2026-06-06',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11165,'115000044',537,256,24,'2026-06-07',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11166,'115000044',537,256,24,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11167,'115000044',537,256,24,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11168,'115000044',537,256,24,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11169,'115000044',537,256,24,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11170,'115000044',537,256,24,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11171,'115000044',537,256,24,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11172,'115000044',537,256,24,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11173,'115000044',537,256,24,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11174,'115000044',537,256,24,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11175,'115000044',537,256,24,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11176,'115000044',537,256,24,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11177,'115000044',537,256,24,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11178,'115000044',537,256,24,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11179,'115000044',537,256,24,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11180,'115000044',537,256,24,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11181,'115000044',537,256,24,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11182,'115000044',537,256,24,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11183,'115000044',537,256,24,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11184,'115000044',537,256,24,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11185,'115000044',537,256,24,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11186,'115000044',537,256,24,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11187,'115000044',537,256,24,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11188,'115000044',537,256,24,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11189,'115000044',537,256,24,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11190,'115000044',537,256,24,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11191,'115000044',537,256,24,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11192,'115000045',549,257,25,'2026-07-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11193,'115000045',549,257,25,'2026-07-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11194,'115000045',549,257,25,'2026-07-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11195,'115000045',549,257,25,'2026-07-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11196,'115000045',549,257,25,'2026-07-19',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11197,'115000045',549,257,25,'2026-07-20',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11198,'115000045',549,257,25,'2026-07-21',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11199,'115000045',549,257,25,'2026-07-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11200,'115000045',549,257,25,'2026-07-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11201,'115000045',549,257,25,'2026-07-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11202,'115000045',549,257,25,'2026-07-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11203,'115000045',549,257,25,'2026-07-26',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11204,'115000045',549,257,25,'2026-07-27',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11205,'115000045',549,257,25,'2026-07-28',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11206,'115000045',549,257,25,'2026-07-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11207,'115000045',549,257,25,'2026-07-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11208,'115000045',549,257,25,'2026-07-31',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11209,'115000045',549,257,25,'2026-08-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11210,'115000045',549,257,25,'2026-08-02',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11211,'115000045',549,257,25,'2026-08-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11212,'115000045',549,257,25,'2026-08-04',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11213,'115000045',549,257,25,'2026-08-05',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11214,'115000045',549,257,25,'2026-08-06',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11215,'115000045',549,257,25,'2026-08-07',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11216,'115000045',549,257,25,'2026-08-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11217,'115000045',549,257,25,'2026-08-09',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11218,'115000045',549,257,25,'2026-08-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11219,'115000045',549,257,25,'2026-08-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11220,'115000045',549,257,25,'2026-08-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11221,'115000045',549,257,25,'2026-08-13',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11222,'115000045',549,257,25,'2026-08-14',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11223,'115000045',549,257,25,'2026-08-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11224,'115000045',549,257,25,'2026-08-16',0,0,1,'週休1日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11225,'115000045',549,257,25,'2026-08-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11226,'115000045',549,257,25,'2026-08-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11227,'115000047',564,258,26,'2026-06-08',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11228,'115000047',564,258,26,'2026-06-09',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11229,'115000047',564,258,26,'2026-06-10',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11230,'115000047',564,258,26,'2026-06-11',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11231,'115000047',564,258,26,'2026-06-12',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11232,'115000047',564,258,26,'2026-06-13',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11233,'115000047',564,258,26,'2026-06-14',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11234,'115000047',564,258,26,'2026-06-15',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11235,'115000047',564,258,26,'2026-06-16',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11236,'115000047',564,258,26,'2026-06-17',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11237,'115000047',564,258,26,'2026-06-18',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11238,'115000047',564,258,26,'2026-06-19',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11239,'115000047',564,258,26,'2026-06-20',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11240,'115000047',564,258,26,'2026-06-21',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11241,'115000047',564,258,26,'2026-06-22',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11242,'115000047',564,258,26,'2026-06-23',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11243,'115000047',564,258,26,'2026-06-24',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11244,'115000047',564,258,26,'2026-06-25',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11245,'115000047',564,258,26,'2026-06-26',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11246,'115000047',564,258,26,'2026-06-27',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11247,'115000047',564,258,26,'2026-06-28',0,0,1,'週休2日固定休假','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11248,'115000047',564,258,26,'2026-06-29',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11249,'115000047',564,258,26,'2026-06-30',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11250,'115000047',564,258,26,'2026-07-01',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11251,'115000047',564,258,26,'2026-07-02',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56'),(11252,'115000047',564,258,26,'2026-07-03',1,0,1,'assignment-owned service day','2026-07-22 07:46:35','2026-08-02 16:23:56');
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
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_schedule_review` (`schedule_id`),
  KEY `idx_schedule_assignment_review_status` (`review_status`,`created_at`),
  KEY `fk_schedule_assignment_review_assignment` (`resolved_assignment_id`),
  CONSTRAINT `fk_schedule_assignment_review_assignment` FOREIGN KEY (`resolved_assignment_id`) REFERENCES `case_staff_assignments` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_schedule_assignment_review_schedule` FOREIGN KEY (`schedule_id`) REFERENCES `staff_schedule` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_schedule_assignment_review_resolution` CHECK ((((`review_status` = _utf8mb4'review_required') and (`resolved_assignment_id` is null) and (`resolved_at` is null)) or ((`review_status` = _utf8mb4'resolved') and (`resolved_assignment_id` is not null) and (`resolved_at` is not null))))
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
INSERT INTO `staff_time_slots` VALUES (531,'24小時',NULL),(531,'4小時(上午8:30-12:30)',NULL),(531,'8小時',NULL),(532,'24小時',NULL),(532,'4小時(上午8:30-12:30)',NULL),(532,'4小時(下午13:00-17:00)',NULL),(533,'24小時',NULL),(533,'4小時(上午8:30-12:30)',NULL),(533,'4小時(下午13:00-17:00)',NULL),(533,'8小時',NULL),(534,'24小時',NULL),(535,'24小時',NULL),(535,'4小時(下午13:00-17:00)',NULL),(536,'4小時(上午8:30-12:30)',NULL),(536,'4小時(下午13:00-17:00)',NULL),(537,'24小時',NULL),(537,'4小時(上午8:30-12:30)',NULL),(537,'4小時(下午13:00-17:00)',NULL),(537,'8小時',NULL),(538,'24小時',NULL),(539,'4小時(上午8:30-12:30)',NULL),(539,'4小時(下午13:00-17:00)',NULL),(539,'8小時',NULL),(540,'4小時(上午8:30-12:30)',NULL),(540,'4小時(下午13:00-17:00)',NULL),(540,'8小時',NULL),(541,'24小時',NULL),(541,'4小時(下午13:00-17:00)',NULL),(542,'24小時',NULL),(542,'8小時',NULL),(543,'4小時(上午8:30-12:30)',NULL),(543,'4小時(下午13:00-17:00)',NULL),(544,'4小時(上午8:30-12:30)',NULL),(544,'8小時',NULL),(545,'4小時(上午8:30-12:30)',NULL),(546,'24小時',NULL),(546,'4小時(上午8:30-12:30)',NULL),(546,'4小時(下午13:00-17:00)',NULL),(547,'24小時',NULL),(547,'4小時(上午8:30-12:30)',NULL),(547,'8小時',NULL),(548,'24小時',NULL),(548,'4小時(上午8:30-12:30)',NULL),(548,'4小時(下午13:00-17:00)',NULL),(548,'8小時',NULL),(549,'24小時',NULL),(549,'4小時(上午8:30-12:30)',NULL),(549,'4小時(下午13:00-17:00)',NULL),(549,'8小時',NULL),(550,'24小時',NULL),(550,'4小時(上午8:30-12:30)',NULL),(550,'4小時(下午13:00-17:00)',NULL),(550,'8小時',NULL),(551,'4小時(上午8:30-12:30)',NULL),(552,'24小時',NULL),(552,'4小時(下午13:00-17:00)',NULL),(553,'24小時',NULL),(553,'4小時(下午13:00-17:00)',NULL),(554,'24小時',NULL),(554,'4小時(上午8:30-12:30)',NULL),(554,'4小時(下午13:00-17:00)',NULL),(554,'8小時',NULL),(555,'4小時(上午8:30-12:30)',NULL),(555,'8小時',NULL),(556,'24小時',NULL),(556,'4小時(下午13:00-17:00)',NULL),(556,'8小時',NULL),(557,'24小時',NULL),(557,'4小時(下午13:00-17:00)',NULL),(557,'8小時',NULL),(558,'24小時',NULL),(558,'4小時(上午8:30-12:30)',NULL),(558,'4小時(下午13:00-17:00)',NULL),(559,'24小時',NULL),(559,'4小時(上午8:30-12:30)',NULL),(560,'4小時(上午8:30-12:30)',NULL),(560,'8小時',NULL),(561,'24小時',NULL),(562,'4小時(上午8:30-12:30)',NULL),(562,'4小時(下午13:00-17:00)',NULL),(563,'24小時',NULL),(563,'4小時(上午8:30-12:30)',NULL),(563,'8小時',NULL),(564,'24小時',NULL),(564,'4小時(上午8:30-12:30)',NULL),(564,'4小時(下午13:00-17:00)',NULL),(564,'8小時',NULL),(565,'4小時(上午8:30-12:30)',NULL),(566,'8小時',NULL),(567,'24小時',NULL),(567,'4小時(上午8:30-12:30)',NULL),(567,'4小時(下午13:00-17:00)',NULL),(567,'8小時',NULL),(568,'24小時',NULL),(568,'4小時(上午8:30-12:30)',NULL),(568,'4小時(下午13:00-17:00)',NULL),(568,'8小時',NULL),(569,'4小時(上午8:30-12:30)',NULL),(569,'8小時',NULL),(570,'24小時',NULL),(570,'4小時(上午8:30-12:30)',NULL),(570,'4小時(下午13:00-17:00)',NULL),(570,'8小時',NULL),(571,'4小時(下午13:00-17:00)',NULL),(571,'8小時',NULL),(572,'24小時',NULL),(572,'4小時(上午8:30-12:30)',NULL),(573,'4小時(下午13:00-17:00)',NULL),(573,'8小時',NULL),(574,'24小時',NULL),(574,'4小時(上午8:30-12:30)',NULL),(574,'4小時(下午13:00-17:00)',NULL),(574,'8小時',NULL),(575,'4小時(上午8:30-12:30)',NULL),(575,'4小時(下午13:00-17:00)',NULL),(575,'8小時',NULL),(576,'4小時(上午8:30-12:30)',NULL),(576,'4小時(下午13:00-17:00)',NULL),(576,'8小時',NULL),(577,'24小時',NULL),(577,'4小時(下午13:00-17:00)',NULL),(577,'8小時',NULL),(578,'24小時',NULL),(578,'4小時(上午8:30-12:30)',NULL),(578,'4小時(下午13:00-17:00)',NULL),(578,'8小時',NULL),(579,'4小時(上午8:30-12:30)',NULL),(579,'4小時(下午13:00-17:00)',NULL),(580,'24小時',NULL),(580,'4小時(上午8:30-12:30)',NULL),(580,'8小時',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=215 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `staff_transfer_allocations`
--

LOCK TABLES `staff_transfer_allocations` WRITE;
/*!40000 ALTER TABLE `staff_transfer_allocations` DISABLE KEYS */;
INSERT INTO `staff_transfer_allocations` VALUES (184,100,134,26400.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(185,100,134,240.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(186,101,135,28600.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(187,101,135,260.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(188,102,136,20000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(189,102,136,10000.00,'legacy_subsidy','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(190,102,136,166.67,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(191,103,137,20000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(192,103,137,10000.00,'legacy_subsidy','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(193,103,137,166.67,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(194,104,138,20000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(195,104,138,10000.00,'legacy_subsidy','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(196,104,138,166.66,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(197,105,139,132000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(198,106,140,54000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(199,106,140,500.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(200,107,141,54000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(201,108,142,67500.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(202,108,142,500.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(203,109,143,49500.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(204,109,143,500.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(205,110,144,216000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(206,110,144,500.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(207,111,145,49500.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(208,111,145,500.00,'floor_fee','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(209,112,146,50000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(210,113,147,67500.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(211,114,148,180000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(212,115,149,66000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(213,116,150,67500.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35'),(214,117,151,48000.00,'regular_salary','explicit','approved',NULL,'2026-07-22 07:46:35','2026-07-22 07:46:35');
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
INSERT INTO `staff_transportation` VALUES (531,'機車'),(531,'轎車'),(532,'機車'),(532,'轎車'),(533,'機車'),(533,'轎車'),(534,'機車'),(534,'轎車'),(535,'機車'),(535,'轎車'),(536,'機車'),(536,'轎車'),(537,'機車'),(537,'轎車'),(538,'機車'),(538,'轎車'),(539,'機車'),(539,'轎車'),(540,'機車'),(540,'轎車'),(541,'機車'),(541,'轎車'),(542,'機車'),(543,'轎車'),(544,'轎車'),(545,'機車'),(546,'機車'),(547,'機車'),(547,'轎車'),(548,'轎車'),(549,'機車'),(550,'轎車'),(551,'轎車'),(552,'機車'),(552,'轎車'),(553,'機車'),(553,'轎車'),(554,'機車'),(554,'轎車'),(555,'轎車'),(556,'機車'),(556,'轎車'),(557,'機車'),(558,'轎車'),(559,'機車'),(559,'轎車'),(560,'機車'),(560,'轎車'),(561,'機車'),(561,'轎車'),(562,'轎車'),(563,'機車'),(563,'轎車'),(564,'機車'),(564,'轎車'),(565,'轎車'),(566,'機車'),(566,'轎車'),(567,'機車'),(568,'機車'),(568,'轎車'),(569,'機車'),(569,'轎車'),(570,'機車'),(570,'轎車'),(571,'機車'),(572,'機車'),(572,'轎車'),(573,'機車'),(573,'轎車'),(574,'轎車'),(575,'轎車'),(576,'機車'),(576,'轎車'),(577,'機車'),(577,'轎車'),(578,'機車'),(578,'轎車'),(579,'機車'),(580,'機車'),(580,'轎車');
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
INSERT INTO `staff_weekly_rest` VALUES (531,'連續服務',NULL),(531,'週休1日',NULL),(531,'週休2日',NULL),(532,'連續服務',NULL),(533,'連續服務',NULL),(533,'週休1日',NULL),(533,'週休2日',NULL),(534,'連續服務',NULL),(535,'連續服務',NULL),(535,'週休1日',NULL),(535,'週休2日',NULL),(536,'週休2日',NULL),(537,'連續服務',NULL),(537,'週休1日',NULL),(537,'週休2日',NULL),(538,'週休2日',NULL),(539,'連續服務',NULL),(539,'週休1日',NULL),(539,'週休2日',NULL),(540,'連續服務',NULL),(541,'週休1日',NULL),(542,'連續服務',NULL),(542,'週休1日',NULL),(542,'週休2日',NULL),(543,'連續服務',NULL),(543,'週休1日',NULL),(543,'週休2日',NULL),(544,'週休1日',NULL),(545,'連續服務',NULL),(545,'週休1日',NULL),(545,'週休2日',NULL),(546,'連續服務',NULL),(546,'週休1日',NULL),(546,'週休2日',NULL),(547,'連續服務',NULL),(548,'週休1日',NULL),(549,'連續服務',NULL),(549,'週休1日',NULL),(550,'連續服務',NULL),(551,'週休1日',NULL),(551,'週休2日',NULL),(552,'週休2日',NULL),(553,'連續服務',NULL),(553,'週休1日',NULL),(553,'週休2日',NULL),(554,'週休1日',NULL),(555,'連續服務',NULL),(555,'週休1日',NULL),(556,'連續服務',NULL),(556,'週休2日',NULL),(557,'連續服務',NULL),(557,'週休1日',NULL),(557,'週休2日',NULL),(558,'連續服務',NULL),(558,'週休1日',NULL),(559,'連續服務',NULL),(559,'週休2日',NULL),(560,'連續服務',NULL),(561,'連續服務',NULL),(562,'週休2日',NULL),(563,'連續服務',NULL),(563,'週休2日',NULL),(564,'週休2日',NULL),(565,'連續服務',NULL),(565,'週休1日',NULL),(565,'週休2日',NULL),(566,'連續服務',NULL),(566,'週休2日',NULL),(567,'週休2日',NULL),(568,'連續服務',NULL),(568,'週休2日',NULL),(569,'連續服務',NULL),(569,'週休2日',NULL),(570,'連續服務',NULL),(570,'週休2日',NULL),(571,'連續服務',NULL),(571,'週休1日',NULL),(571,'週休2日',NULL),(572,'連續服務',NULL),(572,'週休1日',NULL),(572,'週休2日',NULL),(573,'週休1日',NULL),(574,'連續服務',NULL),(575,'連續服務',NULL),(575,'週休1日',NULL),(575,'週休2日',NULL),(576,'週休1日',NULL),(576,'週休2日',NULL),(577,'週休1日',NULL),(577,'週休2日',NULL),(578,'連續服務',NULL),(578,'週休1日',NULL),(578,'週休2日',NULL),(579,'連續服務',NULL),(580,'連續服務',NULL),(580,'週休1日',NULL),(580,'週休2日',NULL);
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
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
  `alert_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_domain` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `case_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `details` json NOT NULL,
  `event_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` enum('open','claimed','resolved') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'open',
  `claimed_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `claimed_at` datetime DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `resolved_at` datetime DEFAULT NULL,
  `resolved_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resolution_reason` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_alert_case` (`alert_code`,`case_key`),
  KEY `idx_alert_status` (`status`),
  KEY `idx_system_alert_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=223 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_alerts`
--

LOCK TABLES `system_alerts` WRITE;
/*!40000 ALTER TABLE `system_alerts` DISABLE KEYS */;
INSERT INTO `system_alerts` VALUES (112,'ORDER-001','ORDER','115000049','案件 115000049 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000049\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(113,'ORDER-001','ORDER','115000035','案件 115000035 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000035\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(114,'ORDER-001','ORDER','115000046','案件 115000046 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000046\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(115,'ORDER-001','ORDER','115000030','案件 115000030 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000030\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(116,'ORDER-001','ORDER','115000037','案件 115000037 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000037\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(117,'ORDER-001','ORDER','115000016','案件 115000016 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000016\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(118,'ORDER-001','ORDER','115000025','案件 115000025 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000025\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(119,'ORDER-001','ORDER','115000023','案件 115000023 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000023\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(120,'ORDER-001','ORDER','115000050','案件 115000050 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000050\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(121,'ORDER-001','ORDER','115000039','案件 115000039 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000039\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(122,'ORDER-001','ORDER','115000021','案件 115000021 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000021\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(123,'ORDER-001','ORDER','115000036','案件 115000036 尚未發送訂單資訊-1給任何候選月嫂','{\"case_no\": \"115000036\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(124,'ORDER-003','ORDER','115000015','案件 115000015 已發送訂單資訊-1，候選月嫂尚未回覆意願','{\"case_no\": \"115000015\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(125,'ORDER-003','ORDER','115000042','案件 115000042 已發送訂單資訊-1，候選月嫂尚未回覆意願','{\"case_no\": \"115000042\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(126,'LINE-001','LINE','115000001','案件 115000001 的客戶尚未綁定 LINE','{\"case_no\": \"115000001\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(127,'LINE-001','LINE','115000002','案件 115000002 的客戶尚未綁定 LINE','{\"case_no\": \"115000002\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(128,'LINE-001','LINE','115000003','案件 115000003 的客戶尚未綁定 LINE','{\"case_no\": \"115000003\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(129,'LINE-001','LINE','115000004','案件 115000004 的客戶尚未綁定 LINE','{\"case_no\": \"115000004\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(130,'LINE-001','LINE','115000005','案件 115000005 的客戶尚未綁定 LINE','{\"case_no\": \"115000005\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(131,'LINE-001','LINE','115000006','案件 115000006 的客戶尚未綁定 LINE','{\"case_no\": \"115000006\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(132,'LINE-001','LINE','115000007','案件 115000007 的客戶尚未綁定 LINE','{\"case_no\": \"115000007\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(133,'LINE-001','LINE','115000008','案件 115000008 的客戶尚未綁定 LINE','{\"case_no\": \"115000008\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(134,'LINE-001','LINE','115000009','案件 115000009 的客戶尚未綁定 LINE','{\"case_no\": \"115000009\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(135,'LINE-001','LINE','115000010','案件 115000010 的客戶尚未綁定 LINE','{\"case_no\": \"115000010\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(136,'LINE-001','LINE','115000011','案件 115000011 的客戶尚未綁定 LINE','{\"case_no\": \"115000011\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(137,'LINE-001','LINE','115000012','案件 115000012 的客戶尚未綁定 LINE','{\"case_no\": \"115000012\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(138,'LINE-001','LINE','115000013','案件 115000013 的客戶尚未綁定 LINE','{\"case_no\": \"115000013\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(139,'LINE-001','LINE','115000014','案件 115000014 的客戶尚未綁定 LINE','{\"case_no\": \"115000014\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(140,'LINE-001','LINE','115000015','案件 115000015 的客戶尚未綁定 LINE','{\"case_no\": \"115000015\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(141,'LINE-001','LINE','115000016','案件 115000016 的客戶尚未綁定 LINE','{\"case_no\": \"115000016\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(142,'LINE-001','LINE','115000017','案件 115000017 的客戶尚未綁定 LINE','{\"case_no\": \"115000017\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(143,'LINE-001','LINE','115000018','案件 115000018 的客戶尚未綁定 LINE','{\"case_no\": \"115000018\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(144,'LINE-001','LINE','115000019','案件 115000019 的客戶尚未綁定 LINE','{\"case_no\": \"115000019\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(145,'LINE-001','LINE','115000020','案件 115000020 的客戶尚未綁定 LINE','{\"case_no\": \"115000020\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(146,'LINE-001','LINE','115000021','案件 115000021 的客戶尚未綁定 LINE','{\"case_no\": \"115000021\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(147,'LINE-001','LINE','115000022','案件 115000022 的客戶尚未綁定 LINE','{\"case_no\": \"115000022\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(148,'LINE-001','LINE','115000023','案件 115000023 的客戶尚未綁定 LINE','{\"case_no\": \"115000023\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(149,'LINE-001','LINE','115000024','案件 115000024 的客戶尚未綁定 LINE','{\"case_no\": \"115000024\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(150,'LINE-001','LINE','115000025','案件 115000025 的客戶尚未綁定 LINE','{\"case_no\": \"115000025\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(151,'LINE-001','LINE','115000026','案件 115000026 的客戶尚未綁定 LINE','{\"case_no\": \"115000026\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(152,'LINE-001','LINE','115000027','案件 115000027 的客戶尚未綁定 LINE','{\"case_no\": \"115000027\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(153,'LINE-001','LINE','115000028','案件 115000028 的客戶尚未綁定 LINE','{\"case_no\": \"115000028\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(154,'LINE-001','LINE','115000029','案件 115000029 的客戶尚未綁定 LINE','{\"case_no\": \"115000029\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(155,'LINE-001','LINE','115000030','案件 115000030 的客戶尚未綁定 LINE','{\"case_no\": \"115000030\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(156,'LINE-001','LINE','115000031','案件 115000031 的客戶尚未綁定 LINE','{\"case_no\": \"115000031\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(157,'LINE-001','LINE','115000032','案件 115000032 的客戶尚未綁定 LINE','{\"case_no\": \"115000032\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(158,'LINE-001','LINE','115000033','案件 115000033 的客戶尚未綁定 LINE','{\"case_no\": \"115000033\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(159,'LINE-001','LINE','115000034','案件 115000034 的客戶尚未綁定 LINE','{\"case_no\": \"115000034\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(160,'LINE-001','LINE','115000035','案件 115000035 的客戶尚未綁定 LINE','{\"case_no\": \"115000035\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(161,'LINE-001','LINE','115000036','案件 115000036 的客戶尚未綁定 LINE','{\"case_no\": \"115000036\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(162,'LINE-001','LINE','115000037','案件 115000037 的客戶尚未綁定 LINE','{\"case_no\": \"115000037\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(163,'LINE-001','LINE','115000038','案件 115000038 的客戶尚未綁定 LINE','{\"case_no\": \"115000038\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(164,'LINE-001','LINE','115000039','案件 115000039 的客戶尚未綁定 LINE','{\"case_no\": \"115000039\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(165,'LINE-001','LINE','115000040','案件 115000040 的客戶尚未綁定 LINE','{\"case_no\": \"115000040\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(166,'LINE-001','LINE','115000041','案件 115000041 的客戶尚未綁定 LINE','{\"case_no\": \"115000041\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(167,'LINE-001','LINE','115000042','案件 115000042 的客戶尚未綁定 LINE','{\"case_no\": \"115000042\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(168,'LINE-001','LINE','115000043','案件 115000043 的客戶尚未綁定 LINE','{\"case_no\": \"115000043\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(169,'LINE-001','LINE','115000044','案件 115000044 的客戶尚未綁定 LINE','{\"case_no\": \"115000044\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(170,'LINE-001','LINE','115000045','案件 115000045 的客戶尚未綁定 LINE','{\"case_no\": \"115000045\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(171,'LINE-001','LINE','115000046','案件 115000046 的客戶尚未綁定 LINE','{\"case_no\": \"115000046\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(172,'LINE-001','LINE','115000047','案件 115000047 的客戶尚未綁定 LINE','{\"case_no\": \"115000047\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(173,'LINE-001','LINE','115000048','案件 115000048 的客戶尚未綁定 LINE','{\"case_no\": \"115000048\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(174,'LINE-001','LINE','115000049','案件 115000049 的客戶尚未綁定 LINE','{\"case_no\": \"115000049\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(175,'LINE-001','LINE','115000050','案件 115000050 的客戶尚未綁定 LINE','{\"case_no\": \"115000050\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(176,'LINE-005','LINE','115000026','案件 115000026 的服務人員尚未綁定 LINE','{\"case_no\": \"115000026\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(177,'LINE-005','LINE','115000008','案件 115000008 的服務人員尚未綁定 LINE','{\"case_no\": \"115000008\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(178,'LINE-005','LINE','115000011','案件 115000011 的服務人員尚未綁定 LINE','{\"case_no\": \"115000011\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(179,'LINE-005','LINE','115000040','案件 115000040 的服務人員尚未綁定 LINE','{\"case_no\": \"115000040\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(180,'LINE-005','LINE','115000028','案件 115000028 的服務人員尚未綁定 LINE','{\"case_no\": \"115000028\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(181,'LINE-005','LINE','115000002','案件 115000002 的服務人員尚未綁定 LINE','{\"case_no\": \"115000002\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(182,'LINE-005','LINE','115000044','案件 115000044 的服務人員尚未綁定 LINE','{\"case_no\": \"115000044\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(183,'LINE-005','LINE','115000022','案件 115000022 的服務人員尚未綁定 LINE','{\"case_no\": \"115000022\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(184,'LINE-005','LINE','115000012','案件 115000012 的服務人員尚未綁定 LINE','{\"case_no\": \"115000012\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(185,'LINE-005','LINE','115000043','案件 115000043 的服務人員尚未綁定 LINE','{\"case_no\": \"115000043\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(186,'LINE-005','LINE','115000014','案件 115000014 的服務人員尚未綁定 LINE','{\"case_no\": \"115000014\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(187,'LINE-005','LINE','115000045','案件 115000045 的服務人員尚未綁定 LINE','{\"case_no\": \"115000045\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(188,'LINE-005','LINE','115000006','案件 115000006 的服務人員尚未綁定 LINE','{\"case_no\": \"115000006\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(189,'LINE-005','LINE','115000020','案件 115000020 的服務人員尚未綁定 LINE','{\"case_no\": \"115000020\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(190,'LINE-005','LINE','115000048','案件 115000048 的服務人員尚未綁定 LINE','{\"case_no\": \"115000048\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(191,'LINE-005','LINE','115000031','案件 115000031 的服務人員尚未綁定 LINE','{\"case_no\": \"115000031\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(192,'LINE-005','LINE','115000009','案件 115000009 的服務人員尚未綁定 LINE','{\"case_no\": \"115000009\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(193,'LINE-005','LINE','115000038','案件 115000038 的服務人員尚未綁定 LINE','{\"case_no\": \"115000038\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(194,'LINE-005','LINE','115000041','案件 115000041 的服務人員尚未綁定 LINE','{\"case_no\": \"115000041\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(195,'LINE-005','LINE','115000047','案件 115000047 的服務人員尚未綁定 LINE','{\"case_no\": \"115000047\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(196,'LINE-005','LINE','115000003','案件 115000003 的服務人員尚未綁定 LINE','{\"case_no\": \"115000003\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(197,'LINE-005','LINE','115000019','案件 115000019 的服務人員尚未綁定 LINE','{\"case_no\": \"115000019\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(198,'LINE-005','LINE','115000007','案件 115000007 的服務人員尚未綁定 LINE','{\"case_no\": \"115000007\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(199,'LINE-005','LINE','115000010','案件 115000010 的服務人員尚未綁定 LINE','{\"case_no\": \"115000010\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(200,'LINE-005','LINE','115000013','案件 115000013 的服務人員尚未綁定 LINE','{\"case_no\": \"115000013\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(201,'LINE-005','LINE','115000004','案件 115000004 的服務人員尚未綁定 LINE','{\"case_no\": \"115000004\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(202,'LINE-005','LINE','115000034','案件 115000034 的服務人員尚未綁定 LINE','{\"case_no\": \"115000034\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(203,'LINE-005','LINE','115000017','案件 115000017 的服務人員尚未綁定 LINE','{\"case_no\": \"115000017\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(204,'LINE-005','LINE','115000018','案件 115000018 的服務人員尚未綁定 LINE','{\"case_no\": \"115000018\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(205,'LINE-005','LINE','115000024','案件 115000024 的服務人員尚未綁定 LINE','{\"case_no\": \"115000024\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(206,'LINE-005','LINE','115000033','案件 115000033 的服務人員尚未綁定 LINE','{\"case_no\": \"115000033\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(207,'LINE-005','LINE','115000027','案件 115000027 的服務人員尚未綁定 LINE','{\"case_no\": \"115000027\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(208,'LINE-005','LINE','115000032','案件 115000032 的服務人員尚未綁定 LINE','{\"case_no\": \"115000032\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(209,'DOC-SEND-001','DOC-SEND','115000035','案件 115000035 已有候選月嫂願意接案，但履歷尚未發送給客戶','{\"case_no\": \"115000035\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(210,'DOC-SEND-001','DOC-SEND','115000050','案件 115000050 已有候選月嫂願意接案，但履歷尚未發送給客戶','{\"case_no\": \"115000050\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(211,'RECEIVABLE-001','RECEIVABLE','115000005','案件 115000005 的客戶訂金已過應收日期，尚未收齊','{\"case_no\": \"115000005\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"1000.00\", \"階段\": \"訂金\", \"到期日\": \"2026-07-29\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(212,'RECEIVABLE-001','RECEIVABLE','115000011','案件 115000011 的客戶第二期已過應收日期，尚未收齊','{\"case_no\": \"115000011\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"28575.00\", \"階段\": \"第二期\", \"到期日\": \"2026-07-17\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(213,'RECEIVABLE-001','RECEIVABLE','115000019','案件 115000019 的客戶第二期已過應收日期，尚未收齊','{\"case_no\": \"115000019\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"28575.00\", \"階段\": \"第二期\", \"到期日\": \"2026-07-07\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(214,'RECEIVABLE-001','RECEIVABLE','115000026','案件 115000026 的客戶第二期已過應收日期，尚未收齊','{\"case_no\": \"115000026\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"35438.00\", \"階段\": \"第二期\", \"到期日\": \"2026-06-25\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(215,'RECEIVABLE-001','RECEIVABLE','115000029','案件 115000029 的客戶訂金已過應收日期，尚未收齊','{\"case_no\": \"115000029\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"8100.00\", \"階段\": \"訂金\", \"到期日\": \"2026-07-21\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(216,'RECEIVABLE-001','RECEIVABLE','115000043','案件 115000043 的客戶第二期已過應收日期，尚未收齊','{\"case_no\": \"115000043\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"37800.00\", \"階段\": \"第二期\", \"到期日\": \"2026-06-18\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(217,'RECEIVABLE-001','RECEIVABLE','115000047','案件 115000047 的客戶第二期已過應收日期，尚未收齊','{\"case_no\": \"115000047\", \"逾期階段\": [{\"已收\": \"0.00\", \"應收\": \"25200.00\", \"階段\": \"第二期\", \"到期日\": \"2026-06-28\"}]}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(218,'SCHEDULE-005','SCHEDULE','575:2026-06-19','案件 115000024 的月嫂登記國定假日必休，但 2026-06-19（端午節）排班仍是上班日','{\"case_no\": \"115000024\", \"staff_id\": 575, \"work_date\": \"2026-06-19\", \"holiday_name\": \"端午節\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(219,'SCHEDULE-005','SCHEDULE','563:2026-06-19','案件 115000009 的月嫂登記國定假日必休，但 2026-06-19（端午節）排班仍是上班日','{\"case_no\": \"115000009\", \"staff_id\": 563, \"work_date\": \"2026-06-19\", \"holiday_name\": \"端午節\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(220,'SCHEDULE-005','SCHEDULE','547:2026-06-19','案件 115000043 的月嫂登記國定假日必休，但 2026-06-19（端午節）排班仍是上班日','{\"case_no\": \"115000043\", \"staff_id\": 547, \"work_date\": \"2026-06-19\", \"holiday_name\": \"端午節\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(221,'SCHEDULE-005','SCHEDULE','541:2026-06-19','案件 115000022 的月嫂登記國定假日必休，但 2026-06-19（端午節）排班仍是上班日','{\"case_no\": \"115000022\", \"staff_id\": 541, \"work_date\": \"2026-06-19\", \"holiday_name\": \"端午節\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL),(222,'SCHEDULE-005','SCHEDULE','537:2026-06-19','案件 115000044 的月嫂登記國定假日必休，但 2026-06-19（端午節）排班仍是上班日','{\"case_no\": \"115000044\", \"staff_id\": 537, \"work_date\": \"2026-06-19\", \"holiday_name\": \"端午節\"}',NULL,NULL,'open',NULL,NULL,'2026-08-01 05:26:56','2026-08-01 05:26:56',NULL,NULL,NULL);
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
-- Dumping events for database 'lu_test_accounting_linkage_20260804'
--

--
-- Dumping routines for database 'lu_test_accounting_linkage_20260804'
--

--
-- Current Database: `lu_test_accounting_linkage_20260804`
--

USE `lu_test_accounting_linkage_20260804`;

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

-- Dump completed on 2026-08-04  5:56:36
