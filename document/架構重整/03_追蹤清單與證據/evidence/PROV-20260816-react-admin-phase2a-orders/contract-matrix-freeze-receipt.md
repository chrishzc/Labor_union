# Phase 2A contract matrix freeze receipt

| Field | Value |
|---|---|
| identity | `PROV-20260816-react-admin-phase2a-orders` |
| charter revision | Work Package V3 |
| branch / HEAD | `main` / `ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922` |
| source readback | `api/schemas/order_summary.py`, `order_detail.py`, `order_calendar_detail.py`, `order_terms.py`, `form_management.py`, `order_actual_start.py`, `order_contract_completion.py`, `assignment_plan.py`, corresponding routes/tests |
| visible-field rows | 37 |
| disposition counts | READY_TYPED 14 / PRESENTATION_CONSTANT 2 / BACKEND_GAP 18 / OUT_OF_SCOPE 3 |
| exact success endpoints | summaries, detail, calendar-detail, terms, form-management-context, actual-start, contract-completion, assignment-plan |
| raw endpoints | excluded; `PUBLIC_CONTRACT_CHANGE_REQUIRED` |
| freeze status | `CONTRACT_MATRIX_FROZEN` for current HEAD and current working-tree source |
| verified by | Integration Owner source readback, 2026-08-16 |

## Freeze caveats

- Freeze is invalidated by changes to the eight Pydantic models/routes or to the Phase 2A visible surfaces.
- The matrix deliberately records the current 7-stage, SOP, notification, formal recommendation,
  emergency warning and three-settlement projections as `BACKEND_GAP`; it does not promote mock UI to contract.
- G5 browser runtime evidence is independent and remains blocked.
