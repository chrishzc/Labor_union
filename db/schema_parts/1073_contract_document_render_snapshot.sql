-- File: 1073_contract_document_render_snapshot.sql
-- Preserve real immutable document versions without archiving new draft bytes.
-- Existing media references remain legacy_archived; no seed or historical backfill.
ALTER TABLE contract_document_versions
    MODIFY COLUMN media_asset_id BIGINT NULL,
    ADD COLUMN render_source_kind ENUM('legacy_archived', 'render_snapshot')
        NOT NULL DEFAULT 'legacy_archived',
    ADD COLUMN render_source_snapshot JSON NULL,
    ADD COLUMN render_source_snapshot_sha256 CHAR(64) NULL,
    ADD COLUMN render_source_sha256 CHAR(64) NULL,
    ADD COLUMN render_source_size_bytes BIGINT UNSIGNED NULL,
    ADD CONSTRAINT chk_contract_document_render_source CHECK (
        (render_source_kind = 'legacy_archived'
            AND media_asset_id IS NOT NULL
            AND render_source_snapshot IS NULL
            AND render_source_snapshot_sha256 IS NULL
            AND render_source_sha256 IS NULL
            AND render_source_size_bytes IS NULL)
        OR (render_source_kind = 'render_snapshot'
            AND media_asset_id IS NULL
            AND document_role = 'template_generated'
            AND source_document_version_id IS NULL
            AND template_key IS NOT NULL AND CHAR_LENGTH(TRIM(template_key)) > 0
            AND template_sha256 IS NOT NULL
            AND template_sha256 REGEXP '^[0-9a-f]{64}$'
            AND mapping_sha256 IS NOT NULL
            AND mapping_sha256 REGEXP '^[0-9a-f]{64}$'
            AND facts_snapshot_sha256 IS NOT NULL
            AND facts_snapshot_sha256 REGEXP '^[0-9a-f]{64}$'
            AND render_source_snapshot IS NOT NULL
            AND JSON_TYPE(render_source_snapshot) = 'OBJECT'
            AND JSON_LENGTH(render_source_snapshot) = 4
            AND JSON_CONTAINS_PATH(render_source_snapshot, 'all',
                '$.schema', '$.serialization', '$.source', '$.facts')
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.schema'))
                = 'contract-render-source.v1'
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.serialization'))
                = 'canonical-xlsx-zip.v1'
            AND JSON_TYPE(JSON_EXTRACT(render_source_snapshot, '$.source')) = 'OBJECT'
            AND JSON_LENGTH(JSON_EXTRACT(render_source_snapshot, '$.source')) = 9
            AND JSON_TYPE(JSON_EXTRACT(render_source_snapshot, '$.facts')) = 'OBJECT'
            AND JSON_CONTAINS_PATH(render_source_snapshot, 'all',
                '$.source.case_no', '$.source.document_scope',
                '$.source.matching_plan_id', '$.source.matching_segment_id',
                '$.source.document_target_key', '$.source.template_key',
                '$.source.template_sha256', '$.source.mapping_sha256',
                '$.source.facts_snapshot_sha256')
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.case_no')) = case_no
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.document_scope')) = document_scope
            AND JSON_TYPE(JSON_EXTRACT(render_source_snapshot, '$.source.matching_plan_id')) = 'INTEGER'
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.matching_plan_id')) = CAST(matching_plan_id AS CHAR)
            AND ((matching_segment_id IS NULL
                    AND JSON_TYPE(JSON_EXTRACT(render_source_snapshot, '$.source.matching_segment_id')) = 'NULL')
                OR (matching_segment_id IS NOT NULL
                    AND JSON_TYPE(JSON_EXTRACT(render_source_snapshot, '$.source.matching_segment_id')) = 'INTEGER'
                    AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.matching_segment_id')) = CAST(matching_segment_id AS CHAR)))
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.document_target_key')) = document_target_key
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.template_key')) = template_key
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.template_sha256')) = template_sha256
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.mapping_sha256')) = mapping_sha256
            AND JSON_UNQUOTE(JSON_EXTRACT(render_source_snapshot, '$.source.facts_snapshot_sha256')) = facts_snapshot_sha256
            AND render_source_snapshot_sha256 IS NOT NULL
            AND render_source_snapshot_sha256 REGEXP '^[0-9a-f]{64}$'
            AND render_source_sha256 IS NOT NULL
            AND render_source_sha256 REGEXP '^[0-9a-f]{64}$'
            AND render_source_size_bytes IS NOT NULL AND render_source_size_bytes > 0)
    );
