domain: payroll
architecture: ../../../domains/payroll/index.md
test_root: layout_gap
integration_root: tests/subsystems/payroll/
fixtures_root: tests/fixtures/
subsystems:
  payroll:
    index: subsystems/payroll/index.md

# Routing notes
No `tests/domains/payroll/` root was observed. `tests/subsystems/payroll/` is the current strongest owner-local root; remaining Payroll suites in flat/shared roots are `layout_gap` and should be admitted only by scoped search.
