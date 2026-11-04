module: staff-performance
parent_subsystem: reporting
architecture: ../../../../../../../domains/global/subsystems/reporting/modules/staff-performance.md
layout_status: custom_current
test_root: tests/domains/global/subsystems/reporting/modules/staff-performance/
integration_root: ui_react/src/tests/domains/global/subsystems/reporting/modules/staff-performance/

# Owned verification
- `test_staff_performance.py` — opening-month/principal credit, service-month hours, monthly reconciliation, unknown dates, lineage adapter, authenticated v2 API and XLSX recognition detail.
- `staff_performance.test.tsx` — numbered staff selector, ranking, details, period changes, export and stale requests.
- `staff_performance_client.test.ts` — strict version/period transport and XLSX validation.
