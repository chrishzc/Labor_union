# Module: registry-deletion

## Parent
- domain: `global`
- subsystem: `registry-deletion`

## Responsibility
UI 開啟詳情時借用既有 auth `/me` 回讀 root，明確顯示「刪除此案件」；權限查詢失敗可重試，不以舊快取授予／隱藏 mutation。
僅 root 可刪除未簽約案件及 case-owned 關聯資料；任一相關月嫂／客戶曾簽回即阻擋。共用 Client、其他案件與月嫂保留。無通用 table selector，失敗 rollback，成功後可從去個資 receipt 重播。
既有 append-only triggers 預設保留；例外必須符合本次 pending claim、unsigned case、row ownership 與未完成 receipt。connection context 在成功／失敗清除；明確 guard 拒絕為完整 rollback 的 typed 409。

## Implementation
- `subsystems/registry_deletion/coordinator.py`
- `subsystems/registry_deletion/__init__.py`
- `infrastructure/mysql/registry_deletion_repository.py`
- `infrastructure/mysql/registry_case_deletion.py`
- `api/dependencies/registry_deletion.py`
- `api/schemas/registry_deletion.py`
- `api/routes/registry_deletion.py`
- `ui_react/src/api/registry_deletion_client.ts`
- `ui_react/src/components/RegistryDeletionPanel.tsx`
- `ui_react/src/components/RegistryDeletionPanel.css`
- `db/schema_parts/238_registry_case_deletion_guards.sql` — fresh guards permit only the active root unsigned-case command scope.
- `db/schema_parts/1060_registry_case_deletion_guards.sql` — preserve-data equivalent, retains ordinary append-only and signed-case protection.

## Dependencies
- inbound: `clients/profile-change` — ClientRosterPage 與 client_registry router 組合 typed Case deletion。
- outbound: `global/migration/nas-runtime-permissions` — NAS locked-definer 固定 `lu_nas_delete_unsigned_case_v2`；追加 command key 並驗 pending claim，runtime 不取得直接 DELETE。
- outbound: `global/migration/preserved-database-upgrade` — 1060 精確 predecessor／successor trigger descriptors 與 schema-only qualification。
- outbound: `global/shared-kernel` — actor、command digest 與 existing MySQL outer UoW。

## Entrypoints
- `GET /api/v1/admin/registries/clients/{case_no}/deletion`
- `POST /api/v1/admin/registries/clients/{case_no}/deletion/apply`

## Contracts
- `document/架構重整/01_規格基線/33_案件與月嫂整合名冊正式規格.md` RD-1／RD-A1～A5。

## Verification
- layout_status: `custom_current`
- layout_basis: 共用 coordinator／UI 的 root 與交易 oracle 歸 Global；Case canonical Client binding oracle 留在 Client Profile 模組。
- test_root: `tests/domains/global/subsystems/registry-deletion/modules/registry-deletion/`
- test_root: `ui_react/src/tests/domains/global/subsystems/registry-deletion/modules/registry-deletion/`
- integration_root: `tests/domains/clients/subsystems/client-profile/modules/profile-change/contract/test_case_registry_deletion.py`

## Change triggers
Reconcile when authority、deletion targets、relation guards、entrypoints、receipt or verification roots change.
