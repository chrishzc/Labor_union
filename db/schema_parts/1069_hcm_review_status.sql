-- Preserve the source decision separately from the order lifecycle.
ALTER TABLE clients
    ADD COLUMN hcm_review_status ENUM('符合','不符合') NULL COMMENT 'HCM 案件審核結果';
