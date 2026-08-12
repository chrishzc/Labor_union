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
2. `異常警示中心 → 服務人員`：確認此案件的 `SCHEDULE-006` 排班天數不平衡異常。其工作流資料已驗證 `claim → resolve → reopen → auto_resolve → reopen`。
3. `📦 訂單與帳務管理系統 → 💳 銀行流水匯入與帳務修正`：批次 `finance-import-batch:1` 顯示一筆待人工確認列；按「使用第一筆待確認銀行列」會將 `finance-import-row:1` 預填到人工修正入口。
4. `異常警示中心 → 資料匯入異常`：會看到待修正的 `IMPORT-001`。在「從目前待修正異常選擇」選取項目後，將電話改為 `0987654321`、保留 `phone_invalid` 為已解決問題，依序執行 Preview 與 Apply；刷新後警示須自動解除，且會建立 `DSV1-BECLASS-0002`。關閉「僅顯示未結束異常」後，仍可看到已修正的 `DSV1-BECLASS-0001` 作為對照。

此版本故意尚未提供合約完成、正式指派、月曆、薪資與補助的 happy path。這些都依賴尚未存在的受控 `contract_identity` 整合入口，不能以 SQL 假造。
