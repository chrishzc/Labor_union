-- File: 1014_historical_baseline_projector_v2.sql
-- Description: 1011 的 additive successor；保存 occurrence state、v2 receipt、
-- active membership snapshot、durable delivery、source checkpoint 與 post-commit readback。
--
-- This artifact is schema-only.  It deliberately does not alter or backfill any
-- 1010/1011 row and does not replace the 1011 tables.

CREATE TABLE IF NOT EXISTS historical_baseline_v2_occurrence_state_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    state_event_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    occurrence_id BIGINT UNSIGNED NOT NULL,
    prior_state_event_id BIGINT UNSIGNED NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    descriptor_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    contract_id VARCHAR(191) NOT NULL,
    contract_version BIGINT UNSIGNED NOT NULL,
    terminal_predicate_id VARCHAR(191) NOT NULL,
    terminal_predicate_version BIGINT UNSIGNED NOT NULL,
    owner_event_identity VARCHAR(191) NOT NULL,
    owner_source_version BIGINT UNSIGNED NOT NULL,
    expected_state_version BIGINT UNSIGNED NOT NULL,
    resulting_state_version BIGINT UNSIGNED NOT NULL,
    state ENUM('opened', 'resolved', 'superseded') NOT NULL,
    owner_binding_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    fresh_readback_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_state_identity (state_event_identity),
    UNIQUE KEY uq_hbp_v2_state_occurrence_version (
        occurrence_id,
        resulting_state_version
    ),
    UNIQUE KEY uq_hbp_v2_state_occurrence_lineage (
        id,
        occurrence_id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version
    ),
    INDEX idx_hbp_v2_state_occurrence (
        occurrence_id,
        resulting_state_version,
        id
    ),
    INDEX idx_hbp_v2_state_owner_event (
        owner_event_identity,
        owner_source_version,
        id
    ),
    CONSTRAINT fk_hbp_v2_state_occurrence
        FOREIGN KEY (
            occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) REFERENCES historical_baseline_occurrences (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_state_prior
        FOREIGN KEY (
            prior_state_event_id,
            occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) REFERENCES historical_baseline_v2_occurrence_state_events (
            id,
            occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_v2_state_hashes
        CHECK (
            state_event_identity REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND descriptor_identity REGEXP '^[0-9a-f]{64}$'
            AND owner_binding_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND fresh_readback_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_v2_state_versions
        CHECK (
            catalog_version > 0
            AND contract_version > 0
            AND terminal_predicate_version > 0
            AND resulting_state_version = expected_state_version + 1
            AND (
                (expected_state_version = 0 AND prior_state_event_id IS NULL)
                OR (expected_state_version > 0 AND prior_state_event_id IS NOT NULL)
            )
        ),
    CONSTRAINT chk_hbp_v2_state_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
            AND CHAR_LENGTH(TRIM(contract_id)) > 0
            AND CHAR_LENGTH(TRIM(terminal_predicate_id)) > 0
            AND CHAR_LENGTH(TRIM(owner_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(reason)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_v2_projector_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    projector_receipt_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_trigger_identity VARCHAR(191) NOT NULL,
    source_trigger_version BIGINT UNSIGNED NOT NULL,
    payload_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    baseline_receipt_id BIGINT UNSIGNED NOT NULL,
    baseline_outbox_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    whole_vector_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    whole_vector_count INT UNSIGNED NOT NULL,
    emitted_occurrence_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    emitted_occurrence_set_count INT UNSIGNED NOT NULL,
    emitted_occurrence_identities JSON NOT NULL,
    active_membership_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    active_membership_set_count INT UNSIGNED NOT NULL,
    umbrella_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    projection_sequence BIGINT UNSIGNED NOT NULL,
    current_alert_fingerprint CHAR(64) NOT NULL,
    expected_readback_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_state ENUM('projected', 'held_active') NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_receipt_identity (projector_receipt_identity),
    UNIQUE KEY uq_hbp_v2_receipt_source_trigger (source_trigger_identity),
    UNIQUE KEY uq_hbp_v2_receipt_idempotency (idempotency_key),
    UNIQUE KEY uq_hbp_v2_receipt_lineage (
        id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version,
        umbrella_identity
    ),
    UNIQUE KEY uq_hbp_v2_receipt_readback_binding (
        id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version,
        umbrella_identity,
        projection_sequence
    ),
    INDEX idx_hbp_v2_receipt_case_sequence (
        case_no,
        projection_sequence,
        id
    ),
    CONSTRAINT fk_hbp_v2_receipt_baseline_event
        FOREIGN KEY (baseline_event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_receipt_baseline_receipt
        FOREIGN KEY (baseline_receipt_id)
        REFERENCES historical_order_operational_baseline_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_receipt_baseline_outbox
        FOREIGN KEY (baseline_outbox_id)
        REFERENCES historical_order_operational_baseline_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_receipt_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_receipt_alert
        FOREIGN KEY (current_alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_v2_receipt_hashes
        CHECK (
            projector_receipt_identity REGEXP '^[0-9a-f]{64}$'
            AND payload_digest REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND whole_vector_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND emitted_occurrence_set_digest REGEXP '^[0-9a-f]{64}$'
            AND active_membership_set_digest REGEXP '^[0-9a-f]{64}$'
            AND umbrella_identity REGEXP '^[0-9a-f]{64}$'
            AND current_alert_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND expected_readback_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_v2_receipt_counts
        CHECK (
            catalog_version > 0
            AND whole_vector_count > 0
            AND emitted_occurrence_set_count >= 0
            AND active_membership_set_count >= 0
            AND projection_sequence > 0
        ),
    CONSTRAINT chk_hbp_v2_receipt_emitted_snapshot
        CHECK (
            JSON_TYPE(emitted_occurrence_identities) = 'ARRAY'
            AND JSON_LENGTH(emitted_occurrence_identities)
                = emitted_occurrence_set_count
        ),
    CONSTRAINT chk_hbp_v2_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(source_trigger_identity)) > 0
            AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_v2_active_membership_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    membership_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    projector_receipt_id BIGINT UNSIGNED NOT NULL,
    umbrella_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    set_ordinal INT UNSIGNED NOT NULL,
    occurrence_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    projection_sequence BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_membership_identity (membership_identity),
    UNIQUE KEY uq_hbp_v2_membership_receipt_ordinal (
        projector_receipt_id,
        set_ordinal
    ),
    UNIQUE KEY uq_hbp_v2_membership_receipt_occurrence (
        projector_receipt_id,
        occurrence_id
    ),
    INDEX idx_hbp_v2_membership_umbrella (
        umbrella_identity,
        projection_sequence,
        set_ordinal
    ),
    INDEX idx_hbp_v2_membership_occurrence (occurrence_id, id),
    CONSTRAINT fk_hbp_v2_membership_receipt
        FOREIGN KEY (
            projector_receipt_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity
        ) REFERENCES historical_baseline_v2_projector_receipts (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_membership_occurrence
        FOREIGN KEY (
            occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) REFERENCES historical_baseline_occurrences (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_v2_membership_hashes
        CHECK (
            membership_identity REGEXP '^[0-9a-f]{64}$'
            AND umbrella_identity REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND set_ordinal > 0
            AND catalog_version > 0
            AND projection_sequence > 0
        ),
    CONSTRAINT chk_hbp_v2_membership_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_v2_projector_deliveries (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    delivery_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_trigger_identity VARCHAR(191) NOT NULL,
    payload_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_kind ENUM('baseline_confirmed', 'owner_repair') NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_event_identity VARCHAR(191) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    partition_key VARCHAR(191) NOT NULL,
    projection_sequence BIGINT UNSIGNED NULL,
    projector_receipt_id BIGINT UNSIGNED NULL,
    delivery_status ENUM(
        'pending',
        'processing',
        'retryable_failed',
        'committed_unverified',
        'processed',
        'dead_letter'
    ) NOT NULL DEFAULT 'pending',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL,
    next_attempt_at TIMESTAMP(6) NULL,
    lease_owner VARCHAR(191) NULL,
    lease_expires_at TIMESTAMP(6) NULL,
    last_error_code VARCHAR(191) NULL,
    last_error_detail VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_delivery_identity (delivery_identity),
    UNIQUE KEY uq_hbp_v2_delivery_trigger (source_trigger_identity),
    INDEX idx_hbp_v2_delivery_claim (
        delivery_status,
        next_attempt_at,
        lease_expires_at,
        id
    ),
    INDEX idx_hbp_v2_delivery_partition (
        source_domain,
        partition_key,
        source_version,
        id
    ),
    INDEX idx_hbp_v2_delivery_receipt (projector_receipt_id),
    CONSTRAINT fk_hbp_v2_delivery_receipt
        FOREIGN KEY (projector_receipt_id)
        REFERENCES historical_baseline_v2_projector_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_v2_delivery_hashes
        CHECK (
            delivery_identity REGEXP '^[0-9a-f]{64}$'
            AND payload_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_v2_delivery_attempts
        CHECK (
            max_attempts > 0
            AND attempt_count <= max_attempts
            AND source_version >= 0
        ),
    CONSTRAINT chk_hbp_v2_delivery_text
        CHECK (
            CHAR_LENGTH(TRIM(source_trigger_identity)) > 0
            AND CHAR_LENGTH(TRIM(source_domain)) > 0
            AND CHAR_LENGTH(TRIM(source_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(partition_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_v2_source_checkpoints (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    checkpoint_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_domain VARCHAR(100) NOT NULL,
    source_stream VARCHAR(191) NOT NULL,
    partition_key VARCHAR(191) NOT NULL,
    last_source_event_identity VARCHAR(191) NULL,
    last_source_version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    last_projection_sequence BIGINT UNSIGNED NOT NULL DEFAULT 0,
    checkpoint_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_checkpoint_identity (checkpoint_identity),
    UNIQUE KEY uq_hbp_v2_checkpoint_partition (
        source_domain,
        source_stream,
        partition_key
    ),
    INDEX idx_hbp_v2_checkpoint_progress (
        source_domain,
        source_stream,
        last_source_version,
        last_projection_sequence,
        id
    ),
    CONSTRAINT chk_hbp_v2_checkpoint_hash
        CHECK (checkpoint_identity REGEXP '^[0-9a-f]{64}$'
            AND checkpoint_fingerprint REGEXP '^[0-9a-f]{64}$'),
    CONSTRAINT chk_hbp_v2_checkpoint_versions
        CHECK (last_source_version >= 0 AND last_projection_sequence >= 0),
    CONSTRAINT chk_hbp_v2_checkpoint_text
        CHECK (
            CHAR_LENGTH(TRIM(source_domain)) > 0
            AND CHAR_LENGTH(TRIM(source_stream)) > 0
            AND CHAR_LENGTH(TRIM(partition_key)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_v2_post_commit_readbacks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    readback_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    projector_receipt_id BIGINT UNSIGNED NOT NULL,
    delivery_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    umbrella_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    projection_sequence BIGINT UNSIGNED NOT NULL,
    readback_attempt INT UNSIGNED NOT NULL,
    expected_readback_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actual_readback_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_emitted_occurrence_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_emitted_occurrence_set_count INT UNSIGNED NULL,
    actual_active_membership_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_active_membership_set_count INT UNSIGNED NULL,
    actual_state_event_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_successor_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_workflow_event_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    actual_current_alert_fingerprint CHAR(64) NULL,
    readback_result ENUM('exact', 'mismatch', 'unknown') NOT NULL,
    error_code VARCHAR(191) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_v2_readback_identity (readback_identity),
    UNIQUE KEY uq_hbp_v2_readback_receipt_attempt (
        projector_receipt_id,
        readback_attempt
    ),
    INDEX idx_hbp_v2_readback_delivery (delivery_id, id),
    INDEX idx_hbp_v2_readback_case_sequence (
        case_no,
        projection_sequence,
        id
    ),
    CONSTRAINT fk_hbp_v2_readback_receipt
        FOREIGN KEY (
            projector_receipt_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity,
            projection_sequence
        ) REFERENCES historical_baseline_v2_projector_receipts (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity,
            projection_sequence
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_readback_delivery
        FOREIGN KEY (delivery_id)
        REFERENCES historical_baseline_v2_projector_deliveries(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_v2_readback_alert
        FOREIGN KEY (actual_current_alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_v2_readback_hashes
        CHECK (
            readback_identity REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND umbrella_identity REGEXP '^[0-9a-f]{64}$'
            AND expected_readback_digest REGEXP '^[0-9a-f]{64}$'
            AND (
                actual_readback_digest IS NULL
                OR actual_readback_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_emitted_occurrence_set_digest IS NULL
                OR actual_emitted_occurrence_set_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_active_membership_set_digest IS NULL
                OR actual_active_membership_set_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_state_event_set_digest IS NULL
                OR actual_state_event_set_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_successor_set_digest IS NULL
                OR actual_successor_set_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_workflow_event_set_digest IS NULL
                OR actual_workflow_event_set_digest REGEXP '^[0-9a-f]{64}$'
            )
            AND (
                actual_current_alert_fingerprint IS NULL
                OR actual_current_alert_fingerprint REGEXP '^[0-9a-f]{64}$'
            )
        ),
    CONSTRAINT chk_hbp_v2_readback_result
        CHECK (
            readback_attempt > 0
            AND catalog_version > 0
            AND projection_sequence > 0
            AND (
                (
                    readback_result = 'exact'
                    AND actual_readback_digest IS NOT NULL
                    AND actual_emitted_occurrence_set_digest IS NOT NULL
                    AND actual_emitted_occurrence_set_count IS NOT NULL
                    AND actual_active_membership_set_digest IS NOT NULL
                    AND actual_active_membership_set_count IS NOT NULL
                    AND actual_state_event_set_digest IS NOT NULL
                    AND actual_successor_set_digest IS NOT NULL
                    AND actual_workflow_event_set_digest IS NOT NULL
                    AND actual_current_alert_fingerprint IS NOT NULL
                    AND error_code IS NULL
                )
                OR (
                    readback_result IN ('mismatch', 'unknown')
                    AND error_code IS NOT NULL
                    AND CHAR_LENGTH(TRIM(error_code)) > 0
                )
            )
        ),
    CONSTRAINT chk_hbp_v2_readback_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Occurrence state, receipts, membership rows and post-commit readbacks are
-- append-only. Delivery/checkpoint metadata may advance, but their identities
-- and source partition cannot be rewritten or deleted.
DROP TRIGGER IF EXISTS trg_hbp_v2_state_before_update;
CREATE TRIGGER trg_hbp_v2_state_before_update
BEFORE UPDATE ON historical_baseline_v2_occurrence_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_occurrence_state_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_v2_state_before_delete;
CREATE TRIGGER trg_hbp_v2_state_before_delete
BEFORE DELETE ON historical_baseline_v2_occurrence_state_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_occurrence_state_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_v2_receipt_before_update;
CREATE TRIGGER trg_hbp_v2_receipt_before_update
BEFORE UPDATE ON historical_baseline_v2_projector_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_projector_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_v2_receipt_before_delete;
CREATE TRIGGER trg_hbp_v2_receipt_before_delete
BEFORE DELETE ON historical_baseline_v2_projector_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_projector_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_v2_membership_before_update;
CREATE TRIGGER trg_hbp_v2_membership_before_update
BEFORE UPDATE ON historical_baseline_v2_active_membership_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_active_membership_snapshots records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_v2_membership_before_delete;
CREATE TRIGGER trg_hbp_v2_membership_before_delete
BEFORE DELETE ON historical_baseline_v2_active_membership_snapshots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_active_membership_snapshots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_v2_delivery_before_update;
CREATE TRIGGER trg_hbp_v2_delivery_before_update
BEFORE UPDATE ON historical_baseline_v2_projector_deliveries
FOR EACH ROW SET NEW.delivery_identity = IF(
    OLD.delivery_identity <=> NEW.delivery_identity
    AND OLD.source_trigger_identity <=> NEW.source_trigger_identity
    AND OLD.payload_digest <=> NEW.payload_digest
    AND OLD.source_kind <=> NEW.source_kind
    AND OLD.source_domain <=> NEW.source_domain
    AND OLD.source_event_identity <=> NEW.source_event_identity
    AND OLD.source_version <=> NEW.source_version
    AND OLD.partition_key <=> NEW.partition_key,
    NEW.delivery_identity,
    NULL
);

DROP TRIGGER IF EXISTS trg_hbp_v2_delivery_before_delete;
CREATE TRIGGER trg_hbp_v2_delivery_before_delete
BEFORE DELETE ON historical_baseline_v2_projector_deliveries
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_projector_deliveries records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_v2_checkpoint_before_update;
CREATE TRIGGER trg_hbp_v2_checkpoint_before_update
BEFORE UPDATE ON historical_baseline_v2_source_checkpoints
FOR EACH ROW SET NEW.checkpoint_identity = IF(
    OLD.checkpoint_identity <=> NEW.checkpoint_identity
    AND OLD.source_domain <=> NEW.source_domain
    AND OLD.source_stream <=> NEW.source_stream
    AND OLD.partition_key <=> NEW.partition_key
    AND OLD.created_at <=> NEW.created_at,
    NEW.checkpoint_identity,
    NULL
);

DROP TRIGGER IF EXISTS trg_hbp_v2_checkpoint_before_delete;
CREATE TRIGGER trg_hbp_v2_checkpoint_before_delete
BEFORE DELETE ON historical_baseline_v2_source_checkpoints
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_source_checkpoints records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_v2_readback_before_update;
CREATE TRIGGER trg_hbp_v2_readback_before_update
BEFORE UPDATE ON historical_baseline_v2_post_commit_readbacks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_post_commit_readbacks records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_v2_readback_before_delete;
CREATE TRIGGER trg_hbp_v2_readback_before_delete
BEFORE DELETE ON historical_baseline_v2_post_commit_readbacks
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_v2_post_commit_readbacks records cannot be deleted';
