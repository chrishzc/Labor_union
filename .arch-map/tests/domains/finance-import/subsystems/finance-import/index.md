subsystem: finance-import
parent_domain: finance-import
architecture: ../../../../../domains/finance-import/subsystems/finance-import/index.md
test_root: tests/domains/finance-import/subsystems/finance-import/
integration_root: tests/domains/finance-import/subsystems/finance-import/integration/
fixtures_root: tests/fixtures/

# Routing notes
The former `tests/imports/` root contained only current Finance Import format detection, normalization and bank-adapter tests and has moved to the canonical Finance Import subsystem integration root. Future import tests owned by Case Import or another Domain must use that owner's architecture root rather than recreating a generic `tests/imports/` bucket.
