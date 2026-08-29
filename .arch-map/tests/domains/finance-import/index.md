domain: finance-import
architecture: ../../../domains/finance-import/index.md
test_root: tests/domains/finance-import/
integration_root: tests/domains/finance-import/subsystems/finance-import/integration/
fixtures_root: tests/fixtures/
subsystems:
  finance-import:
    index: subsystems/finance-import/index.md

# Routing notes
Finance Import format detection, normalization and bank-adapter tests now live under the canonical Finance Import subsystem integration root. Do not recreate a generic `tests/imports/` bucket; Case Import and other owners must route to their own architecture roots.
