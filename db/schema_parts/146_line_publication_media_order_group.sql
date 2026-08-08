-- Canonical LINE Rich Menu publication, media metadata, and order-group binding.

CREATE TABLE IF NOT EXISTS line_rich_menu_publication_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    menu_definition_id VARCHAR(191) NOT NULL,
    configuration_revision BIGINT UNSIGNED NOT NULL,
    operation ENUM('publish','rollback','delete') NOT NULL DEFAULT 'publish',
    publication_status ENUM(
        'draft','queued','publishing','published','publish_retryable_failed',
        'failed','rollback_queued','delete_queued','rollback_retryable_failed',
        'delete_retryable_failed','rolled_back','deleted'
    ) NOT NULL,
    definition_snapshot JSON NOT NULL,
    image_object_reference VARCHAR(500) NULL,
    provider_menu_id VARCHAR(191) NULL,
    previous_provider_menu_id VARCHAR(191) NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    requested_by_actor_id VARCHAR(191) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 3,
    next_attempt_at_utc DATETIME(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at_utc DATETIME(6) NULL,
    error_code VARCHAR(191) NULL,
    error_message VARCHAR(1000) NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_rich_menu_publication_idempotency (idempotency_key),
    INDEX idx_line_rich_menu_publication_due (
        publication_status, next_attempt_at_utc, id
    ),
    INDEX idx_line_rich_menu_definition (
        menu_definition_id, configuration_revision, id
    ),
    CONSTRAINT chk_line_rich_menu_definition
        CHECK (JSON_TYPE(definition_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_rich_menu_publication_tasks (
    id, menu_definition_id, configuration_revision, operation,
    publication_status, definition_snapshot, image_object_reference,
    provider_menu_id, previous_provider_menu_id, idempotency_key,
    correlation_id, requested_by_actor_id, attempt_count, max_attempts,
    next_attempt_at_utc, error_code, error_message, created_at_utc, updated_at_utc
)
SELECT
    publication.id,
    publication.menu_config_id,
    0,
    'publish',
    CASE publication.status
        WHEN 'pending' THEN 'queued'
        WHEN 'processing' THEN 'publishing'
        WHEN 'published' THEN 'published'
        ELSE 'failed'
    END,
    publication.config_snapshot,
    asset.storage_key,
    publication.line_rich_menu_id,
    publication.previous_line_rich_menu_id,
    CONCAT('legacy-line-rich-menu:', publication.id),
    CONCAT('legacy-line-rich-menu:', publication.id),
    COALESCE(CAST(publication.requested_by_admin_user_id AS CHAR),
        'migration:line-stage-2'),
    publication.retry_count,
    publication.max_retries,
    publication.next_retry_at,
    publication.error_code,
    publication.error_message,
    publication.created_at,
    publication.updated_at
FROM line_rich_menu_publications AS publication
LEFT JOIN media_assets AS asset ON asset.id = publication.image_asset_id;

CREATE TABLE IF NOT EXISTS line_media_records (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    provider_media_id VARCHAR(191) NOT NULL,
    source_type ENUM('user','group','room') NOT NULL,
    source_identity VARCHAR(191) NOT NULL,
    source_user_id VARCHAR(191) NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    received_at_utc DATETIME(6) NOT NULL,
    media_category ENUM(
        'user_upload','identity_evidence','order_attachment','rich_menu_image',
        'customer_service_attachment','unclassified'
    ) NOT NULL,
    owner_type VARCHAR(100) NULL,
    owner_reference VARCHAR(191) NULL,
    object_reference VARCHAR(500) NOT NULL,
    legacy_media_asset_id BIGINT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_media_provider_id (provider_media_id),
    UNIQUE KEY uq_line_media_idempotency (idempotency_key),
    INDEX idx_line_media_owner (
        media_category, owner_type, owner_reference, received_at_utc
    ),
    CONSTRAINT fk_line_media_legacy_asset
        FOREIGN KEY (legacy_media_asset_id) REFERENCES media_assets(id)
        ON UPDATE RESTRICT ON DELETE SET NULL,
    CONSTRAINT chk_line_media_sha256
        CHECK (content_sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_media_records (
    provider_media_id, source_type, source_identity, content_type,
    size_bytes, content_sha256, received_at_utc, media_category,
    owner_type, owner_reference, object_reference, legacy_media_asset_id,
    idempotency_key
)
SELECT
    CONCAT('legacy-media:', id),
    'user',
    'legacy:unknown',
    mime_type,
    file_size,
    sha256,
    created_at,
    CASE category
        WHEN 'rich_menu' THEN 'rich_menu_image'
        WHEN 'line_user_upload' THEN 'user_upload'
        WHEN 'contract' THEN 'order_attachment'
        ELSE 'unclassified'
    END,
    owner_type,
    owner_id,
    storage_key,
    id,
    CONCAT('legacy-line-media:', id)
FROM media_assets
WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS line_order_group_bindings (
    case_no VARCHAR(50) PRIMARY KEY,
    group_id VARCHAR(191) NULL,
    binding_status ENUM('unbound','bound','replaced','released')
        NOT NULL DEFAULT 'unbound',
    aggregate_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_id (group_id),
    CONSTRAINT fk_line_order_group_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_status CHECK (
        (binding_status = 'unbound' AND group_id IS NULL)
        OR
        (binding_status <> 'unbound' AND group_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_binding_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    action ENUM('bound','replaced','released','legacy_imported') NOT NULL,
    before_group_id VARCHAR(191) NULL,
    resulting_group_id VARCHAR(191) NULL,
    expected_version BIGINT UNSIGNED NOT NULL,
    resulting_version BIGINT UNSIGNED NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    binding_fingerprint CHAR(64) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    occurred_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_event_idempotency (idempotency_key),
    INDEX idx_line_order_group_event_case (case_no, id),
    CONSTRAINT fk_line_order_group_event_binding
        FOREIGN KEY (case_no) REFERENCES line_order_group_bindings(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_event_fingerprint
        CHECK (binding_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_line_order_group_event_version
        CHECK (resulting_version = expected_version + 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS line_order_group_migration_anomalies (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL,
    legacy_group_id VARCHAR(191) NOT NULL,
    anomaly_code VARCHAR(100) NOT NULL,
    details_snapshot JSON NOT NULL,
    detected_at_utc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_line_order_group_migration_anomaly (
        case_no, anomaly_code
    ),
    INDEX idx_line_order_group_migration_group (legacy_group_id, id),
    CONSTRAINT fk_line_order_group_migration_order
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_line_order_group_migration_details
        CHECK (JSON_TYPE(details_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO line_order_group_bindings (
    case_no, group_id, binding_status, aggregate_version,
    created_at_utc, updated_at_utc
)
SELECT
    case_no,
    NULL,
    'unbound',
    0,
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
FROM orders;

INSERT IGNORE INTO line_order_group_migration_anomalies (
    case_no, legacy_group_id, anomaly_code, details_snapshot
)
SELECT
    source_order.case_no,
    TRIM(source_order.line_group_id),
    'duplicate_legacy_group_id',
    JSON_OBJECT(
        'legacy_group_id', TRIM(source_order.line_group_id),
        'duplicate_count', duplicate_group.duplicate_count
    )
FROM orders AS source_order
INNER JOIN (
    SELECT TRIM(line_group_id) AS group_id, COUNT(*) AS duplicate_count
    FROM orders
    WHERE line_group_id IS NOT NULL AND TRIM(line_group_id) <> ''
    GROUP BY TRIM(line_group_id)
    HAVING COUNT(*) > 1
) AS duplicate_group
    ON duplicate_group.group_id = TRIM(source_order.line_group_id);

UPDATE line_order_group_bindings AS binding
INNER JOIN orders AS source_order ON source_order.case_no = binding.case_no
INNER JOIN (
    SELECT TRIM(line_group_id) AS group_id
    FROM orders
    WHERE line_group_id IS NOT NULL AND TRIM(line_group_id) <> ''
    GROUP BY TRIM(line_group_id)
    HAVING COUNT(*) = 1
) AS unique_group ON unique_group.group_id = TRIM(source_order.line_group_id)
SET
    binding.group_id = unique_group.group_id,
    binding.binding_status = 'bound',
    binding.aggregate_version = 1;

INSERT IGNORE INTO line_order_group_binding_events (
    case_no, action, resulting_group_id, expected_version, resulting_version,
    actor_id, binding_fingerprint, idempotency_key, correlation_id
)
SELECT
    binding.case_no,
    'legacy_imported',
    binding.group_id,
    0,
    1,
    'migration:line-stage-2',
    SHA2(CONCAT_WS('|', binding.case_no, binding.group_id), 256),
    CONCAT('legacy-line-order-group:', binding.case_no),
    CONCAT('legacy-line-order-group:', binding.case_no)
FROM line_order_group_bindings AS binding
WHERE binding.binding_status = 'bound';

DROP TRIGGER IF EXISTS trg_line_order_group_binding_events_before_update;
CREATE TRIGGER trg_line_order_group_binding_events_before_update
BEFORE UPDATE ON line_order_group_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_line_order_group_binding_events_before_delete;
CREATE TRIGGER trg_line_order_group_binding_events_before_delete
BEFORE DELETE ON line_order_group_binding_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'line_order_group_binding_events records cannot be deleted';
