# G03 Cancellation UI/API/MySQL E2E Receipt

- Observed: 2026-08-08
- Isolation: randomly named disposable local MySQL database with the `lu_test_g03_ui_` prefix; dropped in the runner `finally` block.
- Test: `tests/test_order_cancellation_disposable_mysql_e2e.py::test_g03_panel_uses_real_http_preview_and_apply`
- Result: `1 passed`.

## Business trace

1. A two-caregiver in-service order has four scheduled service days.
2. The Streamlit cancellation panel retains only the two dates actually completed by their assigned caregivers.
3. The actual typed HTTP Preview and Apply endpoints execute the canonical cancellation workflow.
4. Orders, Scheduling, Client Finance and Payroll commit the cancellation as one cross-domain result.
5. Client refund obligations and staff payable obligations remain separate; no cross-domain auto-netting occurs.

## Scope

This receipt supplements the existing direct G03 transaction/replay scenario. It proves the production panel does not derive its own business result and sends the selected completed-service-day facts through the backend API.
