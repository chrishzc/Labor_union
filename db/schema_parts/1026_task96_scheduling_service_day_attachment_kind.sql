-- File: 1026_task96_scheduling_service_day_attachment_kind.sql
-- Purpose: preserve-data successor for the Scheduling Baby Log controlled-media kind.
-- Data effect: schema only; existing service-day log attachments remain readable.

ALTER TABLE scheduling_service_day_log_attachments
    MODIFY COLUMN attachment_kind ENUM('meal_photo','baby_log_photo') NOT NULL;
