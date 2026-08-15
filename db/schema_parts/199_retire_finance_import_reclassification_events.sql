-- File: 199_retire_finance_import_reclassification_events.sql
-- Description: Fresh schema 不再建立已退役的 finance reclassification event 結構。

DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_update;
DROP TRIGGER IF EXISTS trg_finance_import_reclassification_events_before_delete;
DROP TABLE IF EXISTS finance_import_reclassification_events;
