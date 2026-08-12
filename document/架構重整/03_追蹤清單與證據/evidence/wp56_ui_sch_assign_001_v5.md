# WP56 UI SCH Assign 001 v5

- Date: 2026-08-11
- UI: `http://127.0.0.1:8502`
- Scenario: `UI-SCH-ASSIGN-001`

Browser evidence through the existing Multi-Caregiver Scheduling page selected
the Case Staffing surface. The selected case did not have the required formal
root state, so the UI fail-closed and did not expose Assignment Plan mutation.
This confirms the surface is guarded by the existing root-state boundary.

Screenshot: `wp56_ui_sch_assign_001_v5.png`.
DB oracle: `validation/receipts/UI-SCH-ASSIGN-001_v4.json`.
