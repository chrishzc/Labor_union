-- File: 197_client_beclass_transition_binding.sql
-- Description: 將唯一比對的 Client BeClass 來源記錄綁定 Client 與案件。

-- Client BeClass query_no is source provenance, not a Client or case identity.
ALTER TABLE beclass_records
    ADD COLUMN client_id INT NULL COMMENT '過渡期唯一比對後的 Client 綁定' AFTER query_no,
    ADD COLUMN bound_case_no VARCHAR(50) NULL COMMENT '過渡期唯一比對後的案件編號' AFTER client_id,
    ADD INDEX idx_beclass_client_case (client_id, bound_case_no),
    ADD CONSTRAINT fk_beclass_client
        FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT;
