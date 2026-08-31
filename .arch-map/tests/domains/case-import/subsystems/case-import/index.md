subsystem: case-import
parent_domain: case-import
architecture: ../../../../../domains/case-import/subsystems/case-import/index.md
test_root: tests/subsystems/case_import/
higher_boundary: tests/domains/case_import/
fixtures_root: tests/fixtures/
modules:
  pairing-current-facts:
    layout_status: canonical
    test_root: tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/

# Routing notes
Current owner-local coverage includes HCM workbook preview/apply/replay contracts, HCM-BeClass reconciliation application/MySQL adapter transaction boundaries, and HCM resubmission domain/workbook/workflow behavior. Tests that exercise release/migration, disposable-MySQL/E2E, or a true cross-owner workflow remain at their higher verification boundary.

# Placement refresh — 2026-08-30
The following flat tests were relocated into this canonical root:
- `test_hcm_resubmission.py`
- `test_hcm_resubmission_workbook.py`
- `test_hcm_resubmission_workflow.py`

The source-path assertion in `test_hcm_resubmission.py` was made relocation-safe for the canonical owner root; behavior and production code are unchanged.

# Exceptions
- `tests/test_wp77_import_contracts.py` is a current protected legacy path with an external inventory consumer; status: `layout_gap`.

# Flat-test audit
After this refresh, no additional high-confidence Case Import owner-local HCM resubmission tests remain in the flat root. Admit future cases by direct SUT/current ownership rather than filename alone; keep release/migration, engine, protected legacy and true cross-owner coverage at its higher boundary.
