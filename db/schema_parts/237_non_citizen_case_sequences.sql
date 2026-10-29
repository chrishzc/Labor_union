-- A sequence is allocated only inside the approval transaction.
CREATE TABLE IF NOT EXISTS non_citizen_case_sequences (
    roc_year SMALLINT UNSIGNED NOT NULL PRIMARY KEY,
    next_sequence INT UNSIGNED NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
