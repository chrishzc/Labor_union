# Module: nas-runtime-permissions

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
對單一 NAS 隔離資料庫安裝固定用途程序、locked definer 與 management／line／access／maintenance 的物件及欄位權限。只提供 migration／部署 substrate，不擁有業務規則或 outer UoW。

## Implementation
- primary: `infrastructure/mysql/nas_permissions.py`
- fixed operations: `infrastructure/mysql/nas_mutations.py`
- entrypoint: `scripts/configure_nas_permissions.py`
- connection profiles: `infrastructure/mysql/mysql_adapter.py`
- canonical additive registration release: `db/migration_releases/labor_union_2026_10_19_nas_registration_approval_v1.json`、`db/migration_releases/labor_union_2026_10_19_nas_registration_approval_v1.descriptors.json`

## Contracts
- Spec 33 RD-1：registry 專用 unsigned-case 永久刪除程序只授予 management EXECUTE；case-owned graph 的 DELETE 僅授予 locked definer，不授予 staff DELETE。caller root gate／簽回鎖／receipt 與 outer UoW 由 Global registry-deletion 擁有，不允許 LINE 執行。
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` NAS-DB-01/02/03。
- schema 先由 canonical fresh／preserve-data upgrade 處理；plan 零寫入；未知／partial／foreign grants／procedure drift 拒絕，不 reset 業務資料。
- runtime 無直接 DELETE／DDL／GRANT；固定程序僅具名 EXECUTE，沒有動態 table 參數或內部 commit。逐功能 adapter 仍由其 owning Subsystem 控制 transaction 與業務驗證。
- runtime startup 實查表、欄位及程序授權；LINE 無 core INSERT／UPDATE 或刪除程序，身分投影僅限 LINE 連結欄位。讀取的本人範圍仍由 LINE owner 驗證，不宣稱 DB row-level security。
- NAS-LINE-04：公開 LINE 的受控檔案 facts 與日誌主檔／附件／完成事件收斂為唯讀；合法操作經私人照片 transport 由原管理 profile／Scheduling writer 執行，通知 outbox／checkpoint 與 LINE 專用媒體不受影響。
- canonical inventory 同時檢查必要授權缺漏。既有 FOR UPDATE 只以本 database 的 LOCK TABLES 滿足 read-lock 前提，無額外 core DML；依 partial_revokes 處理 database wildcard，保留原有 outer UoW。

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/nas-runtime-permissions/`
- default_boundary: Module
- engine: `tests/domains/global/subsystems/migration/modules/nas-runtime-permissions/test_nas_permissions_mysql.py` — 明確 opt-in 的 localhost 隔離庫；四 profile grants／TLS 正負例、固定用途程序及 outer commit／rollback，不 reset／drop。registry 專用案件程序另由 Global registry-deletion 的 opt-in engine tests 驗證 SQL 與同一交易；不以此替代目標 NAS grants 資格。
- offline policy／plan 不代表真實 MySQL grants、DDL 或 rollback 通過；DB qualification 依 10 §9。

## Provenance
- architecture_declared: 使用者 2026-10-19 核准最終權限清單與 NAS Worker 方案。
- source_observed: 上述 installer／runtime profile 與固定程序。

## Change triggers
Reconcile when profiles、fixed procedure interface、schema prerequisites、account lifecycle 或 test root changes。
