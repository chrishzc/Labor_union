-- Allow only the FAQ owner transaction to remove the selected item's versions.
DELIMITER $$
DROP TRIGGER IF EXISTS trg_knowledge_item_versions_before_delete$$
CREATE TRIGGER trg_knowledge_item_versions_before_delete
BEFORE DELETE ON knowledge_item_versions FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM knowledge_items item
        JOIN knowledge_apply_receipts receipt
          ON receipt.idempotency_key = CONCAT('faq-deleted:', SHA2(LOWER(item.source_identity), 256))
         AND receipt.command_fingerprint = SHA2(LOWER(item.source_identity), 256)
        WHERE item.id = OLD.item_id
          AND LEFT(item.source_identity, 15) = BINARY 'line-common-qa:'
          AND item.published_version IS NULL
          AND item.state IN ('draft', 'reviewed', 'retired')
          AND JSON_UNQUOTE(JSON_EXTRACT(receipt.receipt_json, '$.deleting_faq_item_id')) = CAST(OLD.item_id AS CHAR)
          AND JSON_UNQUOTE(JSON_EXTRACT(receipt.receipt_json, '$.deleting_connection_id')) = CAST(CONNECTION_ID() AS CHAR)
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'knowledge_item_versions records cannot be deleted';
    END IF;
END$$
DELIMITER ;
