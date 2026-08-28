-- File: 1011_historical_baseline_projector.sql
-- Description: 保存歷史基準 projector 的不可變 occurrence、umbrella membership、successor 與 receipt。

CREATE TABLE IF NOT EXISTS historical_baseline_occurrences (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurrence_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    baseline_receipt_id BIGINT UNSIGNED NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    descriptor_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    contract_id VARCHAR(191) NOT NULL,
    contract_version BIGINT UNSIGNED NOT NULL,
    step_number TINYINT UNSIGNED NOT NULL,
    owner_domain VARCHAR(100) NOT NULL,
    root_identity_kind VARCHAR(191) NOT NULL,
    root_identity_path VARCHAR(500) NOT NULL,
    terminal_predicate_id VARCHAR(191) NOT NULL,
    terminal_predicate_version BIGINT UNSIGNED NOT NULL,
    repair_target VARCHAR(191) NOT NULL,
    repair_capability VARCHAR(191) NOT NULL,
    observation_variant ENUM('available', 'unavailable') NOT NULL,
    observation_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    observed_root_identity VARCHAR(191) NULL,
    owner_source_event_identity VARCHAR(191) NULL,
    owner_source_version BIGINT UNSIGNED NULL,
    terminal_result TINYINT(1) NULL,
    unavailable_code VARCHAR(191) NULL,
    owner_binding_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_occurrence_identity (occurrence_identity),
    UNIQUE KEY uq_hbp_occurrence_observation (
        baseline_event_id,
        catalog_identity,
        descriptor_identity,
        observation_identity
    ),
    UNIQUE KEY uq_hbp_occurrence_membership_lineage (
        id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version
    ),
    UNIQUE KEY uq_hbp_occurrence_successor_lineage (
        id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version,
        descriptor_identity,
        contract_id,
        contract_version,
        terminal_predicate_id,
        terminal_predicate_version,
        owner_source_version
    ),
    INDEX idx_hbp_occurrence_case_catalog (
        case_no,
        catalog_version,
        step_number,
        id
    ),
    INDEX idx_hbp_occurrence_contract (
        contract_id,
        contract_version,
        owner_source_version
    ),
    CONSTRAINT fk_hbp_occurrence_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_occurrence_baseline_event
        FOREIGN KEY (baseline_event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_occurrence_baseline_receipt
        FOREIGN KEY (baseline_receipt_id)
        REFERENCES historical_order_operational_baseline_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_occurrence_hashes
        CHECK (
            occurrence_identity REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND descriptor_identity REGEXP '^[0-9a-f]{64}$'
            AND observation_identity REGEXP '^[0-9a-f]{64}$'
            AND owner_binding_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_occurrence_versions
        CHECK (
            catalog_version > 0
            AND contract_version > 0
            AND terminal_predicate_version > 0
            AND step_number BETWEEN 1 AND 11
        ),
    CONSTRAINT chk_hbp_occurrence_observation
        CHECK (
            (
                observation_variant = 'available'
                AND observed_root_identity IS NOT NULL
                AND CHAR_LENGTH(TRIM(observed_root_identity)) > 0
                AND owner_source_event_identity IS NOT NULL
                AND CHAR_LENGTH(TRIM(owner_source_event_identity)) > 0
                AND owner_source_version IS NOT NULL
                AND terminal_result IS NOT NULL
                AND terminal_result IN (0, 1)
                AND unavailable_code IS NULL
            )
            OR (
                observation_variant = 'unavailable'
                AND observed_root_identity IS NULL
                AND owner_source_event_identity IS NULL
                AND owner_source_version IS NULL
                AND terminal_result IS NULL
                AND unavailable_code IS NOT NULL
                AND CHAR_LENGTH(TRIM(unavailable_code)) > 0
            )
        ),
    CONSTRAINT chk_hbp_occurrence_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
            AND CHAR_LENGTH(TRIM(contract_id)) > 0
            AND CHAR_LENGTH(TRIM(owner_domain)) > 0
            AND CHAR_LENGTH(TRIM(root_identity_kind)) > 0
            AND CHAR_LENGTH(TRIM(root_identity_path)) > 0
            AND CHAR_LENGTH(TRIM(terminal_predicate_id)) > 0
            AND CHAR_LENGTH(TRIM(repair_target)) > 0
            AND CHAR_LENGTH(TRIM(repair_capability)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_projector_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    projector_receipt_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_intent_key VARCHAR(191) NOT NULL,
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
    occurrence_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    occurrence_set_count INT UNSIGNED NOT NULL,
    umbrella_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    result_state ENUM('projected', 'held_active') NOT NULL,
    post_commit_readback_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_projector_receipt_identity (projector_receipt_identity),
    UNIQUE KEY uq_hbp_projector_source_intent (source_intent_key),
    UNIQUE KEY uq_hbp_projector_idempotency (idempotency_key),
    UNIQUE KEY uq_hbp_projector_membership_lineage (
        id,
        case_no,
        order_identity,
        baseline_event_id,
        catalog_identity,
        catalog_version,
        umbrella_identity
    ),
    INDEX idx_hbp_projector_case_catalog (
        case_no,
        catalog_version,
        id
    ),
    CONSTRAINT fk_hbp_projector_baseline_event
        FOREIGN KEY (baseline_event_id)
        REFERENCES historical_order_operational_baseline_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_projector_baseline_receipt
        FOREIGN KEY (baseline_receipt_id)
        REFERENCES historical_order_operational_baseline_receipts(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_projector_baseline_outbox
        FOREIGN KEY (baseline_outbox_id)
        REFERENCES historical_order_operational_baseline_outbox(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_projector_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_projector_hashes
        CHECK (
            projector_receipt_identity REGEXP '^[0-9a-f]{64}$'
            AND payload_digest REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND whole_vector_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND occurrence_set_digest REGEXP '^[0-9a-f]{64}$'
            AND umbrella_identity REGEXP '^[0-9a-f]{64}$'
            AND post_commit_readback_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_projector_counts
        CHECK (
            catalog_version > 0
            AND whole_vector_count > 0
            AND occurrence_set_count >= 0
        ),
    CONSTRAINT chk_hbp_projector_text
        CHECK (
            source_intent_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_umbrella_memberships (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    membership_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    umbrella_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    projector_receipt_id BIGINT UNSIGNED NOT NULL,
    set_ordinal INT UNSIGNED NOT NULL,
    occurrence_id BIGINT UNSIGNED NOT NULL,
    anomaly_alert_fingerprint CHAR(64) NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    order_identity VARCHAR(191) NOT NULL,
    baseline_event_id BIGINT UNSIGNED NOT NULL,
    catalog_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    catalog_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_membership_identity (membership_identity),
    UNIQUE KEY uq_hbp_membership_occurrence (occurrence_id),
    UNIQUE KEY uq_hbp_membership_receipt_ordinal (
        projector_receipt_id,
        set_ordinal
    ),
    INDEX idx_hbp_membership_umbrella (
        umbrella_identity,
        catalog_version,
        occurrence_id
    ),
    INDEX idx_hbp_membership_alert (anomaly_alert_fingerprint),
    CONSTRAINT fk_hbp_membership_occurrence_lineage
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
    CONSTRAINT fk_hbp_membership_receipt_lineage
        FOREIGN KEY (
            projector_receipt_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity
        ) REFERENCES historical_baseline_projector_receipts (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            umbrella_identity
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_membership_alert
        FOREIGN KEY (anomaly_alert_fingerprint)
        REFERENCES anomaly_current_alerts(fingerprint)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_membership_hashes
        CHECK (
            membership_identity REGEXP '^[0-9a-f]{64}$'
            AND umbrella_identity REGEXP '^[0-9a-f]{64}$'
            AND anomaly_alert_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_membership_identity_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
            AND catalog_version > 0
            AND set_ordinal > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS historical_baseline_successors (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    successor_relation_identity CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    predecessor_occurrence_id BIGINT UNSIGNED NOT NULL,
    successor_occurrence_id BIGINT UNSIGNED NOT NULL,
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
    owner_event_identity VARCHAR(191) NOT NULL,
    prior_owner_source_version BIGINT UNSIGNED NOT NULL,
    new_owner_source_version BIGINT UNSIGNED NOT NULL,
    terminal_predicate_id VARCHAR(191) NOT NULL,
    terminal_predicate_version BIGINT UNSIGNED NOT NULL,
    fresh_readback_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_hbp_successor_identity (successor_relation_identity),
    UNIQUE KEY uq_hbp_successor_predecessor (predecessor_occurrence_id),
    UNIQUE KEY uq_hbp_successor_occurrence (successor_occurrence_id),
    INDEX idx_hbp_successor_case_contract (
        case_no,
        contract_id,
        contract_version,
        new_owner_source_version
    ),
    CONSTRAINT fk_hbp_successor_predecessor_lineage
        FOREIGN KEY (
            predecessor_occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            descriptor_identity,
            contract_id,
            contract_version,
            terminal_predicate_id,
            terminal_predicate_version,
            prior_owner_source_version
        ) REFERENCES historical_baseline_occurrences (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            descriptor_identity,
            contract_id,
            contract_version,
            terminal_predicate_id,
            terminal_predicate_version,
            owner_source_version
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hbp_successor_occurrence_lineage
        FOREIGN KEY (
            successor_occurrence_id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            descriptor_identity,
            contract_id,
            contract_version,
            terminal_predicate_id,
            terminal_predicate_version,
            new_owner_source_version
        ) REFERENCES historical_baseline_occurrences (
            id,
            case_no,
            order_identity,
            baseline_event_id,
            catalog_identity,
            catalog_version,
            descriptor_identity,
            contract_id,
            contract_version,
            terminal_predicate_id,
            terminal_predicate_version,
            owner_source_version
        ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hbp_successor_hashes
        CHECK (
            successor_relation_identity REGEXP '^[0-9a-f]{64}$'
            AND catalog_identity REGEXP '^[0-9a-f]{64}$'
            AND descriptor_identity REGEXP '^[0-9a-f]{64}$'
            AND fresh_readback_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_hbp_successor_lineage
        CHECK (
            predecessor_occurrence_id <> successor_occurrence_id
            AND new_owner_source_version > prior_owner_source_version
            AND catalog_version > 0
            AND contract_version > 0
            AND terminal_predicate_version > 0
        ),
    CONSTRAINT chk_hbp_successor_text
        CHECK (
            CHAR_LENGTH(TRIM(case_no)) > 0
            AND CHAR_LENGTH(TRIM(order_identity)) > 0
            AND CHAR_LENGTH(TRIM(contract_id)) > 0
            AND CHAR_LENGTH(TRIM(owner_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(terminal_predicate_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_hbp_occurrences_before_insert;
CREATE TRIGGER trg_hbp_occurrences_before_insert
BEFORE INSERT ON historical_baseline_occurrences
FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM historical_order_operational_baseline_events AS event
        INNER JOIN historical_order_operational_baseline_receipts AS receipt
            ON receipt.event_id = event.id
        WHERE event.id = NEW.baseline_event_id
          AND receipt.id = NEW.baseline_receipt_id
          AND event.case_no = NEW.case_no
          AND event.order_identity = NEW.order_identity
    ),
    NEW.case_no,
    NULL
);

DROP TRIGGER IF EXISTS trg_hbp_projector_receipts_before_insert;
CREATE TRIGGER trg_hbp_projector_receipts_before_insert
BEFORE INSERT ON historical_baseline_projector_receipts
FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM historical_order_operational_baseline_events AS event
        INNER JOIN historical_order_operational_baseline_receipts AS receipt
            ON receipt.event_id = event.id
        INNER JOIN historical_order_operational_baseline_outbox AS outbox
            ON outbox.event_id = event.id
           AND outbox.receipt_id = receipt.id
        WHERE event.id = NEW.baseline_event_id
          AND receipt.id = NEW.baseline_receipt_id
          AND outbox.id = NEW.baseline_outbox_id
          AND outbox.intent_key = NEW.source_intent_key
          AND event.case_no = NEW.case_no
          AND event.order_identity = NEW.order_identity
    ),
    NEW.case_no,
    NULL
);

DROP TRIGGER IF EXISTS trg_hbp_memberships_before_insert;
CREATE TRIGGER trg_hbp_memberships_before_insert
BEFORE INSERT ON historical_baseline_umbrella_memberships
FOR EACH ROW SET NEW.anomaly_alert_fingerprint = IF(
    EXISTS(
        SELECT 1
        FROM anomaly_current_alerts AS alert
        WHERE alert.fingerprint = NEW.anomaly_alert_fingerprint
          AND alert.source_identity = NEW.umbrella_identity
    ),
    NEW.anomaly_alert_fingerprint,
    NULL
);

DROP TRIGGER IF EXISTS trg_hbp_occurrences_before_update;
CREATE TRIGGER trg_hbp_occurrences_before_update
BEFORE UPDATE ON historical_baseline_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_occurrences records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_occurrences_before_delete;
CREATE TRIGGER trg_hbp_occurrences_before_delete
BEFORE DELETE ON historical_baseline_occurrences
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_occurrences records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_memberships_before_update;
CREATE TRIGGER trg_hbp_memberships_before_update
BEFORE UPDATE ON historical_baseline_umbrella_memberships
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_umbrella_memberships records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_memberships_before_delete;
CREATE TRIGGER trg_hbp_memberships_before_delete
BEFORE DELETE ON historical_baseline_umbrella_memberships
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_umbrella_memberships records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_successors_before_update;
CREATE TRIGGER trg_hbp_successors_before_update
BEFORE UPDATE ON historical_baseline_successors
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_successors records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_successors_before_delete;
CREATE TRIGGER trg_hbp_successors_before_delete
BEFORE DELETE ON historical_baseline_successors
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_successors records cannot be deleted';

DROP TRIGGER IF EXISTS trg_hbp_projector_receipts_before_update;
CREATE TRIGGER trg_hbp_projector_receipts_before_update
BEFORE UPDATE ON historical_baseline_projector_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_projector_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_hbp_projector_receipts_before_delete;
CREATE TRIGGER trg_hbp_projector_receipts_before_delete
BEFORE DELETE ON historical_baseline_projector_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'historical_baseline_projector_receipts records cannot be deleted';
