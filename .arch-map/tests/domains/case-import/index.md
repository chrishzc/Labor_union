domain: case-import
architecture: ../../../domains/case-import/index.md
test_root: tests/domains/case_import/
integration_root: tests/subsystems/case_import/
fixtures_root: tests/fixtures/
subsystems:
  case-import:
    index: subsystems/case-import/index.md

# Layout gaps
- `tests/imports/` contains functional import tests spanning Case Import and Finance Import.
- `tests/test_wp77_import_contracts.py` remains a protected current legacy path with a direct current inventory consumer; status: `layout_gap`.
Do not duplicate or move these solely to make the tree look canonical.
