# Canonical empty local DB reset 工作包

- `package_id`: `PROV-20260828-canonical-empty-local-db-reset`
- `declared_status`: `approved`
- `authority`: 2026-08-28 人工明確要求把 reset 改為從目前 canonical schema 建立空白最新版 DB
- `owner`: Global Migration／Developer Local Runtime
- `scenario`: 既有本機 `union_db` 可完全捨棄，無須走 preserve-data migration

## Scope 與不變量

修改 `reset_DB.bat`、`scripts.reset_fake_database`、launcher preflight、操作文件與 focused tests。入口只允許
localhost／development 的 exact `union_db`，必須先完成 schema assembly、base schema、ordered artifacts 與
validation manifest digest 驗證，再要求操作者輸入 `RESET`。Apply 可 DROP／CREATE `union_db`，依 canonical
assembly 建立 current schema，最後 readback tables／views／triggers；不得載入 business fixture、不得操作其他
database、remote host 或 production。schema artifacts 已明列的 system seed 不屬 business fixture，維持 canonical
行為。

本包不新增 table／column／constraint／index／trigger／view，不改寫 release 或 hash-locked SQL，不授權 Agent
對既有 `union_db` 實際執行 reset。

## Change inventory

| 類型 | 內容 |
|---|---|
| schema-only | 無新 DDL；重用 current canonical assembly |
| system-seed | 無新增；只執行 assembly 既有聲明 |
| business-row-backfill | none |
| destructive | operator confirmed 後 DROP／CREATE 本機 `union_db` |

## Acceptance

1. dry-run 只檢查 canonical files／modules，零 DB side effect，不再依賴 retired v3 fixture。
2. preview 驗證 target 與全部 canonical hashes，零 DB connection，列出 assembly、terminal artifact 與
   `business_fixture=none`。
3. apply 缺 exact `--confirm-database union_db`、remote／production／非 `union_db` 全部 fail closed。
4. confirmed apply 使用 assembly 明列順序，重建後驗證 manifest database objects；failure 明示 MySQL DDL
   可能已生效，不以 rollback 偽裝完整復原。
5. README、launcher inventory、Global migration spec 與 focused tests同步。

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 本工作包與人工 authority |
| Change inventory | PASS | 上表；無 schema contract 變更 |
| Static release | PASS | canonical assembly／validation manifest focused tests；preview terminal=`1012_service_before_replacement.sql` |
| Descriptor | PASS | 不改 descriptor；current hash-locked catalog／manifest preflight通過 |
| Read-only plan | PASS | reset preview `side_effects=none`；BAT dry-run exit 0 |
| Engine verification | NOT_RUN | disposable MySQL fresh bootstrap 待驗證 |
| Developer acceptance | NOT_RUN | 不在 Agent 工作階段操作既有 `union_db` |

DB summary：`DB_CHANGE_NOT_READY`。
