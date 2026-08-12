ALTER TABLE line_identity_revocation_requests
    MODIFY COLUMN default_menu_publication_id BIGINT NULL,
    ADD COLUMN canonical_default_menu_publication_id BIGINT UNSIGNED NULL
        AFTER default_menu_publication_id,
    ADD INDEX idx_line_identity_revocation_canonical_publication (
        canonical_default_menu_publication_id
    ),
    ADD CONSTRAINT fk_line_identity_revocation_canonical_publication
        FOREIGN KEY (canonical_default_menu_publication_id)
        REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT chk_line_identity_revocation_publication_source CHECK (
        (default_menu_publication_id IS NULL)
        <> (canonical_default_menu_publication_id IS NULL)
    );
