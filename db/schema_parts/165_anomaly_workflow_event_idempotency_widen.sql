-- Widen idempotency_key: VARCHAR(191) truncated content-hash dedupe keys,
-- causing INSERT ... ON DUPLICATE KEY to fail with "Data too long for column
-- 'idempotency_key'" and roll back the background anomaly-scan cycle.

ALTER TABLE anomaly_workflow_events
    MODIFY COLUMN idempotency_key VARCHAR(320) NOT NULL;
