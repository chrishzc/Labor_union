subsystem: case-import
parent_domain: case-import
architecture: ../../../../../domains/case-import/subsystems/case-import/index.md
test_root: tests/subsystems/case_import/
higher_boundary: tests/domains/case_import/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes HCM workbook preview/apply/replay contracts and the HCM-BeClass reconciliation application/MySQL adapter transaction boundary. Tests that exercise release/migration, disposable-MySQL/E2E, or a true cross-owner workflow remain at their higher verification boundary.

# Exceptions
- `tests/test_wp77_import_contracts.py` is a current protected legacy path with an external inventory consumer; status: `layout_gap`.

# Flat-test audit
The current flat-test audit found no additional high-confidence Case Import owner-local tests outside the documented protected legacy, release/migration, disposable-MySQL/E2E, or cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
