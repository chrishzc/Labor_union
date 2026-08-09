-- Reviewed, published knowledge is independent from the retired legacy FAQ table.
CREATE TABLE IF NOT EXISTS knowledge_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_uri VARCHAR(500) NOT NULL,
    source_trust_tier ENUM('internal_policy','government_source','approved_partner') NOT NULL,
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    content_digest CHAR(64) NOT NULL,
    state ENUM('draft','reviewed','published','retired') NOT NULL DEFAULT 'draft',
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_by_admin_user_id BIGINT NOT NULL,
    reviewed_by_admin_user_id BIGINT NULL,
    published_by_admin_user_id BIGINT NULL,
    retired_by_admin_user_id BIGINT NULL,
    review_reason VARCHAR(500) NULL,
    publication_reason VARCHAR(500) NULL,
    retired_reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    published_at DATETIME NULL,
    retired_at DATETIME NULL,
    UNIQUE KEY uk_knowledge_source_digest (source_uri, content_digest),
    INDEX idx_knowledge_answer (state, source_trust_tier, published_at),
    CONSTRAINT fk_knowledge_creator FOREIGN KEY (created_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_reviewer FOREIGN KEY (reviewed_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_publisher FOREIGN KEY (published_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_retirer FOREIGN KEY (retired_by_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_published_actor
        CHECK (state <> 'published' OR published_by_admin_user_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_item_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    knowledge_item_id BIGINT NOT NULL,
    actor_admin_user_id BIGINT NOT NULL,
    event_type ENUM('ingested','reviewed','published','retired') NOT NULL,
    before_version BIGINT UNSIGNED NOT NULL,
    after_version BIGINT UNSIGNED NOT NULL,
    reason VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    snapshot_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_knowledge_event_idempotency (idempotency_key),
    INDEX idx_knowledge_event_item (knowledge_item_id, created_at),
    CONSTRAINT fk_knowledge_event_item FOREIGN KEY (knowledge_item_id)
        REFERENCES knowledge_items(id) ON DELETE RESTRICT,
    CONSTRAINT fk_knowledge_event_actor FOREIGN KEY (actor_admin_user_id)
        REFERENCES admin_users(id) ON DELETE RESTRICT,
    CONSTRAINT chk_knowledge_event_version
        CHECK (after_version = before_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_apply_receipts (
    idempotency_key VARCHAR(191) PRIMARY KEY,
    command_fingerprint CHAR(64) NOT NULL,
    receipt_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
