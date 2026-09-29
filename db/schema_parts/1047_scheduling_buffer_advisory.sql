-- Preserve every assignment, schedule and buffer fact. Buffers are advisory.
ALTER TABLE scheduling_buffer_days
    DROP INDEX uq_scheduling_buffer_staff_date_active,
    ADD INDEX uq_scheduling_buffer_staff_date_active (staff_id, buffer_date, active_marker);

-- Retain historical buffer projections alongside real service occupancy.
-- assignment_interval still has one unique staff/date identity.
ALTER TABLE scheduling_effective_occupancy
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (staff_id, occupancy_date, occupancy_type);
