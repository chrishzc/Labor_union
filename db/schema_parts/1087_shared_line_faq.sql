-- Shared FAQ formal-version pointer, immutable source fields, and LINE layout kind.
ALTER TABLE knowledge_items
    ADD COLUMN published_version BIGINT UNSIGNED NULL,
    ADD COLUMN faq_legacy_aliases JSON NULL,
    ADD COLUMN faq_legacy_category_id VARCHAR(80) NULL,
    ADD COLUMN faq_legacy_category_version BIGINT UNSIGNED NULL;

ALTER TABLE knowledge_item_versions
    ADD COLUMN title VARCHAR(300) NULL,
    ADD COLUMN source_uri VARCHAR(500) NULL,
    ADD COLUMN source_trust_tier ENUM('internal_policy','government_source','approved_partner') NULL;

ALTER TABLE line_configuration_revisions
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules','faq_chat_layout'
    ) NOT NULL;

ALTER TABLE line_configuration_current
    MODIFY COLUMN configuration_kind ENUM(
        'message_templates','message_schedules','rich_menus','liff','customer_service','notification_rules','faq_chat_layout'
    ) NOT NULL;
