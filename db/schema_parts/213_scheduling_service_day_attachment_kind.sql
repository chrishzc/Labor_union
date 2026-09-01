-- File: 213_scheduling_service_day_attachment_kind.sql
-- Description: Add the Scheduling-owned Baby Log controlled-media attachment kind.
-- This successor preserves the hash-bound 204 release and changes no existing rows.

ALTER TABLE scheduling_service_day_log_attachments
    MODIFY COLUMN attachment_kind ENUM('meal_photo','baby_log_photo') NOT NULL;
