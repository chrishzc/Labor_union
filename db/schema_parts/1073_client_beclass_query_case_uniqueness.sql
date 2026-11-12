-- Replace questionnaire-wide uniqueness with one imported row per questionnaire and case.
ALTER TABLE beclass_records
    DROP INDEX query_no,
    ADD UNIQUE KEY uq_beclass_query_case (query_no, bound_case_no);
