-- File: 1024_task96_line_identity_revocation_role_binding_fk.sql
-- Purpose: retarget Staff/LINE revocation requests to the canonical role binding root.
-- Data effect: schema only; existing revocation rows and their lineage are preserved.

ALTER TABLE line_identity_revocation_requests
    DROP FOREIGN KEY fk_line_identity_revocation_binding,
    ADD CONSTRAINT fk_line_identity_revocation_role_binding
        FOREIGN KEY (line_user_id, subject_type)
        REFERENCES line_identity_role_bindings(line_user_id, subject_type)
        ON UPDATE RESTRICT ON DELETE RESTRICT;
