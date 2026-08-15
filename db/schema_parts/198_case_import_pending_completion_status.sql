-- File: 198_case_import_pending_completion_status.sql
-- Description: 為 partial HCM formal case 新增待補件訂單狀態。

-- Partial HCM formal cases exist, but must not enter the service lifecycle before required fields are complete.
ALTER TABLE orders
    MODIFY COLUMN `status` ENUM('待補件', '洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消')
    NOT NULL DEFAULT '洽談中'
    COMMENT '專案狀態；待補件案件不得進入服務生命週期';
