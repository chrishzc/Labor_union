# Subsystem: line

## Parent
- domain: `external-integration`

## Responsibility
處理 LINE webhook、identity binding/review、LIFF/self-service transport、rich menu／message delivery與committed delivery worker composition；擁有 identity root／owner projections／current-fact interpretation，business mutation回owning Subsystem。

## Modules
- `line-identity-management` — canonical LINE identity binding and review persistence; path: `modules/line-identity-management.md`

## Dependencies
- outbound: `scheduling | case-import | orders | other owning domains` — typed commands only。
- outbound: external LINE provider — only after committed durable intent/outbox when side effect is required。
- inbound: `anomalies` — 只透過`LineIdentityCurrentFactQuery/Readback`讀取LINE-004 owner facts；不授權Anomalies修正root。

## Contracts
- `subsystems/line/` — LINE application workflows
- `subsystems/line/identity_management_contracts.py` — LINE-004 typed zero-write current-fact contract與合法雙角色 interpretation
- `infrastructure/mysql/line_identity_management_repository.py::current_fact` — root及owner projections唯一typed readback adapter
- `api/routes/line_identity_management.py::GET /api/v1/line/identity-bindings/{line_user_id}/current-fact` — reader-protected current-fact entry；external caller evidence仍deferred
- `line/` — LINE transport/provider adapter root
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — self-service contract
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — identity contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/external-integration/subsystems/line/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/`.
- higher_boundary: `tests/test_line_identity_management_first_release.py`與Anomalies LINE-004 consumer integration test。
