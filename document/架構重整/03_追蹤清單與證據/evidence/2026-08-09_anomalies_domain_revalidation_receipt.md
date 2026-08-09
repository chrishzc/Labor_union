---
scope: 06_Anomalies_Domain
status: verified
verified_at: 2026-08-09
---

# Anomalies Domain 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/06_Anomalies_Domain.md`
- 決策／退役記錄：
  - `21_Legacy_Retirement_Wave_2B_Anomalies_Caller_Migration_Decision_Package.md`
  - `22_Legacy_Retirement_Wave_2B_1_Anomalies_Caller_Exit_Receipt.md`
  - `23_Legacy_Retirement_Wave_2B_2_Finance_Alert_Module_Removal_Receipt.md`
  - `31_Finance_Alert_Orphan_Route_Retirement_Receipt.md`
  - `32_Client_Refund_Return_Anomaly_Package.md`
  - `43_Writer_Inventory_Scope_and_Legacy_Reprocess_Shutdown_Work_Package.md`

## 本次落地與邊界收斂

- canonical Anomalies chain 已由 `/api/v1/anomalies`、
  `/api/v1/anomaly-recovery`、Anomaly registry／workflow、root-fact projectors、
  outbox worker 與 Streamlit registry panel 組成；legacy Finance Alert routes、clients
  與 service callers 不在 production source tree。
- `finance_import_manual_review` 與 `IMPORT-006` 保持不同根因與投影路徑；退款退回
  `CLIENTREFUND-001` 維持 immutable review event、outbox、replay 與由合法
  `refund_reversal` 根事實驅動的 auto-resolve。
- `CorrectAndPostFinanceImportRow` 的原子交易仍同時涵蓋 classification、owning-domain
  ledger／allocation、reconciliation receipt、outbox 與 alert resolve event；但 resolve
  event 的 SQL writer 已從 Finance Import repository 移至 Anomalies MySQL adapter。
  Finance Import 只呼叫 typed adapter，因此 anomaly workflow event 的 writer ownership
  集中於 Anomalies adapters，同時不犧牲同一交易的 rollback 保證。
- 新增 `test_anomaly_finance_import_writer_boundary.py`，固定驗證 Finance Import source
  不得直接 INSERT `anomaly_workflow_events`。

## 驗證結果

```text
.venv\Scripts\python.exe -m pytest -q [Anomalies root-fact / Finance Import
review / refund-return / outbox / system projection / UI contract focused suite]
86 passed, 1 skipped in 4.62s
```

同輪 static scan：legacy `finance_alert_workflow`、`finance_alert_events`、
`finance_alert_detection`、legacy routes 與 finance-alert center client 在 production
roots 的引用數均為 0；`INSERT INTO anomaly_workflow_events` 僅存在
`anomaly_root_fact_projection_repository.py` 與 `anomaly_registry_repository.py` 兩個
Anomalies adapters。相關 API、projector、worker、UI 與 adapters 均通過 `py_compile`。

退款退回的 disposable MySQL E2E 已於 Client Finance 規格重新驗證時在 fresh `mysql:8.4`
容器通過，未使用既有正式資料庫；本次 writer-boundary 收斂未改變其 Finance Import
correction／ledger 行為。

## 追加複驗（2026-08-09）

- root-fact／Finance Import review／refund return／outbox／system projection／UI contract
  focused suite 重跑：`99 passed in 5.04s`。
- 再次掃描確認 `/api/v1/finance-alerts` 與 `/api/v1/system-alerts` 僅在已退役的 UI
  說明文字中出現；實際路由與 UI client 均使用 `/api/v1/anomalies` 或
  `/api/v1/anomaly-recovery`。

## 遠端異常功能合併裁決（2026-08-10）

- 接受遠端讓 `IMPORT-006` 出現在 canonical 異常中心的功能目的，但拒絕同時維護
  `system_alerts` 與 `anomaly_current_alerts` 兩份可變 current-state。
- 初次 Finance Import 完成仍在原交易內投影；正式 historical reprocess 使用既有
  `finance_import_outbox` 的 `historical_reprocess_completed` 事件，以 durable event id
  作 monotonic source version，避免 active／inactive 往返時重用 workflow event key。
- 移除每 60 秒單交易全表掃描 completed batches 的合併版本；一般 Query 與 worker
  不做 unbounded scan。
- projector idempotency key 改為 canonical tuple 的 SHA-256 固定長度值；schema v9
  仍保留欄寬調整，以相容已存在與其他來源的歷史 key。
