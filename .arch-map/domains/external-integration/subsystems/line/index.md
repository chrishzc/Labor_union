# Subsystem: line

## Parent
- domain: `external-integration`

## Responsibility
處理 LINE webhook、identity binding/review、LIFF/self-service transport、rich menu／message delivery與committed delivery worker composition；擁有 identity root／owner projections／current-fact interpretation，business mutation回owning Subsystem。

## Modules
- `delivery-task-presentation` — LINE delivery task查詢工作台的business-facing presentation；path: `modules/delivery-task-presentation.md`
- `line-identity-management` — canonical LINE identity binding and review persistence; path: `modules/line-identity-management.md`
- `line-identity-maintenance-presentation` — LINE identity更正與解除維護的business-facing presentation；path: `modules/line-identity-maintenance-presentation.md`
- `line-identity-review-presentation` — LINE identity人工審核工作台的business-facing presentation；path: `modules/line-identity-review-presentation.md`
- `notification-rules-presentation` — LINE通知規則維護的business-facing presentation；path: `modules/notification-rules-presentation.md`
- `notification-failure-current-fact` — LINE-006 typed zero-write group readback、manual replay lineage與bounded recheck；path: `modules/notification-failure-current-fact.md`
- `mobile-assignment-review` — persisted-human mobile transport轉接既有Scheduling Assignment Plan Q/P/A/readback；path: `modules/mobile-assignment-review.md`

## Dependencies
- outbound: `scheduling | case-import | orders | other owning domains` — typed commands only。
- outbound: external LINE provider — only after committed durable intent/outbox when side effect is required。
- inbound: `anomalies` — 只透過typed LINE-004 identity與LINE-006 notification-failure current-fact readback讀取owner facts；不授權Anomalies修正root或重算Delivery。

## Contracts
- `subsystems/line/` — LINE application workflows
- `subsystems/line/identity_management_contracts.py` — LINE-004 typed zero-write current-fact contract與合法雙角色 interpretation
- `infrastructure/mysql/line_identity_management_repository.py::current_fact` — root及owner projections唯一typed readback adapter
- `subsystems/line/notification_failure_current_fact.py`與`infrastructure/mysql/line_notification_repository.py::current_failure_fact` — LINE-006 group typed readback；無aggregate persistence。
- `api/routes/line_identity_management.py::GET /api/v1/line/identity-bindings/{line_user_id}/current-fact` — reader-protected current-fact entry；external caller evidence仍deferred
- `line/` — LINE transport/provider adapter root
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — self-service contract
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — identity contract

## Verification routing
layout_status: `custom_current`

- default_boundary: Subsystem
- test_root: `tests/domains/external-integration/subsystems/line/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/`.
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_mysql_repositories.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_identity_stage4.py`
- integration_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_registration_atomicity.py`
- higher_boundary: LINE Identity first-release living baseline由Global schema/release routing分類；Anomalies consumer保留在其canonical integration root。
