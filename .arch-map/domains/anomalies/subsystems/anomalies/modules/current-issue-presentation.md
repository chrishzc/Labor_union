# Module: current-issue-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現15-code current-only清單、typed detail與closed owner action descriptor。一般畫面只顯示問題代碼、負責流程、影響、去敏判斷資料、業務操作與移除條件；owner domain/version及Preview／Apply／completion predicate只保留在預設收合技術詳情。不得建立generic resolve、改寫owner predicate或以UI狀態移除current issue。

## Implementation
- primary: `ui_react/src/pages/CurrentAnomaliesPage.tsx`

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — 15-code current-only Query、detail、owner action與recheck契約。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/current_anomalies_page.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/current-issue-presentation.md`

## Change triggers
Reconcile when current-only list/detail presentation、owner action descriptor、recheck removal copy或focused test location changes。
