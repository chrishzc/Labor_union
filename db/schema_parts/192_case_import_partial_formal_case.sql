-- File: 192_case_import_partial_formal_case.sql
-- Description: 允許 HCM partial formal case 保存完整來源列而延後建立 case architecture bootstrap。

ALTER TABLE case_import_events
    MODIFY COLUMN bootstrap_event_id BIGINT NULL;

ALTER TABLE case_import_receipts
    MODIFY COLUMN bootstrap_event_id BIGINT NULL;
