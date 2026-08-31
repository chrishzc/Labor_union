# Module: line-identity-management

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
持久化同一套 role-scoped canonical LINE identity binding、event、readback 與 application contract；customer／staff 可並存，admin 維持排他。同類客戶案件替換只更新 customer role，保留 staff role，並由LINE Identity正常流程完成；不追加LINE-004 anomaly recheck。此 Module 只擁有一個 nullable selected-role 狀態與一個 bounded binding-failure streak，第二次失敗以既有 Customer Service typed application 冪等建立客服單。

## Implementation
- primary:
  - `domains/line/identity_binding.py`
  - `subsystems/line/identity_application.py`
  - `subsystems/line/identity_management_application.py`
  - `subsystems/line/identity_management_contracts.py`
  - `subsystems/line/staff_retirement_effect.py`
  - `infrastructure/mysql/line_identity_review_repository.py`
  - `infrastructure/mysql/line_identity_management_repository.py`
  - `db/schema_parts/1019_line_identity_role_scope.sql`
  - `db/releases/labor_union_validation_schema_v1.sql` — generated Global validation composition; listed as an exact touched artifact, not LINE-owned business semantics.
  - `scripts/migrate_preserved_database_additive_schema.py` — existing Global migration runner with this release's exact registration/descriptor only.
- entrypoints:
  - `MySqlLineIdentityRepository.replace_subject`
  - internal typed applications only; no new public route or provider entrypoint.

## Dependencies
- outbound: `external-integration/line` — implements the LINE identity typed repository port used by the identity management application.
- outbound: `customer-service` — on the bounded second binding failure only, invokes the existing typed escalation application inside the caller-owned Unit of Work.
- inbound: `subsystems/line/identity_management_application.py` — coordinates replacement validation, owner projections, audit and the outer Unit of Work.
- outbound: `anomalies` — LINE identity replacement不產生LINE-004 anomaly；LINE-006另由notification-failure typed readback提供必要 owner facts，Anomalies不寫LINE root。
- inbound: `staff/module:staff-retirement` — only after a committed Staff retirement candidate, through the typed effect port and shared outer UoW.

## Contracts
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9 — one role-scoped contract, selected-role state and bounded failure streak.
- `domains/line/identity_binding.py` — role-scoped claim/snapshot plus bounded streak transition.
- `db/schema_parts/1019_line_identity_role_scope.sql` — additive shared root/event successor, selected-role column and streak root.

## Verification
- static:
  - `python -m py_compile domains/line/identity_binding.py subsystems/line/identity_application.py subsystems/line/identity_management_application.py infrastructure/mysql/line_identity_review_repository.py infrastructure/mysql/line_identity_management_repository.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/line-identity-management/`

## Provenance
- `line_identity_role_bindings` and `line_identity_role_binding_events` are the single shared role-scoped successor; legacy roots/events are migration/compatibility input only — `architecture_declared` — `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` §9.
- Role selection, bounded streak and same-type replacement tests are owned by this Module test root — `source_observed` — `tests/domains/external-integration/subsystems/line/modules/line-identity-management/`.

## Change triggers
- Reconcile this module when role-scoped binding ownership, selected-role state, bounded streak, replacement constraints, Staff retirement adaptation, persistence implementation root, Customer Service typed dependency, or canonical module test root changes.
