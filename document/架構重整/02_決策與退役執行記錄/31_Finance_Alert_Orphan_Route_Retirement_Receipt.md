---
doc_type: receipt
date: 2026-08-07
---

# Finance Alert Orphan Route Retirement Receipt

日期：2026-08-07

## 背景

`23_Legacy_Retirement_Wave_2B_2_Finance_Alert_Module_Removal_Receipt.md` 已於
2026-08-03 移除 `services/finance_alert_workflow.py` 等三個 legacy service，
canonical 替代鏈確立為 `api/routes/anomaly_registry.py` →
`subsystems/anomalies/alert_workflow.py` → UI `ui/pages/06_finance_alerts.py`。
但 `api/routes/finance_alerts.py`、`api/routes/system_alerts.py` 這兩個路由檔案
當時沒有一併移除，且一直沒有掛載到 `api/main.py`；`06_finance_alerts.py` 舊版
UI 仍呼叫這兩個未掛載的路由，形成「掛在導覽列上但實際壞掉」的孤兒功能，而正式
替代頁面 `ui/pages/anomalies/registry_panel.py` 沒有被接進任何導覽入口。本文件記
錄兩個獨立但相關的事件：另一位工程師修好 UI 端、以及本次清掉剩餘孤兒後端的過程。

## 事件一：UI 端修復（非本次 session 所做，補記錄）

commit `b4ec13b`（作者 `cassandra02477`，2026-08-07 19:34，父 commit
`0e514f5`）把 `ui/pages/06_finance_alerts.py` 整頁重建在正式
`/api/v1/anomalies` 之上，恢復 5-tab 結構（資料匯入異常／流程與系統警示／
帳務異常／服務人員／Line），服務人員分頁下再分訂單配對／待補資料／
補發送資訊／帳務逾期提醒四個子分頁。同批一併：

- `domains/anomalies/registry.py` 新增 13 個正式 `AnomalyDefinition`，從舊
  `services/anomaly_alert_detection.py` 業務規則搬過來。
- 新增 `subsystems/anomalies/process_reminder_anomaly_source.py`、
  `infrastructure/mysql/process_reminder_anomaly_source.py` 作為對應的
  root-fact 掃描器，並接進 `subsystems/anomalies/outbox_worker.py` 既有的
  60 秒背景輪詢。
- 修正 `subsystems/anomalies/alert_workflow.py` 一個既有 bug：`claim()`／
  `resolve()` 原本回傳動態物件而非 dataclass，導致
  `api/routes/anomaly_registry.py` 的 `_materialize()` 無法解開
  `PreviewFingerprint`，每次 claim/resolve 都會 500；因為 `registry_panel.py`
  之前沒有任何 caller，這個 bug 從未被踩到。
- `db/schema.sql` 補回 `orders.lifecycle_version` 欄位，與本 session 稍早
  搬出的 `schema_parts/999_v_order_details_view.sql` 相容，雙重保障全新安裝
  不會因為欄位未就緒而失敗。
- `domains/scheduling/generation.py`：`EmptyAssignmentIdentityResolution`
  的 `MappingProxyType({})` dataclass 預設值在 Python 3.11 不可雜湊，改為
  `field(default_factory=...)`。

本 session 用 `git fetch` 發現此 commit 與本機分岔，用 `git merge-tree` 確認與
本機未推送的 2 個 commit 無檔案重疊，`git merge origin/架構重整 --no-edit`
乾淨合併為 commit `605cf7c`，未產生任何衝突標記。

## 事件二：退役剩餘孤兒後端（本次 session 執行）

UI 端改接正式 API 後，`api/routes/finance_alerts.py`、
`api/routes/system_alerts.py` 徹底變成零呼叫者的孤兒檔案。逐一確認全庫無
production caller 後移除：

| Path | 移除前 SHA-256 |
| --- | --- |
| `api/routes/finance_alerts.py` | `9ad12720a0b9498d7ae592bf4b366b88808f276c74ff6b4301d2e7b3841ea313` |
| `api/routes/system_alerts.py` | `c101307747b1a782534a94318e9e52763cb364e5744ca590226d557c8354b876` |
| `ui/api_clients/finance_alert_center_client.py` | `14fe2eaf62a6fb5d88cfa712fc0b9fb40ee6a9d7d1464db4d58b5ceb2b42987a` |
| `api/schemas/finance_alert_center.py` | `b779a7422479301e8a86f7819b2da173012cffae0335885f82732abd100d4bab` |
| `tests/test_finance_alert_center_subsystem.py` | `f7273863c2acf29991f6278a2e75ef1be2050ddcd94b4605ab300d13ed5da603` |
| `tests/test_finance_alert_router.py` | `386818e691f322ffa22127cf8e73c1d3a0dc781044a02cb0ce1aa3e7217f0d79` |

判斷依據：`grep -rl` 全庫掃描 `finance_alert_center`、
`routes.finance_alerts`、`routes.system_alerts`、`services.finance_alert_workflow`，
確認唯一剩餘呼叫者就是上述六個檔案彼此互相引用，沒有其他 production／UI／
worker／outbox 呼叫。共用測試輔助 `tests/_finance_alert_mock_support.py`
維持不動（比照 23 號收據的既有結論：它仍被三個 Finance Import 整合測試使用，
不 import 任何已退役 module）。

`services/system_alert_service.py`（不同模組，供
`services/finance_import_reprocessing.py` 等使用）與相關的
`system_alerts` 資料表本身**不在退役範圍**，予以保留。

## 附帶修正：`tests/test_finance_import_staging.py`

驗證時發現 `pytest --collect-only` 對此檔案報錯，與本次退役無關，是同一批
「架構重整」路徑漂移的漏網之魚：`from services import finance_import_staging`
改為 `from subsystems.finance_import import staging`（`services.finance_import_staging`
已不存在，正式位置在 `subsystems/finance_import/staging.py`，與
[`模組正式位置對照表.md`](../03_追蹤清單與證據/模組正式位置對照表.md) 表一一致）。

## 驗證

- `PYTHONPATH=. .venv\Scripts\python.exe -c "from api.main import app"` 成功匯入。
- `uvx flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=.venv`
  回報 0 個錯誤。
- `pytest --collect-only -q`：退役前 1163 collected + 1 error，退役並修正
  `test_finance_import_staging.py` 後 **1172 collected, 0 error**。
- 全庫 `grep` 確認移除後零殘留引用。
- **實際啟動服務並在瀏覽器操作**：重啟 `uvicorn`（port 8000）與 `streamlit`
  （port 8501，均為本次修改後的程式碼），開啟「異常警示中心」頁面，5 個分頁
  （資料匯入異常／流程與系統警示／帳務異常／服務人員／Line）與服務人員分頁下
  的 4 個子分頁（訂單配對／待補資料／補發送資訊／帳務逾期提醒）皆正常渲染，
  無 traceback，空資料庫下正確顯示「目前沒有符合條件的異常」與 `(0)` 計數；
  瀏覽器 console 無錯誤訊息。

## Rollback

若需回退，`git revert` 對應的刪除/修改 commit 即可恢復上表六個檔案與
`tests/test_finance_import_staging.py` 的異動；`b4ec13b`／merge commit
`605cf7c` 的回退需另外評估，因為其他分頁功能已依賴其新增的
`domains/anomalies/registry.py` 13 個定義與 `process_reminder_anomaly_source`
掃描器。
