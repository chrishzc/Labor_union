# Module: registry-deletion

## Parent
- domain: `global`
- subsystem: `registry-deletion`

## Responsibility
UI 開啟詳情時借用既有 auth `/me` 回讀 root，明確顯示「刪除此案件」；權限查詢失敗可重試，不以舊快取授予／隱藏 mutation。
僅 root 可永久刪除案件及 case-owned 關聯資料，適用於未簽約與已簽約案件。共用 Client、其他案件與月嫂保留。失敗時 rollback，成功後可從去個資 receipt 重播。
Append-only trigger 例外要求同案 pending claim 與 row ownership。connection context 在成功或失敗後清除。Guard 拒絕時完整 rollback 並返回 typed 409。

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
- `db/schema_parts/1080_registry_case_deletion_signing_guards.sql` — fresh schema 與 preserve-data 升級使用同一版案件刪除 trigger。
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
- `.arch-map/requirements/33_案件與月嫂整合名冊正式規格.md` RD-1／RD-A1～A5。

## Verification
- layout_status: `custom_current`
- layout_basis: 共用 coordinator／UI 的 root 與交易 oracle 歸 Global；Case canonical Client binding oracle 留在 Client Profile 模組。
- test_root: `tests/domains/global/subsystems/registry-deletion/modules/registry-deletion/`
- test_root: `ui_react/src/tests/domains/global/subsystems/registry-deletion/modules/registry-deletion/`
- integration_root: `tests/domains/clients/subsystems/client-profile/modules/profile-change/contract/test_case_registry_deletion.py` — 既有合成案例核對客戶版本不符時不寫入、不提交；協調器也核對案件版本。

## Change triggers
Reconcile when authority、deletion targets、relation guards、entrypoints、receipt or verification roots change.
