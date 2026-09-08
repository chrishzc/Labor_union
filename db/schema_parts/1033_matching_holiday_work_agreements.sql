-- File: 1033_matching_holiday_work_agreements.sql
-- Purpose: preserve-data bridge from the released communication-version column name
--          to the Scheduling-owned matching-plan version contract.
-- Data effect: schema only; MySQL renames the column and preserves every stored value.

ALTER TABLE matching_holiday_work_agreements
    RENAME COLUMN plan_communication_version TO plan_version;
