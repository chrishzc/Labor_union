# LINE AI 客服題庫 Production 匯入操作手冊

## 用途與邊界

本手冊供 production 或 production-like 測試環境首次建立獨立資料庫時，將 repository 內建的 54 題 LINE 常見 QA 匯入正式 Knowledge catalog。UI 與 CLI 都只補缺少的題目，不覆寫既有人工修訂；內建標示啟用且仍為原始 v1 草稿的題目會發布並建立索引工作。

本操作不修改 schema、不啟動 Knowledge worker、不部署服務，也不直接呼叫 LINE provider。需要 release／cutover plan、backup 與 terminal receipt 時使用 CLI；一般獨立主機首次補齊可使用受權限保護的管理端按鈕。

## 前置條件

- 使用與目標服務相同的程式版本及 `.env`。
- `APP_ENV`、`DB_HOST`、`DB_DATABASE` 必須明確設定；`--target-database` 必須與 `DB_DATABASE` 完全相同。
- 資料庫已套用 current Knowledge schema。
- 指定的 `--actor-username` 必須是資料庫內已啟用的管理員，操作會以其 ID 保存 audit／publisher lineage。
- Apply 前必須完成該目標資料庫的 MySQL／MariaDB dump；dump header 必須可辨識目標 database。
- plan、backup 與 terminal receipt 應保存於受控、非公開的位置；不得包含密碼或連線密鑰。

## 1. 從管理端一鍵匯入

1. 登入管理端，進入「LINE 專區 → AI 客服工作室 → 常見 QA」。
2. 按「匯入／補齊內建 54 題」。
3. 確認提示中的「不覆寫既有編修」後執行。
4. 等畫面重新載入，確認總數、本次補入數與發布數。
5. 等「AI 索引」成為 `READY`；未 READY 前題目尚未正式供 AI 客服使用。

操作帳號必須同時具有 Knowledge 管理、發布與重建索引權限。重複執行是安全的：已存在的題目會跳過，人工修訂不會被內建內容覆寫；若沒有可發布的新草稿，也不會建立多餘的索引工作。

## 2. CLI：產生零寫入計畫

以下命令會連線唯讀檢查 target、schema、actor 與既有題庫，但不寫入資料庫：

```powershell
.venv\Scripts\python.exe -m scripts.import_builtin_knowledge_catalog `
  --dry-run `
  --target-database <DB_DATABASE> `
  --actor-username <管理員帳號> `
  --receipt-path scratch\knowledge-catalog\plan.json
```

執行者必須確認輸出：

- `catalog_count` 應為 54，`enabled_count` 應為 40。
- 新資料庫通常是 `missing_count=54`、`publish_candidate_count=40`。
- `preserved_modified_count` 非 0 代表已有人工修訂；這些題目會保留且不自動發布。
- `target_database`、`target_server`、`actor_username` 必須符合本次核准範圍。

## 3. CLI：Apply

先依既有資料庫備份程序產生 `<backup.sql>`，再執行：

```powershell
.venv\Scripts\python.exe -m scripts.import_builtin_knowledge_catalog `
  --apply `
  --target-database <DB_DATABASE> `
  --actor-username <管理員帳號> `
  --confirm-apply "IMPORT BUILTIN QA INTO <DB_DATABASE>" `
  --plan-receipt scratch\knowledge-catalog\plan.json `
  --backup-receipt <backup.sql> `
  --receipt-path scratch\knowledge-catalog\apply.json
```

Apply 前工具會重新讀取 source 與 target；題庫檔案、資料庫狀態、server identity、actor 或 environment 與 plan 不一致時會停止且不開始匯入。成功 receipt 的 `receipt_status` 必須是 `committed`。

匯入與初始發布是兩個可恢復階段：如果題目已補入但發布階段失敗，不可手動刪除資料；修正原因後重新產生 plan，再重跑同一工具。已存在題目會被跳過，仍為原始 v1 draft 的 enabled 題目可繼續發布。

## 4. 建立索引並驗收

Apply 成功且 `published_count` 大於 0 時，receipt 會包含 `index_job_id`。啟動該環境既有的 Knowledge worker，直到管理端「AI 索引」顯示 `READY`；只有 READY 後才可宣稱 AI 客服已啟用題庫。

驗收項目：

1. 管理端常見 QA 顯示 54 題。
2. 初次空庫匯入應有 40 題「已發布」；14 題維持不可自動回答狀態。
3. index terminal readback 為 `READY`。
4. 使用一個已發布題目的 exact question／alias 做 read-only answer 測試，答案帶有核准來源且 `authoritative=false`。
5. 保留 plan、backup、apply receipt 與驗收結果，供本次 production 測試追溯。

## 失敗與停止條件

- schema incomplete、actor 不存在／停用、target 不一致：停止，先修正環境。
- plan drift：重新 dry-run 及人工確認，不得沿用舊 plan。
- `preserved_modified_count` 超出預期：停止並由 Knowledge owner 審核，不得強制覆寫。
- worker 或 index failed：題庫資料不回滾；依 worker failure readback 處理，未 READY 前不得對外宣稱啟用。
- 需要回復時，透過正式 Knowledge retire 流程停用已發布題目並保留歷程；不得直接刪除 Knowledge tables 或 revisions。
