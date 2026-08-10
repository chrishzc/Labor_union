---
scope: 13_規格實作完成度矩陣
status: reconciled-current-evidence
verified_at: 2026-08-09
---

# 規格實作完成度矩陣重新驗證收據

## 修正的證據漂移

- formal architecture baseline generator 與 validator 原本寫入／讀取
  `document/架構重整/evidence/formal_baseline_v1.json`，但矩陣的受管理證據位置是
  `03_追蹤清單與證據/evidence/`。兩者現已統一至後者；舊根目錄檔保留為歷史資料，
  不再被現行 validator 使用。
- BreezySign 退役前的 revalidation formal baseline：645 writer findings、legacy subsidy projection runtime callers 為 0、
  retired legacy subsidy-return module 路徑與 runtime callers 均為 0；SHA-256 為
  `b0b7ef361e68901f8add91fe986b2faa7f036efc30342dc2baf2d91a295bd100`。
- matrix 的 Historical Reprocess 改為正確記錄「強證據可自動 resolve；只有仍歧義列需
  append-only owner selection；strict batch 一列未解即 fail closed」。
- matrix 的 preserve-data complete-restart、G01–G17 manifest 與 UI request-state 表述已
  對齊本輪實作／驗證；2026-08-09 的 localhost disposable MySQL hard rehearsal 已完成
  source→backup→candidate→migration→switch→restart/read-smoke，收據置於
  `preserve_data_rehearsal_20260809/`。真實銀行樣本仍為獨立 external gate；target-host
  deployment evidence 已依決策 53 退役。
- Scheduling 的月曆、配對中心、人力配置與請假／代班選人已全部改走每頁最多 200 筆的
  typed staff summary cursor Query；全量 `GET /api/v1/staff` 已回 `410 Gone`，不再提供
  UI fallback。

## 驗收

```text
scripts/generate_formal_architecture_baseline.py
formal_architecture_baseline writers=669 legacy_runtime_callers=0

scripts/validate_formal_architecture_baseline.py
formal_architecture_baseline_validated

tests/test_formal_architecture_baseline_evidence_path.py
tests/test_legacy_subsidy_projection_boundary.py
tests/test_writer_inventory_v3_dispositions.py
5 passed in 1.69s
```

Writer Inventory v3 disposition validator 另確認 `records=658`、
`approved_to_remove=0`。此矩陣 reconciliation 不授權移除任何 inventory finding。

其中 645 是 BreezySign 退役前的歷史 snapshot；目前 formal baseline 的 669 findings
已由 current-source validator 重建，兩個數字不得互相替代或推導 removal authorization。
