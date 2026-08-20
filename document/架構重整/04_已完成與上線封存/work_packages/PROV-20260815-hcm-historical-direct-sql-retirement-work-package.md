---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Case Import / Global Entry Governance
domain: Case Import
subsystem: HCM historical whole-row writer retirement
implementation_authorization: granted-by-user-2026-08-15
---

# HCM Historical Whole-row Writer 退役工作包

## Scope

移除已退役 HTTP historical routes 唯一依賴的 `HcmHistoricalRowIntake`、historical service factory，以及
寫入 `clients`／`orders` 的整列覆寫 helper。現行 HCM typed Web intake、WP95 scoped resubmission 和其
partial-case validation 必須保留。

## 驗收與結果

1. historical HTTP routes 已固定 `410`，不再有 composition factory 或 direct-SQL whole-row writer。
2. `HcmLegacyRowIntake` 與 `normalize_hcm_row` 仍由 current Web／resubmission coordinator 使用。
3. focused queue、entrypoint、HCM safety／router／API client／workbook 與 disposable E2E tests：36 passed、
   7 skipped；`git diff --check` 通過。

驗收收據：`../03_追蹤清單與證據/evidence/hcm_historical_direct_sql_retirement_receipt_20260815.md`。
