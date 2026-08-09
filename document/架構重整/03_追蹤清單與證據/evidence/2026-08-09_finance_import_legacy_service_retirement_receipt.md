---
scope: Finance Import legacy service module retirement
status: proven-current-source
verified_at: 2026-08-09
---

# Finance Import legacy service retirement receipt

## 判準

只有正式 runtime caller 為零、canonical replacement 已存在，且剩餘用途只是 legacy test 或
compatibility import 的 module 才可移除；不得移除 schema 所保存的 append-only dispatch event。

## 已退役路徑

- `services/finance_cancellation_code.py`：與
  `domains/finance_import/cancellation_code.py` 重複，正式 classifier 已直接使用 Domain helper。
- `services/finance_import_states.py`：沒有 production caller，只被 historical characterization test
  import；該 test 與 module 一併移除，不保留過時 state machine 作為第二契約。
- `services/finance_import_dispatch.py`：沒有 runtime caller，只將舊 import 轉接到
  `subsystems/finance_import/reconciliation_dispatch.py`；正式 typed application 已直接 import
  canonical dispatcher。

`finance_import_dispatch_events` 仍是正式 append-only schema root fact，沒有因 Python
compatibility module retirement 被移除或改寫。

## 回歸驗收

`tests/test_legacy_client_receipt_dispatch_retirement.py` 保留 canonical diagnostic dispatcher 的
fail-closed 行為，並明確驗證三個 retired `services/` paths 不存在。Finance Import focused suite
驗證 canonical ingestion、classifier、application、reprocessing 與 schema 的既有契約。

```text
Finance Import suite + canonical cancellation code + retirement guard
113 passed, 20 skipped

formal_architecture_baseline writers=669 legacy_runtime_callers=0
formal_architecture_baseline_validated
sha256=40d10928ff3af03b035d3d49b7b182ae2325ee26731ac8950efadca0bdcf91e3
```
