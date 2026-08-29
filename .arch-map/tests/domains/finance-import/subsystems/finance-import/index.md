subsystem: finance-import
parent_domain: finance-import
architecture: ../../../../../domains/finance-import/subsystems/finance-import/index.md
test_root: tests/imports/
integration_root: unknown
fixtures_root: tests/fixtures/

# Routing notes
`tests/imports/` is the current functional root but is not architecture-owned; status: `layout_gap`. Select by Finance Import source/contract responsibility rather than loading the directory wholesale.
