# Module: complaint-ingress

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

將 LINE 客訴語句經 `complaint.v1` closed normalizer 導入 Customer Service
escalation 的 caller-owned UoW：只建立去敏 HIGH ticket、automation hold、masked
alert intent 與 durable empathy delivery；LINE 不擁有客服、Payroll 或 assignment root。

## Implementation

- `subsystems/line/runtime_human_escalation_source.py`
- `subsystems/line/service_help_application.py`
- `subsystems/customer_service/escalation_application.py`
- `subsystems/customer_service/escalation_contracts.py`
- `infrastructure/mysql/customer_service_escalation_repository.py`
- `subsystems/line/human_escalation_delivery.py`
- `infrastructure/mysql/line_delivery_task_repository.py`
- `api/routes/customer_service.py`
- `ui_react/src/pages/LineManagementPage.tsx`

## Verification

- test_root: `tests/domains/external-integration/subsystems/line/modules/complaint-ingress/`

## Safety boundary

Raw complaint text is not carried into the escalation command, ticket note, or
alert. The Customer Service owner retains its required routing identity; the
source fingerprint is evidence only. Provider delivery remains the existing
committed intent/outbox boundary.
