-- Reviewed knowledge roots, rebuildable indexes, and cited answer receipts.

CREATE TABLE IF NOT EXISTS knowledge_items (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_identity VARCHAR(191) NOT NULL,
    title VARCHAR(500) NOT NULL,
    lifecycle_status ENUM('draft','reviewed','published','retired') NOT NULL DEFAULT 'draft',
    current_version INT UNSIGNED NOT NULL DEFAULT 1,
    source_digest CHAR(64) NOT NULL,
    source_uri VARCHAR(1000) NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_source_identity (source_identity),
    INDEX idx_knowledge_lifecycle (lifecycle_status, id),
    CONSTRAINT chk_knowledge_source_digest CHECK (source_digest REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_item_versions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    item_id BIGINT UNSIGNED NOT NULL,
    item_version INT UNSIGNED NOT NULL,
    content MEDIUMTEXT NOT NULL,
    source_digest CHAR(64) NOT NULL,
    event_type ENUM('ingested','reviewed','published','retired') NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    reason VARCHAR(500) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    recorded_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_item_version (item_id, item_version),
    UNIQUE KEY uq_knowledge_version_key (idempotency_key),
    CONSTRAINT fk_knowledge_version_item FOREIGN KEY (item_id)
        REFERENCES knowledge_items(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_answer_requests (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    question VARCHAR(2000) NOT NULL,
    requester_line_user_id VARCHAR(191) NULL,
    request_status ENUM('pending','processing','answered','unsupported','failed') NOT NULL DEFAULT 'pending',
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_knowledge_answer_request_key (idempotency_key),
    INDEX idx_knowledge_answer_request_status (request_status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    job_type ENUM('index_build','answer') NOT NULL,
    processing_status ENUM('pending','processing','completed','retry_pending','failed') NOT NULL DEFAULT 'pending',
    answer_request_id BIGINT UNSIGNED NULL,
    target_index_version INT UNSIGNED NULL,
    question VARCHAR(2000) NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    available_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    last_error_code VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_by_actor_id VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at_utc DATETIME(6) NULL,
    UNIQUE KEY uq_knowledge_job_key (idempotency_key),
    INDEX idx_knowledge_job_claim (processing_status, available_at_utc, id),
    CONSTRAINT fk_knowledge_job_answer_request FOREIGN KEY (answer_request_id)
        REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_indexes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    index_version INT UNSIGNED NOT NULL,
    index_status ENUM('requested','building','ready','stale','failed') NOT NULL,
    content_set_digest CHAR(64) NULL,
    built_at_utc DATETIME(6) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_index_version (index_version),
    INDEX idx_knowledge_index_ready (index_status, index_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_answer_receipts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    answer_request_id BIGINT UNSIGNED NOT NULL,
    answer_text TEXT NOT NULL,
    index_version INT UNSIGNED NOT NULL,
    authoritative BOOLEAN NOT NULL DEFAULT FALSE,
    line_delivery_task_id BIGINT UNSIGNED NULL,
    answered_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_knowledge_answer_receipt_request (answer_request_id),
    CONSTRAINT fk_knowledge_answer_request FOREIGN KEY (answer_request_id)
        REFERENCES knowledge_answer_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_answer_delivery FOREIGN KEY (line_delivery_task_id)
        REFERENCES line_delivery_tasks(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_answer_non_authoritative CHECK (authoritative=FALSE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_answer_sources (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    answer_receipt_id BIGINT UNSIGNED NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_version INT UNSIGNED NOT NULL,
    safe_excerpt VARCHAR(500) NOT NULL,
    citation_order INT UNSIGNED NOT NULL,
    UNIQUE KEY uq_knowledge_answer_source_order (answer_receipt_id, citation_order),
    CONSTRAINT fk_knowledge_answer_source_receipt FOREIGN KEY (answer_receipt_id)
        REFERENCES knowledge_answer_receipts(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_knowledge_item_versions_before_update;
CREATE TRIGGER trg_knowledge_item_versions_before_update
BEFORE UPDATE ON knowledge_item_versions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be updated';

DROP TRIGGER IF EXISTS trg_knowledge_item_versions_before_delete;
CREATE TRIGGER trg_knowledge_item_versions_before_delete
BEFORE DELETE ON knowledge_item_versions FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='knowledge_item_versions records cannot be deleted';
