-- Preserve HCM email independently from the BeClass source/effective email.
ALTER TABLE clients ADD COLUMN email VARCHAR(100) NULL COMMENT 'HCM Email';
