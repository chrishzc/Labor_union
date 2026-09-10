# Module: complaint-ingress

## Parent

- domain: `external-integration`
- subsystem: `line`

## Responsibility

將 LINE 客訴語句經 `complaint.v1` closed normalizer 導入 Customer Service
escalation 的 caller-owned UoW，並承接真人轉接確認／active conversation hold／原 requester
恢復 AI：自然語句確認前零 ticket／hold，明確 postback 才建立去敏 ticket、automation
hold、masked alert intent 與 durable notice；requester resume 由 Customer Service owner 原子結案並
release hold。LINE 不擁有客服、Payroll 或 assignment root。

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

Requester resume 必須綁定同一 LINE identity 與 conversation hold；只允許
`open | claimed | handling` 對話型 escalation，並沿 owner version／lock 防止與後台 resolve 競爭。
