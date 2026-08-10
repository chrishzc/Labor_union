---
scope: 00_Global_共同契約
status: proven-current-evidence
verified_at: 2026-08-09
---

# Global 共同契約重新驗證收據

- 原始 Inventory v2-only 核准已正確標示為歷史範圍；現行變更僅能依後續人工核准的
  exact-scope Work Package 執行，不能自動擴張。
- typed command、idempotency、durable job、request supersession 與正式 Apply 不樂觀成功的
  共用契約，都由下列 current-source tests 覆蓋。

```text
durable job / UI state / performance policy / ingestion / assignment workflow
25 passed in 1.09s

validate_formal_architecture_baseline.py
writers=669 legacy_runtime_callers=0
formal_architecture_baseline_validated
```
