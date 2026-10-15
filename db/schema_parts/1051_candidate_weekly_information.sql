-- Append weekly information delivery; retain every existing enum ordinal and event.
ALTER TABLE caregiver_candidate_contact_events
    MODIFY COLUMN event_type ENUM('candidates_added','info_1_sent','info_2_sent','willingness_changed','candidate_selected','candidate_withdrawn','info_3_sent') NOT NULL;
