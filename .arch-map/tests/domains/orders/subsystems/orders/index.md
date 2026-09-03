subsystem: orders
parent_domain: orders
architecture: ../../../../../domains/orders/subsystems/orders/index.md
test_root: tests/domains/orders/subsystems/orders/

# Custom current presentation routing
- Order Tracker summary/retry presentation: `modules/order-tracker-presentation.md`.
integration_root: tests/domains/orders/subsystems/orders/integration/
integration_root: ui_react/src/tests/orders_service_dates_flow.test.tsx
fixtures_root: tests/fixtures/
modules:
  historical-precision-restart:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-precision-restart/
  historical-service-accounting:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-service-accounting/
  order-information:
    test_root: tests/domains/orders/subsystems/orders/modules/order-information/
  historical-adoption:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-adoption/
  historical-stage-baseline:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-stage-baseline/
  service-date-confirmation:
    test_root: tests/domains/orders/subsystems/orders/modules/service-date-confirmation/
  actual-start:
    test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/actual-start/
  historical-adoption-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/historical_order_workbook_client.test.ts
  historical-completion:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-completion/
  historical-baseline-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/historical_operational_baseline_readback.test.tsx
  historical-review-remediation-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/historical_order_review_remediation.test.tsx
  order-card-projection:
    layout_status: custom_current
    test_root: ui_react/src/tests/orders_page_real_data.test.tsx
  service-completion-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/order_service_completion_actions.test.tsx
  cancellation:
    test_root: tests/domains/orders/subsystems/orders/integration/
  terminal-closure-handoff:
    layout_status: custom_current
    test_root: tests/domains/external-integration/subsystems/line/modules/line-identity-management/contract/

# Exceptions
- Current owner-local coverage includes Historical Adoption; cancellation route/read-model; actual-start workflow; calendar/detail/summary queries; lifecycle authoritative facts/loaders; reopen workflow/router; auto-completion API/routes/workflow; lifecycle control/deposit/impact-writer contracts; card/stage projections; historical review remediation API/workflow/repository; historical completion API/oracle/projector/query; service-date confirmation domain/router; historical operational baseline domain/catalog/API/workflow/repository/owner-vector; historical warning mapping; the historical baseline Orders owner adapter and six-owner adapter composition; the contract committed-day read-model helper; and the order-terms empty-staff mutex read-model guard.
- Legacy Streamlit/UI API-client and UI-boundary tests under flat `tests/` remain deferred to UI retirement rather than being misfiled as current Orders owner-local coverage.
- Cross-domain cancellation, terms-correction, and contract-completion flows that prove Scheduling, Client Finance, or Payroll impacts remain at their higher verification boundary; owner-local infrastructure helper guards may be extracted when their direct SUT belongs to one owner.
- Historical baseline anomaly/projector delivery, persistence, and read-model tests remain at the higher Anomalies/projector boundary even when their route or payload is order-scoped.
- Disposable-MySQL/E2E, migration/schema, durable-job, and Task97 acceptance/governance tests remain higher in the tree.
- The current flat-test audit found no additional high-confidence Orders owner-local tests outside these documented higher or other-owner boundaries; admit future cases by current behavior/contract search rather than filename alone.
