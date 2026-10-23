-- Persist only the current manually supplied service-group invitation URL.
-- Existing bindings remain NULL; no group, participant or financial backfill.
ALTER TABLE line_order_group_bindings
    ADD COLUMN invitation_url VARCHAR(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL DEFAULT NULL;
