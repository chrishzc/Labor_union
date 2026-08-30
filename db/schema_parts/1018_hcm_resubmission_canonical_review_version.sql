-- File: 1018_hcm_resubmission_canonical_review_version.sql
-- Description: Canonical HCM review identity/version evidence for correction events.
-- Additive only. Existing 193/201 artifacts are immutable; no backfill.

ALTER TABLE case_import_hcm_correction_events
    MODIFY COLUMN prior_occurrence_id BIGINT NULL,
    ADD COLUMN canonical_review_identity VARCHAR(191) NULL
        COMMENT 'Immutable Case Import HCM review identity; NULL only for historical events',
    ADD COLUMN expected_review_version BIGINT UNSIGNED NULL,
    ADD COLUMN resulting_review_version BIGINT UNSIGNED NULL,
    ADD UNIQUE KEY uq_hcm_correction_event_review_version
        (canonical_review_identity, resulting_review_version),
    ADD INDEX idx_hcm_correction_event_canonical_review
        (canonical_review_identity, id),
    ADD CONSTRAINT fk_hcm_correction_event_canonical_review
        FOREIGN KEY (canonical_review_identity)
        REFERENCES case_import_hcm_review_rows(review_identity)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT chk_hcm_correction_event_review_version
        CHECK (
            (canonical_review_identity IS NULL
             AND expected_review_version IS NULL
             AND resulting_review_version IS NULL)
            OR
            (canonical_review_identity IS NOT NULL
             AND CHAR_LENGTH(TRIM(canonical_review_identity)) > 0
             AND expected_review_version IS NOT NULL
             AND resulting_review_version = expected_review_version + 1)
        );
