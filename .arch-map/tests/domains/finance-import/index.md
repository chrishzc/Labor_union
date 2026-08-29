domain: finance-import
architecture: ../../../domains/finance-import/index.md
test_root: layout_gap
integration_root: tests/imports/
fixtures_root: tests/fixtures/
subsystems:
  finance-import:
    index: subsystems/finance-import/index.md

# Routing notes
`tests/imports/` is a functional legacy root shared with Case Import rather than a canonical `tests/domains/finance-import/` tree. Treat it as `layout_gap`; select tests by Finance Import contracts/paths and expand to Client Finance/Staff Payables/Subsidy only when owner delegation is in scope.
