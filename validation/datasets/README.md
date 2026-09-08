# UI 驗收測試資料集 v1

此資料集只可建立在名稱符合 `lu_test_dataset_*` 的乾淨 MySQL schema。它不覆寫候選庫或正式庫。

## 建立與驗證

先以 `scripts/bootstrap_disposable_mysql_schema.py` 建立一個新的 schema，再執行：

```powershell
.\.venv\Scripts\python.exe scripts\seed_ui_validation_dataset.py `
  --host 127.0.0.1 --port 3306 --user root --password <password> `
  --database lu_test_dataset_v1 --confirm-database lu_test_dataset_v1

.\.venv\Scripts\python.exe scripts\verify_validation_dataset.py `
  --host 127.0.0.1 --port 3306 --user root --password <password> `
  --database lu_test_dataset_v1
```

驗證輸出 `valid: true` 與 `verdict: blocked_as_expected` 表示刻意保留的訂單阻擋條件正確存在，而非資料建立失敗。

## 在既有 UI 檢查

1. `📦 訂單與帳務管理系統 → 📊 訂單資訊總覽`：選擇 `DSV1-CASE-0001`，確認狀態為「洽談中」，並顯示「缺少外部契約識別、正式服務日尚未建立」。
2. `📦 訂單與帳務管理系統 → 💳 銀行流水匯入與帳務修正`：批次 `finance-import-batch:1` 顯示一筆待人工確認列；按「使用第一筆待確認銀行列」會將 `finance-import-row:1` 預填到人工修正入口。
3. `DSV1-BECLASS-0002` 建立一筆待修正的 BeClass root，並確認其 outbox 已投遞。客戶 owner command 尚未配置時，資料集不會旁路該 command 自動修正資料或宣稱有可用的 UI 修正流程。

此版本故意尚未提供合約完成、正式指派、月曆、薪資與補助的 happy path。這些都依賴尚未存在的受控 `contract_identity` 整合入口，不能以 SQL 假造。
