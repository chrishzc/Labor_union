-- File: 1072_line_media_controlled_file_reference.sql
-- Persist the exact controlled object for new formal rich-menu PNG assets.
-- Legacy media retains NULL; no hash/path inference or historical backfill.
ALTER TABLE media_assets
    ADD COLUMN controlled_file_object_id BIGINT UNSIGNED NULL,
    ADD INDEX idx_media_controlled_file_object (controlled_file_object_id),
    ADD CONSTRAINT fk_media_controlled_file_object
        FOREIGN KEY (controlled_file_object_id) REFERENCES controlled_file_objects(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;
