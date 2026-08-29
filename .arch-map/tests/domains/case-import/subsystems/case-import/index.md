subsystem: case-import
parent_domain: case-import
architecture: ../../../../../domains/case-import/subsystems/case-import/index.md
test_root: tests/subsystems/case_import/
higher_boundary: tests/domains/case_import/
fixtures_root: tests/fixtures/

# Exceptions
- `tests/imports/` is a shared functional legacy root; admit only Case Import-owned scenarios.
- `tests/test_wp77_import_contracts.py` is a current protected legacy path with an external inventory consumer; status: `layout_gap`.
