-- File: 1012_service_before_replacement.sql
-- Description: 保存服務前換人的不可變事件、逐 root disposition、successor binding、receipt 與內部 outbox。

CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    replacement_event_identity VARCHAR(191) NOT NULL,
    prior_replacement_event_id BIGINT UNSIGNED NULL,
    case_no VARCHAR(50) NOT NULL,
    scenario ENUM('R-01', 'R-02', 'R-03', 'R-04', 'R-07') NOT NULL,
    prior_generation_id BIGINT NOT NULL,
    replacement_generation_id BIGINT NOT NULL,
    prior_generation_identity VARCHAR(191) NOT NULL,
    replacement_generation_identity VARCHAR(191) NOT NULL,
    prior_event_identity VARCHAR(191) NOT NULL,
    expected_aggregate_version BIGINT UNSIGNED NOT NULL,
    resulting_aggregate_version BIGINT UNSIGNED NOT NULL,
    expected_generation_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_version BIGINT UNSIGNED NOT NULL,
    expected_event_version BIGINT UNSIGNED NOT NULL,
    resulting_event_version BIGINT UNSIGNED NOT NULL,
    zero_service_proof_identity VARCHAR(191) NOT NULL,
    zero_service_proof_owner ENUM(
        'scheduling_official_service_projection'
    ) NOT NULL,
    zero_service_proof_contract_version SMALLINT UNSIGNED NOT NULL,
    zero_service_source_projection_identity VARCHAR(191) NOT NULL,
    zero_service_source_projection_version BIGINT UNSIGNED NOT NULL,
    zero_service_proof_version BIGINT UNSIGNED NOT NULL,
    zero_service_proof_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    official_service_day_count INT UNSIGNED NOT NULL,
    replacement_reason VARCHAR(500) NOT NULL,
    reason_evidence_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    command_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor_id VARCHAR(191) NOT NULL,
    capability_atom VARCHAR(191) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    correlation_id VARCHAR(191) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_before_replacement_event_identity (
        replacement_event_identity
    ),
    UNIQUE KEY uq_service_before_replacement_event_idempotency (
        idempotency_key
    ),
    UNIQUE KEY uq_service_before_replacement_event_prior (
        prior_replacement_event_id
    ),
    UNIQUE KEY uq_service_before_replacement_event_generation (
        replacement_generation_id
    ),
    UNIQUE KEY uq_service_before_replacement_event_successor_binding (
        id,
        case_no,
        replacement_generation_id,
        scenario,
        expected_generation_version,
        expected_event_version
    ),
    UNIQUE KEY uq_service_before_replacement_event_version_binding (
        id,
        case_no,
        resulting_aggregate_version,
        resulting_generation_version,
        resulting_event_version
    ),
    UNIQUE KEY uq_service_before_replacement_case_event_version (
        case_no,
        resulting_event_version
    ),
    INDEX idx_service_before_replacement_prior_event (
        prior_replacement_event_id
    ),
    INDEX idx_service_before_replacement_case_versions (
        case_no,
        resulting_aggregate_version,
        resulting_generation_version,
        id
    ),
    CONSTRAINT fk_service_before_replacement_prior_event
        FOREIGN KEY (
            prior_replacement_event_id,
            case_no,
            expected_aggregate_version,
            expected_generation_version,
            expected_event_version
        )
        REFERENCES scheduling_service_before_replacement_events(
            id,
            case_no,
            resulting_aggregate_version,
            resulting_generation_version,
            resulting_event_version
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_case
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_prior_generation
        FOREIGN KEY (prior_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_generation
        FOREIGN KEY (replacement_generation_id, case_no)
        REFERENCES scheduling_generations(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_service_before_replacement_distinct_generation
        CHECK (replacement_generation_id <> prior_generation_id),
    CONSTRAINT chk_service_before_replacement_strict_versions
        CHECK (
            resulting_aggregate_version > expected_aggregate_version
            AND resulting_generation_version > expected_generation_version
            AND resulting_event_version > expected_event_version
        ),
    CONSTRAINT chk_service_before_replacement_zero_service
        CHECK (
            zero_service_proof_contract_version = 1
            AND zero_service_proof_version > 0
            AND zero_service_source_projection_version = zero_service_proof_version
            AND official_service_day_count = 0
        ),
    CONSTRAINT chk_service_before_replacement_digests
        CHECK (
            zero_service_proof_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND reason_evidence_digest REGEXP '^[0-9a-f]{64}$'
            AND command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_service_before_replacement_text
        CHECK (
            CHAR_LENGTH(TRIM(replacement_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(prior_generation_identity)) > 0
            AND CHAR_LENGTH(TRIM(replacement_generation_identity)) > 0
            AND CHAR_LENGTH(TRIM(prior_event_identity)) > 0
            AND CHAR_LENGTH(TRIM(zero_service_proof_identity)) > 0
            AND CHAR_LENGTH(
                TRIM(zero_service_source_projection_identity)
            ) > 0
            AND CHAR_LENGTH(TRIM(replacement_reason)) > 0
            AND CHAR_LENGTH(TRIM(actor_id)) > 0
            AND CHAR_LENGTH(TRIM(capability_atom)) > 0
            AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND CHAR_LENGTH(TRIM(correlation_id)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_roots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    replacement_event_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    root_identity VARCHAR(191) NOT NULL,
    owner_domain ENUM('scheduling', 'matching') NOT NULL,
    root_kind ENUM(
        'candidate_binding',
        'willingness',
        'matching_plan',
        'matching_segment',
        'matching_reply',
        'recipient_confirmation',
        'waiting_lock',
        'commitment',
        'signback',
        'recipient_binding',
        'effective_generation',
        'assignment',
        'official_schedule',
        'successor_round'
    ) NOT NULL,
    disposition ENUM('retained', 'superseded', 'created') NOT NULL,
    canonical_ordinal INT UNSIGNED NOT NULL,
    owner_descriptor_identity VARCHAR(191) NOT NULL,
    owner_descriptor_version BIGINT UNSIGNED NOT NULL,
    owner_descriptor_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_before_replacement_root_identity (
        replacement_event_id,
        root_identity
    ),
    UNIQUE KEY uq_service_before_replacement_root_ordinal (
        replacement_event_id,
        disposition,
        canonical_ordinal
    ),
    INDEX idx_service_before_replacement_root_case (
        case_no,
        disposition,
        root_kind,
        id
    ),
    CONSTRAINT fk_service_before_replacement_root_event
        FOREIGN KEY (replacement_event_id, case_no)
        REFERENCES scheduling_service_before_replacement_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_service_before_replacement_root_ordinal
        CHECK (canonical_ordinal > 0),
    CONSTRAINT chk_service_before_replacement_root_owner_kind
        CHECK (
            (
                owner_domain = 'matching'
                AND root_kind IN (
                    'candidate_binding',
                    'willingness',
                    'matching_plan',
                    'matching_segment',
                    'matching_reply',
                    'recipient_confirmation',
                    'successor_round'
                )
            )
            OR (
                owner_domain = 'scheduling'
                AND root_kind IN (
                    'waiting_lock',
                    'commitment',
                    'signback',
                    'recipient_binding',
                    'effective_generation',
                    'assignment',
                    'official_schedule'
                )
            )
        ),
    CONSTRAINT chk_service_before_replacement_root_descriptor
        CHECK (
            CHAR_LENGTH(TRIM(owner_descriptor_identity)) > 0
            AND owner_descriptor_version > 0
            AND owner_descriptor_fingerprint REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_service_before_replacement_root_text
        CHECK (
            CHAR_LENGTH(TRIM(root_identity)) > 0
            AND root_identity NOT REGEXP '[[:cntrl:]]'
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_successors (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    replacement_event_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    replacement_generation_id BIGINT NOT NULL,
    matching_package_lineage_id BIGINT UNSIGNED NOT NULL,
    matching_event_id BIGINT UNSIGNED NOT NULL,
    successor_package_identity VARCHAR(191) NOT NULL,
    successor_round_identity VARCHAR(191) NOT NULL,
    successor_matching_event_identity VARCHAR(191) NOT NULL,
    scenario ENUM('R-01', 'R-02', 'R-03', 'R-04', 'R-07') NOT NULL,
    expected_generation_version BIGINT UNSIGNED NOT NULL,
    expected_event_version BIGINT UNSIGNED NOT NULL,
    candidate_count INT UNSIGNED NOT NULL,
    zero_candidate_disposition ENUM('blocked_no_candidate') NULL,
    reuse_proof_variant ENUM('not_reused', 'candidate_pool_reused') NOT NULL,
    reuse_pool_identity VARCHAR(191) NULL,
    reuse_round_identity VARCHAR(191) NULL,
    reuse_coverage_version BIGINT UNSIGNED NULL,
    reuse_availability_version BIGINT UNSIGNED NULL,
    reuse_willingness_version BIGINT UNSIGNED NULL,
    reuse_candidate_identity VARCHAR(191) NULL,
    reuse_accepted_candidate TINYINT(1) NULL,
    reuse_proof_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NULL,
    resume_step ENUM('step_2', 'step_3', 'step_4') NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_before_replacement_successor_event (
        replacement_event_id
    ),
    UNIQUE KEY uq_service_before_replacement_successor_round (
        successor_round_identity
    ),
    UNIQUE KEY uq_service_before_replacement_successor_binding (
        id,
        replacement_event_id,
        case_no
    ),
    INDEX idx_service_before_replacement_successor_package (
        matching_package_lineage_id,
        matching_event_id
    ),
    CONSTRAINT fk_service_before_replacement_successor_owner_event
        FOREIGN KEY (
            replacement_event_id,
            case_no,
            replacement_generation_id,
            scenario,
            expected_generation_version,
            expected_event_version
        )
        REFERENCES scheduling_service_before_replacement_events(
            id,
            case_no,
            replacement_generation_id,
            scenario,
            expected_generation_version,
            expected_event_version
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_successor_package
        FOREIGN KEY (matching_package_lineage_id)
        REFERENCES matching_coordination_package_lineage(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_successor_matching_event
        FOREIGN KEY (matching_event_id)
        REFERENCES matching_coordination_events(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_service_before_replacement_successor_r07
        CHECK (
            (
                scenario = 'R-07'
                AND candidate_count = 0
                AND zero_candidate_disposition = 'blocked_no_candidate'
                AND reuse_proof_variant = 'not_reused'
                AND resume_step = 'step_2'
            )
            OR (
                scenario <> 'R-07'
                AND zero_candidate_disposition IS NULL
            )
        ),
    CONSTRAINT chk_service_before_replacement_successor_reuse
        CHECK (
            (
                reuse_proof_variant = 'not_reused'
                AND reuse_pool_identity IS NULL
                AND reuse_round_identity IS NULL
                AND reuse_coverage_version IS NULL
                AND reuse_availability_version IS NULL
                AND reuse_willingness_version IS NULL
                AND reuse_candidate_identity IS NULL
                AND reuse_accepted_candidate IS NULL
                AND reuse_proof_fingerprint IS NULL
                AND resume_step = 'step_2'
            )
            OR (
                reuse_proof_variant = 'candidate_pool_reused'
                AND reuse_round_identity = successor_round_identity
                AND CHAR_LENGTH(TRIM(reuse_pool_identity)) > 0
                AND reuse_coverage_version IS NOT NULL
                AND reuse_availability_version IS NOT NULL
                AND reuse_willingness_version IS NOT NULL
                AND CHAR_LENGTH(TRIM(reuse_candidate_identity)) > 0
                AND reuse_accepted_candidate IN (0, 1)
                AND reuse_proof_fingerprint REGEXP '^[0-9a-f]{64}$'
                AND (
                    (
                        reuse_accepted_candidate = 0
                        AND resume_step = 'step_3'
                    )
                    OR (
                        reuse_accepted_candidate = 1
                        AND resume_step = 'step_4'
                    )
                )
            )
        ),
    CONSTRAINT chk_service_before_replacement_successor_text
        CHECK (
            CHAR_LENGTH(TRIM(successor_package_identity)) > 0
            AND CHAR_LENGTH(TRIM(successor_round_identity)) > 0
            AND CHAR_LENGTH(TRIM(successor_matching_event_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    receipt_identity VARCHAR(191) NOT NULL,
    replacement_event_id BIGINT UNSIGNED NOT NULL,
    successor_binding_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    root_set_digest_contract ENUM('sha256_newline_v1') NOT NULL,
    command_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    preview_fingerprint CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    retained_root_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    retained_root_count INT UNSIGNED NOT NULL,
    superseded_root_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    superseded_root_count INT UNSIGNED NOT NULL,
    created_root_set_digest CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    created_root_count INT UNSIGNED NOT NULL,
    resulting_aggregate_version BIGINT UNSIGNED NOT NULL,
    resulting_generation_version BIGINT UNSIGNED NOT NULL,
    resulting_event_version BIGINT UNSIGNED NOT NULL,
    outbox_identity VARCHAR(191) NOT NULL,
    result_state ENUM('applied') NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_before_replacement_receipt_identity (
        receipt_identity
    ),
    UNIQUE KEY uq_service_before_replacement_receipt_event (
        replacement_event_id
    ),
    UNIQUE KEY uq_service_before_replacement_receipt_successor (
        successor_binding_id
    ),
    UNIQUE KEY uq_service_before_replacement_receipt_idempotency (
        idempotency_key
    ),
    UNIQUE KEY uq_service_before_replacement_receipt_outbox (
        outbox_identity
    ),
    UNIQUE KEY uq_service_before_replacement_receipt_binding (
        id,
        replacement_event_id,
        case_no
    ),
    CONSTRAINT fk_service_before_replacement_receipt_event
        FOREIGN KEY (
            replacement_event_id,
            case_no,
            resulting_aggregate_version,
            resulting_generation_version,
            resulting_event_version
        )
        REFERENCES scheduling_service_before_replacement_events(
            id,
            case_no,
            resulting_aggregate_version,
            resulting_generation_version,
            resulting_event_version
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_receipt_successor
        FOREIGN KEY (successor_binding_id, replacement_event_id, case_no)
        REFERENCES scheduling_service_before_replacement_successors(
            id,
            replacement_event_id,
            case_no
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_service_before_replacement_receipt_digests
        CHECK (
            command_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND preview_fingerprint REGEXP '^[0-9a-f]{64}$'
            AND retained_root_set_digest REGEXP '^[0-9a-f]{64}$'
            AND superseded_root_set_digest REGEXP '^[0-9a-f]{64}$'
            AND created_root_set_digest REGEXP '^[0-9a-f]{64}$'
        ),
    CONSTRAINT chk_service_before_replacement_receipt_versions
        CHECK (
            resulting_aggregate_version > 0
            AND resulting_generation_version > 0
            AND resulting_event_version > 0
        ),
    CONSTRAINT chk_service_before_replacement_receipt_text
        CHECK (
            CHAR_LENGTH(TRIM(receipt_identity)) > 0
            AND idempotency_key REGEXP '^[a-z0-9][a-z0-9._:-]{0,190}$'
            AND CHAR_LENGTH(TRIM(outbox_identity)) > 0
        )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scheduling_service_before_replacement_outbox (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    replacement_event_id BIGINT UNSIGNED NOT NULL,
    receipt_id BIGINT UNSIGNED NOT NULL,
    case_no VARCHAR(50) NOT NULL,
    outbox_identity VARCHAR(191) NOT NULL,
    intent_type ENUM('successor_projection_readback_requested') NOT NULL,
    target_owner ENUM('orders_anomalies_projection') NOT NULL,
    bounded_payload JSON NOT NULL,
    published_at TIMESTAMP(6) NULL,
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_before_replacement_outbox_event (
        replacement_event_id
    ),
    UNIQUE KEY uq_service_before_replacement_outbox_receipt (receipt_id),
    UNIQUE KEY uq_service_before_replacement_outbox_identity (
        outbox_identity
    ),
    INDEX idx_service_before_replacement_outbox_pending (
        published_at,
        attempts,
        id
    ),
    CONSTRAINT fk_service_before_replacement_outbox_event
        FOREIGN KEY (replacement_event_id, case_no)
        REFERENCES scheduling_service_before_replacement_events(id, case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_service_before_replacement_outbox_receipt
        FOREIGN KEY (receipt_id, replacement_event_id, case_no)
        REFERENCES scheduling_service_before_replacement_receipts(
            id,
            replacement_event_id,
            case_no
        )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_service_before_replacement_outbox_payload
        CHECK (JSON_TYPE(bounded_payload) = 'OBJECT'),
    CONSTRAINT chk_service_before_replacement_outbox_text
        CHECK (CHAR_LENGTH(TRIM(outbox_identity)) > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TRIGGER IF EXISTS trg_service_before_replacement_events_before_insert;
CREATE TRIGGER trg_service_before_replacement_events_before_insert
BEFORE INSERT ON scheduling_service_before_replacement_events
FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM scheduling_generations AS prior_generation
        INNER JOIN scheduling_generations AS replacement_generation
            ON replacement_generation.id = NEW.replacement_generation_id
           AND replacement_generation.case_no = NEW.case_no
        INNER JOIN scheduling_aggregates AS aggregate
            ON aggregate.case_no = NEW.case_no
        WHERE prior_generation.id = NEW.prior_generation_id
          AND prior_generation.case_no = NEW.case_no
          AND prior_generation.generation_number = NEW.expected_generation_version
          AND prior_generation.resulting_aggregate_version = NEW.expected_aggregate_version
          AND replacement_generation.generation_number = NEW.resulting_generation_version
          AND replacement_generation.resulting_aggregate_version = NEW.resulting_aggregate_version
          AND aggregate.generation_counter = NEW.resulting_generation_version
          AND aggregate.aggregate_version = NEW.resulting_aggregate_version
          AND NOT EXISTS (
              SELECT 1
              FROM scheduling_service_day_logs AS service_day_log
              WHERE service_day_log.case_no = NEW.case_no
          )
    ),
    NEW.case_no,
    NULL
);

DROP TRIGGER IF EXISTS trg_service_before_replacement_events_before_update;
CREATE TRIGGER trg_service_before_replacement_events_before_update
BEFORE UPDATE ON scheduling_service_before_replacement_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_events records cannot be updated';

DROP TRIGGER IF EXISTS trg_service_before_replacement_events_before_delete;
CREATE TRIGGER trg_service_before_replacement_events_before_delete
BEFORE DELETE ON scheduling_service_before_replacement_events
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_events records cannot be deleted';

DROP TRIGGER IF EXISTS trg_service_before_replacement_roots_before_update;
CREATE TRIGGER trg_service_before_replacement_roots_before_update
BEFORE UPDATE ON scheduling_service_before_replacement_roots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_roots records cannot be updated';

DROP TRIGGER IF EXISTS trg_service_before_replacement_roots_before_delete;
CREATE TRIGGER trg_service_before_replacement_roots_before_delete
BEFORE DELETE ON scheduling_service_before_replacement_roots
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_roots records cannot be deleted';

DROP TRIGGER IF EXISTS trg_service_before_replacement_successors_before_insert;
CREATE TRIGGER trg_service_before_replacement_successors_before_insert
BEFORE INSERT ON scheduling_service_before_replacement_successors
FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM matching_coordination_package_lineage AS matching_package
        INNER JOIN matching_coordination_events AS matching_event
            ON matching_event.package_lineage_id = matching_package.id
        WHERE matching_package.id = NEW.matching_package_lineage_id
          AND matching_event.id = NEW.matching_event_id
          AND matching_package.package_id = NEW.successor_package_identity
          AND matching_event.event_id = NEW.successor_matching_event_identity
          AND matching_package.case_no = NEW.case_no
          AND matching_event.case_no = NEW.case_no
    ),
    NEW.case_no,
    NULL
);

DROP TRIGGER IF EXISTS trg_service_before_replacement_successors_before_update;
CREATE TRIGGER trg_service_before_replacement_successors_before_update
BEFORE UPDATE ON scheduling_service_before_replacement_successors
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_successors records cannot be updated';

DROP TRIGGER IF EXISTS trg_service_before_replacement_successors_before_delete;
CREATE TRIGGER trg_service_before_replacement_successors_before_delete
BEFORE DELETE ON scheduling_service_before_replacement_successors
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_successors records cannot be deleted';

DROP TRIGGER IF EXISTS trg_service_before_replacement_receipts_before_update;
DROP TRIGGER IF EXISTS trg_service_before_replacement_receipts_before_insert;
CREATE TRIGGER trg_service_before_replacement_receipts_before_insert
BEFORE INSERT ON scheduling_service_before_replacement_receipts
FOR EACH ROW SET NEW.case_no = IF(
    NEW.retained_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS retained_root
        WHERE retained_root.replacement_event_id = NEW.replacement_event_id
          AND retained_root.case_no = NEW.case_no
          AND retained_root.disposition = 'retained'
    )
    AND NEW.retained_root_count = (
        SELECT COALESCE(MAX(retained_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS retained_root
        WHERE retained_root.replacement_event_id = NEW.replacement_event_id
          AND retained_root.case_no = NEW.case_no
          AND retained_root.disposition = 'retained'
    )
    AND NEW.superseded_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS superseded_root
        WHERE superseded_root.replacement_event_id = NEW.replacement_event_id
          AND superseded_root.case_no = NEW.case_no
          AND superseded_root.disposition = 'superseded'
    )
    AND NEW.superseded_root_count = (
        SELECT COALESCE(MAX(superseded_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS superseded_root
        WHERE superseded_root.replacement_event_id = NEW.replacement_event_id
          AND superseded_root.case_no = NEW.case_no
          AND superseded_root.disposition = 'superseded'
    )
    AND NEW.created_root_count = (
        SELECT COUNT(*)
        FROM scheduling_service_before_replacement_roots AS created_root
        WHERE created_root.replacement_event_id = NEW.replacement_event_id
          AND created_root.case_no = NEW.case_no
          AND created_root.disposition = 'created'
    )
    AND NEW.created_root_count = (
        SELECT COALESCE(MAX(created_root.canonical_ordinal), 0)
        FROM scheduling_service_before_replacement_roots AS created_root
        WHERE created_root.replacement_event_id = NEW.replacement_event_id
          AND created_root.case_no = NEW.case_no
          AND created_root.disposition = 'created'
    ),
    NEW.case_no,
    NULL
);

CREATE TRIGGER trg_service_before_replacement_receipts_before_update
BEFORE UPDATE ON scheduling_service_before_replacement_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_receipts records cannot be updated';

DROP TRIGGER IF EXISTS trg_service_before_replacement_receipts_before_delete;
CREATE TRIGGER trg_service_before_replacement_receipts_before_delete
BEFORE DELETE ON scheduling_service_before_replacement_receipts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_receipts records cannot be deleted';

DROP TRIGGER IF EXISTS trg_service_before_replacement_outbox_before_update;
CREATE TRIGGER trg_service_before_replacement_outbox_before_update
BEFORE UPDATE ON scheduling_service_before_replacement_outbox
FOR EACH ROW SET NEW.replacement_event_id = IF(
    OLD.id <=> NEW.id
    AND OLD.replacement_event_id <=> NEW.replacement_event_id
    AND OLD.receipt_id <=> NEW.receipt_id
    AND OLD.case_no <=> NEW.case_no
    AND OLD.outbox_identity <=> NEW.outbox_identity
    AND OLD.intent_type <=> NEW.intent_type
    AND OLD.target_owner <=> NEW.target_owner
    AND OLD.bounded_payload <=> NEW.bounded_payload
    AND OLD.created_at <=> NEW.created_at,
    NEW.replacement_event_id,
    NULL
);

DROP TRIGGER IF EXISTS trg_service_before_replacement_outbox_before_insert;
CREATE TRIGGER trg_service_before_replacement_outbox_before_insert
BEFORE INSERT ON scheduling_service_before_replacement_outbox
FOR EACH ROW SET NEW.case_no = IF(
    EXISTS(
        SELECT 1
        FROM scheduling_service_before_replacement_receipts AS receipt
        WHERE receipt.id = NEW.receipt_id
          AND receipt.replacement_event_id = NEW.replacement_event_id
          AND receipt.case_no = NEW.case_no
          AND receipt.outbox_identity = NEW.outbox_identity
    ),
    NEW.case_no,
    NULL
);

DROP TRIGGER IF EXISTS trg_service_before_replacement_outbox_before_delete;
CREATE TRIGGER trg_service_before_replacement_outbox_before_delete
BEFORE DELETE ON scheduling_service_before_replacement_outbox
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'scheduling_service_before_replacement_outbox records cannot be deleted';
