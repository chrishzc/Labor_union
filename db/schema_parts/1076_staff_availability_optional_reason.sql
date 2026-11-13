-- Allow optional (empty) reason on staff unavailability blocks while retaining required created_by.
ALTER TABLE scheduling_staff_unavailability_blocks
    DROP CHECK chk_scheduling_staff_unavailability_reason,
    ADD CONSTRAINT chk_scheduling_staff_unavailability_reason
        CHECK (CHAR_LENGTH(TRIM(created_by)) > 0);
