# Workbook 匯入與預覽介面

正式寫入以經認證的現行 Web API／owner workflow 為入口。以下腳本的名稱不代表可直接更新資料庫；CLI 與可匯入函式的效果必須分開看。

| 模組 | CLI 現況 | 資料庫效果 |
| --- | --- | --- |
| `scripts/imports/import_client_hcm.py` | 函式庫，沒有獨立 CLI。提供 HCM 正規化與現行匯入流程使用的函式。 | 寫入由呼叫端的 Case Import workflow 與 Unit of Work 管理；不是「既有案件直接複寫更新」命令。 |
| `scripts/imports/import_client_beclass.py` | 預設委派 workbook 預演；`--historical-apply` 即使通過目標檢查仍會拒絕。 | 預覽不寫入資料庫；不得將函式可匯入解讀為 CLI Apply 已開放。 |
| `scripts/imports/import_staff_beclass.py` | 預設委派 workbook 預演；`--historical-apply` 仍被拒絕。 | 同上；正式採用由現行 Staff 歷史 workbook workflow 處理。 |
| `scripts/imports/import_finance_excel.py` | 只提供銀行 workbook 格式預覽；`--apply` 已退役。 | 不建立 Finance Import 批次、不核銷、不寫入 payments；`--confirm-database` 不會開放寫入。 |
| `scripts/imports/rehearse_case_import_workbook.py` | HCM／Client BeClass／Staff BeClass 來源診斷。 | 不連線資料庫，不建立業務根事實。 |

## 可用的預覽範例

從 repository root，使用已安裝相應 workbook 依賴的 Python 環境：

```bash
python -m scripts.imports.import_finance_excel --excel-path bank.xlsx
python -m scripts.imports.import_finance_excel --excel-path bank.xlsx --report-path preview.json
python -m scripts.imports.import_client_beclass clients.xlsx
python -m scripts.imports.import_staff_beclass staff.xlsx
```

財務預覽輸出包含 `mode: dry_run`、`transaction_outcome: not_written`、格式及正規化列數，不表示已完成業務匯入。`--report-path` 會建立本機 JSON 報告，因此「不寫入」在此指資料庫，不是 filesystem。

`--apply`、`--historical-apply` 等舊選項不是替代正式 API 的操作方式；此文件不提供繞過其拒絕條件的命令。

## 驗證

`tests/test_finance_import_cli_test_adapter.py` 驗證財務預覽與 Apply 拒絕行為；`tests/test_wp73_workbook_rehearsal_cli.py` 覆蓋來源預演。CI 與人工 focused test 的實際執行範圍見 [scripts_map.md](../scripts_map.md)，不因測試檔存在就宣稱 CI 已執行。
