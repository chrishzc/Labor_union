# Task96 異常分類 UX 規格與任務包 receipt

- `date`: 2026-08-28
- `status`: `passed`
- `authority`: 人工要求每個異常分類顯示數量，並禁止匯入待辦在無關分類顯示。
- `spec`: `02_決策與退役執行記錄/PROV-20260828-anomaly-category-count-import-section-ux-spec.md`，`SPEC_READY`。
- `task_pack`: `02_決策與退役執行記錄/PROV-20260828-anomaly-category-count-import-section-ux-work-package.md`，`PACKAGE_READY`。
- `live_evidence`: `AnomaliesPage.tsx` 只為「全部」附數量，而 import-warning section 目前無條件 render。
- `implementation_status`: `not_run`；本 receipt 只證明任務已正式收錄且無規格 blocker。
- `priority_return`: 收錄後回到 Task96 異常人工修復閉環與 DB 另機驗收主線。
