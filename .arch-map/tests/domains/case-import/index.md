domain: case-import
architecture: ../../../domains/case-import/index.md
test_root: tests/domains/case_import/
integration_root: tests/subsystems/case_import/
fixtures_root: tests/fixtures/
subsystems:
  case-import:
    index: subsystems/case-import/index.md

# Current placement
Case Import owner-local workflow/integration coverage lives under `tests/subsystems/case_import/`. The 2026-08-30 refresh moved HCM resubmission domain/workbook/workflow tests out of the flat root into that canonical owner location. `tests/domains/case_import/` remains the Domain-level higher boundary for broader Case Import contracts.

# Layout gaps / higher boundary
- `tests/test_wp77_import_contracts.py` remains a protected current legacy path with a direct current inventory consumer; status: `layout_gap`.
- Release/migration, disposable-MySQL/engine and true cross-owner tests remain at their higher verification boundary.
Do not duplicate or move those cases solely to make the tree look canonical.
