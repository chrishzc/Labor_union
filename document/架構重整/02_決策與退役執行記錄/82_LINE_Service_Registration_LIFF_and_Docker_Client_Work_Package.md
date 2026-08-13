---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: LINE Integration / Developer Experience
priority: P0
---

# 82 LINE 服務登記 LIFF 與 Docker MySQL Client Work Package

## 人工核准與場景

2026-08-13 使用者授權修復：一般用戶點選 Rich Menu「服務登記」時，目前送出普通文字，
webhook 已處理但不會開啟登記頁。部分開發者的 MySQL 亦只在 Docker 容器內，無法使用 host CLI。

## 範圍與不變量

- `服務登記` 必須是 `?target=registration` 的 LIFF URI，gateway 導向 `/line-registration`；新版不產生文字 webhook。
- 已發布舊版仍送出 `服務登記` 文字時，canonical webhook 回覆同一個無時效 LIFF URL；不得建立 15 分鐘 identity flow。
- canonical DB rich-menu revision 仍是執行期 SSOT；設定檔只提供可審核預設。既有非空 DB revision 不得被 bootstrap 覆寫。
- 實際 LINE 發布必須由 authenticated Rich Menu Preview／Apply 執行；本工作包不自動呼叫 provider。
- `.env` 可選填 `MYSQL_CONTAINER`，讓保留資料升級在該 Docker 容器執行 MySQL CLI；容器名稱是開發者本機設定，不得寫死或提交 `.env`。
- 不新增 schema、system seed、business-row backfill 或 destructive DB 操作。

## 驗收

1. 設定、gateway 與 legacy-text regression 證明「服務登記」使用客戶登記長效 LIFF URL。
2. `.env.example` 與 README 說明 Docker MySQL client 設定及 per-developer 容器名稱。
3. 客戶端既有 DB Rich Menu 需由管理端 Preview／Apply 更新並發布後才會生效；未執行時保留舊版本，不能宣稱已切換。
