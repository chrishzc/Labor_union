---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Orders / Anomalies
priority: P0
---

# 歷史訂單匯入警示中心導航 Work Package

## 人工裁決與範圍

承接 WP90 與 2026-08-15 使用者裁決：異常中心只顯示去敏警示、追蹤狀態與導向 owning 業面，不可
輸入、傳遞或套用歷史訂單修正值。既有 historical-order review root 及其 committed outbox 依已登錄
issue code 建立 field-level tracking task；UI-neutral action 只指向既有資料匯入中心的歷史訂單流程。

## Write set

- `domains/orders/historical_order_warning_review.py`
- `subsystems/anomalies/historical_order_adoption_outbox_consumer.py`
- `subsystems/anomalies/outbox_worker.py`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `api/schemas/import_warning_tracking.py`
- `ui/pages/06_finance_alerts.py`
- focused 與 disposable MySQL tests，以及本 Work Package／active index。

無 schema、migration、Orders mutation endpoint、assignment command、React runtime、LINE side effect 或
金融資料寫入。本包不把 unknown historical issue 猜成可操作類型。

## Mapping 與不變量

| review issue | logical code | field path |
|---|---|---|
| `staff_missing`／`historical_staff_not_found` | `ORDER-HIST-STAFF-001` | `$staff` |
| `staff_ambiguous`／`historical_staff_ambiguous` | `ORDER-HIST-STAFF-002` | `$staff` |
| `historical_assignment_conflict`／known caregiver evidence issue | `ORDER-HIST-ASSIGNMENT-001` | `$assignment` |
| known status／date／nonempty conflict issue | `ORDER-HIST-FIELD-001` | exact field or safe synthetic path |

每個 occurrence 使用 immutable source event identity；投影初始 event 為 system `opened` version 1；replay
不得新增 occurrence、event 或 current task。`closed` 只表示人工追蹤結束，不能表示 Orders／assignment
已修正；正式資料仍只由 owning typed Preview／Apply command 寫入。

## Acceptance

- outbox consumer 與 architecture worker 能將已提交 review 投影為 canonical umbrella alert 和 field-level
  tracking task，且只有遮罩 case identity 與 bounded evidence 可穿越。
- Query action 是 stable typed identifier，不回傳 URL、raw workbook、candidate、corrected payload 或 root id。
- unknown issue 無 action/task；existing tracking Preview／Apply 合約不回歸。
- focused tests、disposable MySQL replay evidence、UI navigation smoke 與 no-schema gate 完成前維持
  `in-progress`，不得封存或宣稱 WP90 complete。

## Closure

WP90 completion receipt 已承接歷史訂單 warning projection、owner navigation、replay 及 no-schema
驗收；本文件不再保有 active write set。
