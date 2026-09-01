# Module: matching-coordination-delivery

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
將 Scheduling M3 已提交且具 exact recipient/configuration snapshot 的 owner intent，投影為既有 LINE delivery task；重播由 delivery idempotency 收斂。此模組不讀寫 Scheduling root、不執行 provider effect，並可透過 LINE-006 typed current-fact readback 驗證目前 predicate。
Success bilateral envelopes are informational-only; a bounded worker records typed legacy/manual fallbacks and continues later immutable rows.

## Implementation
- primary: `subsystems/line/matching_coordination_delivery.py`
- source adapter: `infrastructure/mysql/line_matching_coordination_delivery_source.py`
- projection adapter: `infrastructure/mysql/line_matching_coordination_delivery_projection.py`
- worker: `subsystems/line/matching_coordination_delivery_worker.py`
- customer-service handoff source: `infrastructure/mysql/matching_coordination_customer_service_source.py`
- customer-service handoff worker: `subsystems/customer_service/matching_coordination_worker.py`

## Contracts
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-line-modules-1-4-closure-spec-gap.md` §5 P5 (`R5-DELIVERY`, `R5-LINE006`)
- `subsystems/line/delivery_contracts.py`
- `subsystems/line/notification_failure_current_fact.py`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/matching-coordination-delivery/contract/`

## Change triggers
Reconcile when M3 owner-outbox payload validation, delivery-task projection, local/mock outcome, or LINE-006 readback boundary changes.
