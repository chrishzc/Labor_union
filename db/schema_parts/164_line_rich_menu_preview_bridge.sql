-- Bind the governed preview confirmation to the canonical publication task.
ALTER TABLE line_rich_menu_publish_previews
    ADD COLUMN canonical_publication_task_id BIGINT UNSIGNED NULL
        AFTER publication_id,
    ADD INDEX idx_line_menu_preview_canonical_task (
        canonical_publication_task_id
    ),
    ADD CONSTRAINT fk_line_menu_preview_canonical_task
        FOREIGN KEY (canonical_publication_task_id)
        REFERENCES line_rich_menu_publication_tasks(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;
