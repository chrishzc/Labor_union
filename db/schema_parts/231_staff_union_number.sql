-- Staff-owned manual union number; preserve existing roots and leave old rows unset.
ALTER TABLE staff
    ADD COLUMN union_no VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NULL COMMENT '公會自訂編號',
    ADD UNIQUE KEY uq_staff_union_no (union_no);
