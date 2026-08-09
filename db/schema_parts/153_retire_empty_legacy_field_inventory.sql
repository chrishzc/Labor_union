-- Current local databases contain only fake data. Retire structures that no
-- production caller owns so bootstrap and the active candidate cannot revive them.
DROP TABLE IF EXISTS finance_import_reclassification_events;
