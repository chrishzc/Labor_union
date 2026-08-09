-- Stage 5 reliable LINE configuration, media-outbox, and Rich Menu publication runtime.

SET @line_outbox_max_attempts_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_domain_outbox'
      AND COLUMN_NAME='max_attempts'
);
SET @line_outbox_max_attempts_column_sql := IF(
    @line_outbox_max_attempts_column_exists=0,
    'ALTER TABLE line_domain_outbox ADD COLUMN max_attempts INT UNSIGNED NOT NULL DEFAULT 3 AFTER attempt_count',
    'SELECT 1'
);
PREPARE line_outbox_max_attempts_column_stmt FROM @line_outbox_max_attempts_column_sql;
EXECUTE line_outbox_max_attempts_column_stmt;
DEALLOCATE PREPARE line_outbox_max_attempts_column_stmt;

SET @line_outbox_error_message_column_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='line_domain_outbox'
      AND COLUMN_NAME='error_message'
);
SET @line_outbox_error_message_column_sql := IF(
    @line_outbox_error_message_column_exists=0,
    'ALTER TABLE line_domain_outbox ADD COLUMN error_message VARCHAR(1000) NULL AFTER error_code',
    'SELECT 1'
);
PREPARE line_outbox_error_message_column_stmt FROM @line_outbox_error_message_column_sql;
EXECUTE line_outbox_error_message_column_stmt;
DEALLOCATE PREPARE line_outbox_error_message_column_stmt;

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_step_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    publication_id BIGINT UNSIGNED NOT NULL,
    step_name ENUM('create','upload','switch','cleanup') NOT NULL,
    provider_menu_id VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    completed_at_utc DATETIME(6) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_step (publication_id, step_name),
    UNIQUE KEY uq_line_rich_menu_step_idempotency (idempotency_key),
    CONSTRAINT fk_line_rich_menu_step_publication
        FOREIGN KEY (publication_id) REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_receipts_before_update;
CREATE TRIGGER trg_line_rich_menu_step_receipts_before_update
BEFORE UPDATE ON line_rich_menu_publication_step_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_rich_menu_step_receipts_before_delete;
CREATE TRIGGER trg_line_rich_menu_step_receipts_before_delete
BEFORE DELETE ON line_rich_menu_publication_step_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_rich_menu_publication_step_receipts records cannot be deleted';
