subsystem: orders
parent_domain: orders
architecture: ../../../../../domains/orders/subsystems/orders/index.md
test_root: tests/domains/orders/subsystems/orders/
integration_root: tests/domains/orders/subsystems/orders/integration/
fixtures_root: tests/fixtures/
modules:
  historical-adoption:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-adoption/

# Exceptions
- `historical-adoption` — disposable-MySQL workbook integration remains at `tests/integration/test_historical_order_workbook.py`; it is a higher-boundary `layout_gap`, not duplicate owner-local coverage.
- Current owner-local coverage includes Historical Adoption; cancellation route/read-model; actual-start workflow; calendar/detail/summary queries; lifecycle authoritative facts/loaders; reopen workflow/router; auto-completion API/routes/workflow; lifecycle control/deposit/impact-writer contracts; card/stage projections; historical review remediation API/workflow/repository; historical completion API/oracle/projector/query; service-date confirmation domain/router; historical operational baseline domain/catalog/API/workflow/repository/owner-vector; historical warning mapping; the historical baseline Orders owner adapter; and the contract committed-day read-model helper.
- `tests/test_order_cancellation_api_client.py` directly exercises legacy `ui.api_clients` and remains deferred to Streamlit retirement rather than being misfiled as current Orders coverage.
- Cross-domain cancellation, terms-correction, and contract-completion flows that prove Scheduling, Client Finance, or Payroll impacts remain at their higher verification boundary.
- Disposable-MySQL/E2E, migration/schema, durable-job, and Task97 acceptance/governance tests remain higher in the tree.
- Other Orders focused tests may still be flat under `tests/`; admit by current behavior/contract search rather than broad scan.
