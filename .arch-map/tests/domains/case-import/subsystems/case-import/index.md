subsystem: case-import
parent_domain: case-import
architecture: ../../../../../domains/case-import/subsystems/case-import/index.md
test_root: tests/subsystems/case_import/
higher_boundary: tests/domains/case_import/
fixtures_root: tests/fixtures/
modules:
  staff-historical-workbook-adoption:
    layout_status: current
    test_root: tests/domains/case-import/subsystems/case-import/modules/staff-historical-workbook-adoption/
  pairing-current-facts:
    layout_status: canonical
    test_root: tests/domains/case-import/subsystems/case-import/modules/pairing-current-facts/

# Routing notes
Current owner-local coverage includes HCM workbook preview/apply/replay contracts, HCM-BeClass reconciliation application/MySQL adapter transaction boundaries, HCM resubmission domain/workbook/workflow behavior, and HCM resubmission outbox consumer canonical-identity/fresh-root/claim-ordering/replay guards. Tests that exercise release/migration, disposable-MySQL/E2E, or a true cross-owner workflow remain at their higher verification boundary.

# Placement refresh — 2026-08-30
The following flat tests were relocated into this canonical root:
- `test_hcm_resubmission.py`
- `test_hcm_resubmission_workbook.py`
- `test_hcm_resubmission_workflow.py`

The source-path assertion in `test_hcm_resubmission.py` was made relocation-safe for the canonical owner root; behavior and production code are unchanged.

# Placement refresh — 2026-09-09
`tests/domains/case-import/subsystems/case-import/modules/staff-historical-workbook-adoption/test_staff_historical_workbook_parser.py` now lives in the existing module root declared by the architecture leaf. It directly tests `subsystems.case_import.staff_historical_workbook`; sheet selection and input normalization are Case Import responsibilities, not Staff lifecycle or cross-owner adoption acceptance. The file was moved without content changes. The general `tests/subsystems/case_import/` root and existing higher-boundary exceptions remain unchanged.

# Placement refresh — 2026-09-10
`tests/subsystems/case_import/test_hcm_resubmission_outbox_consumer.py` now owns the HCM resubmission outbox consumer guards previously mixed into the Anomalies import-warning auto-resolution guard. The direct SUT is `subsystems.case_import.hcm_resubmission_outbox_consumer`; legacy import-warning rulebook tests remain at their compatibility boundary.

# Exceptions
- `tests/test_wp77_import_contracts.py` is a current protected legacy path with an external inventory consumer; status: `layout_gap`.

# Flat-test audit
After this refresh, no additional high-confidence Case Import owner-local HCM resubmission tests remain in the flat root. Admit future cases by direct SUT/current ownership rather than filename alone; keep release/migration, engine, protected legacy and true cross-owner coverage at its higher boundary.
