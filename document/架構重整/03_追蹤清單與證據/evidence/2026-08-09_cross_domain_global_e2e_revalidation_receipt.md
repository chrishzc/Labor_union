---
scope: 07_跨Domain交易與pytest驗收架構
status: verified-current-source
verified_at: 2026-08-09
---

# 跨 Domain Global E2E 重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/07_跨Domain交易與pytest驗收架構.md`
- 決策／驗收依據：
  - `28_Global_E2E_Acceptance_Gap_Package.md`
  - `46_Six_Remaining_Gaps_Completion_Architecture.md`
- Global manifest：`evidence/global_e2e_manifest.json`

## 本次修復

- 將 Finance Import correction 的 anomaly workflow event writer 移至 Anomalies adapter 後，
  correction Preview 仍需要讀取 active `finance_import_manual_review` 以取得 workflow
  version；已保留該唯讀 query。正式 workflow-event INSERT 仍只存在 Anomalies adapters。
- G11 replay fixture 改為保留第一份產生的 XLSX bytes；exact replay 必須重送相同 payload，
  不能以測試中重新序列化、位元組不同的 workbook 假裝同一 command。
- Finance Import correction request 的人工原因位於 immutable selection；borrowed owning-domain
  composite 現改為使用該 validated reason，同時保留 historical reprocess request 的直接 reason。
  避免 refund／return／subsidy correction 與 historical owner selection 互相破壞。
- `global_e2e_manifest.json` 是 isolated-MySQL 執行的 source snapshot，不可宣稱自動
  涵蓋後續 dirty worktree。2026-08-09 現況稽核曾發現 10 個 mismatch；重跑受影響
  Finance Import／durable／UI scenarios 後已更新 manifest，75 個 source hash 的 mismatch
  為 0。

## 隔離驗收

所有資料庫 E2E 都在 disposable `mysql:8.4` 容器執行，僅綁定
`127.0.0.1:33308`，環境變數固定為
`LABOR_UNION_TEST_MYSQL_DATABASE=lu_test_global_e2e_20260809`。測試完成後已停止
`--rm` 容器並移除本輪 pytest workspace 暫存目錄；未連線或寫入 `union_db`。

```text
tests/test_finance_import_disposable_mysql_e2e.py
18 passed in 160.63s

其餘 G01–G07、G09、G13–G17 scenarios
22 passed in 176.94s
```

Global manifest 的 17 個 G01–G17 scenario 均為 `proven`，`not_yet_proven` 為空。對 source
漂移的範圍，fresh `mysql:8.4`（`127.0.0.1:33309`、
`lu_test_global_revalidation_20260809`）重跑 `test_finance_import_disposable_mysql_e2e.py`
為 `19 passed`，並重跑 G07／G16／G09／G17 為 `4 passed`；兩組均未使用 `union_db`。
