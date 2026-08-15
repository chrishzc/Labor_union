---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: LINE Integration / Developer Experience
priority: P0
---

## Exact write set（決策紀錄收斂）

- `config/line_menu.json`
- `line/static/gateway.html`
- `subsystems/line/service_help_application.py`
- `scripts/update_local_database.py`
- `scripts/migrate_preserved_database_additive_schema.py`
- `.env.example`
- `README.md`
- `tests/line/infrastructure/test_line_liff_entrypoint.py`
- `tests/test_line_customer_service_first_release.py`
- `tests/test_customer_service_partial_recovery_disposable_mysql.py`
- `tests/test_update_local_database_docker_client.py`

共享 schema assembly、release catalog、manifest 或 migration metadata 不因本清單自動取得寫入授權；
live inventory 若證明必須修改，須依資料庫變更執行門另行擴充已核准範圍。

# 82 LINE 服務登記 LIFF 與 Docker MySQL Client Work Package

## 人工核准與場景

2026-08-13 使用者授權修復：一般用戶點選 Rich Menu「服務登記」時，目前送出普通文字，
webhook 已處理但不會開啟登記頁。部分開發者的 MySQL 亦只在 Docker 容器內，無法使用 host CLI。
後續實測發現舊資料庫只有 `customer_service_tickets`、缺少同一 185 artifact 的 events table，
啟動檢查與 preserve-data update 因 partial 而安全停止；使用者再授權修復此本機升級路徑。

## 範圍與不變量

- `服務登記` 必須是 `?target=registration` 的 LIFF URI，gateway 導向 `/line-registration`；新版不產生文字 webhook。
- 已發布舊版仍送出 `服務登記` 文字時，canonical webhook 回覆同一個無時效 LIFF URL；不得建立 15 分鐘 identity flow。
- canonical DB rich-menu revision 仍是執行期 SSOT；設定檔只提供可審核預設。既有非空 DB revision 不得被 bootstrap 覆寫。
- 實際 LINE 發布必須由 authenticated Rich Menu Preview／Apply 執行；本工作包不自動呼叫 provider。
- 未安裝 host MySQL CLI 時，若 Compose 預設 `mysql_db` 正在執行，升級器自動使用其 MySQL CLI；自訂容器名以 `.env` 的 `MYSQL_CONTAINER` 覆寫，不提交個人 `.env`。
- 185 只允許 tickets 完整 exact、events 完全 absent 的既知 statement boundary 在 candidate 續跑；其他 partial／drift fail closed。
- 不修改 schema SQL、release identity、system seed 或 business rows；source 維持唯讀並沿用驗證後同名替換。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | 既有 185 第二段 CREATE TABLE 的 candidate-only recovery | exact 後 skip；source dump rollback |
| system-seed | 無 | 不適用 |
| business-row-backfill | 無 | 不適用 |
| destructive | 無新增；沿用驗證後同名替換 | source dump rollback |

## 驗收

1. 設定、gateway 與 legacy-text regression 證明「服務登記」使用客戶登記長效 LIFF URL。
2. `.env.example` 與 README 提供 Compose 預設容器，並說明自訂 Docker MySQL client 設定。
3. 客戶端既有 DB Rich Menu 需由管理端 Preview／Apply 更新並發布後才會生效；未執行時保留舊版本，不能宣稱已切換。
4. Docker MySQL 8.0.46 完成 partial source → dump → candidate → 185 apply → exact；source 不被修改。

## 2026-08-15 非實機收尾

已完成靜態 write-set 對照：`service_registration` 使用 LIFF `?target=registration`，gateway 導向
`/line-registration`，舊文字 webhook 回覆長效 LIFF URL；本機 updater 可使用預設 `mysql_db` 或
`MYSQL_CONTAINER`，185 partial recovery 僅接受已宣告 tickets-exact/events-absent 邊界。`.env.example`、
README 與 focused contract tests 均已對應。剩餘 gate 僅為管理端 Rich Menu Preview／Apply 的實際發布
驗收，以及 Docker MySQL partial source→candidate→exact engine receipt；未完成前維持 `in-progress`。
統一交接紀錄見
`document/架構重整/03_追蹤清單與證據/evidence/2026-08-15_wp73_wp77_wp82_non_engine_closeout.md`。
