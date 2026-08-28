-- File: 1008_historical_order_adoption_noop_constraint.sql
-- Description: 讓合法且不改變 Orders 根狀態的歷史採納不建立假的 lifecycle event。

ALTER TABLE historical_order_adoption_receipts
    DROP CHECK chk_historical_order_adoption_shape,
    ADD CONSTRAINT chk_historical_order_adoption_shape
        CHECK (
            (outcome = 'unmatched_case' AND lifecycle_event_id IS NULL
             AND expected_version IS NULL AND resulting_version IS NULL)
            OR
            (outcome = 'adopted'
             AND expected_version IS NOT NULL
             AND case_no IS NOT NULL
             AND (
                 (lifecycle_event_id IS NULL
                  AND resulting_version = expected_version)
                 OR
                 (lifecycle_event_id IS NOT NULL
                  AND resulting_version = expected_version + 1)
             ))
            OR
            (outcome IN ('review_required','current_conflict')
             AND lifecycle_event_id IS NULL
             AND expected_version IS NOT NULL
             AND resulting_version = expected_version
             AND case_no IS NOT NULL)
        );
