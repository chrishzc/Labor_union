-- Preserve all rows and owner identities. Staff mutex + interval checks guard
-- overlap; the former staff/date keys remain available for lookups.
ALTER TABLE staff_schedule
    DROP INDEX uq_staff_schedule_effective_date,
    ADD INDEX uq_staff_schedule_effective_date (staff_id, work_date, effective_marker);

ALTER TABLE caregiver_availability_lock_days
    DROP INDEX uq_availability_lock_staff_date_active,
    ADD INDEX uq_availability_lock_staff_date_active (staff_id, lock_date, active_marker);

ALTER TABLE scheduling_effective_occupancy
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (staff_id, occupancy_date, occupancy_type, assignment_id);

ALTER TABLE scheduling_leave_occupancy_days
    DROP INDEX uq_scheduling_leave_occupancy_staff_date,
    ADD INDEX uq_scheduling_leave_occupancy_staff_date (staff_id, occupancy_date, active_marker);
