-- Additive only: existing completed registrations and bindings are preserved.
ALTER TABLE provisional_client_registrations
    ADD COLUMN application_payload JSON NULL,
    ADD COLUMN application_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    ADD COLUMN approved_by_actor VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
    ADD COLUMN approved_at_utc DATETIME(6) NULL;
