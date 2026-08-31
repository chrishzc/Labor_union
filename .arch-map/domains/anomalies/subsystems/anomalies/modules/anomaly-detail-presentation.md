# Module: anomaly-detail-presentation

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
呈現既有異常詳情、處理方式與排班導向；主畫面保留目標日期與已指定服務人員語意，不暴露內部 staff identity。不得改寫 Scheduling 導向或 Anomalies recovery contract。

## Implementation
- primary: `ui_react/src/pages/AnomaliesPage.tsx`

## Contracts
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面業務資訊層級與技術識別邊界。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/anomalies_page_real_data.test.tsx`
- routing: `.arch-map/tests/domains/anomalies/subsystems/anomalies/modules/anomaly-detail-presentation.md`

## Change triggers
Reconcile when anomaly detail presentation、calendar navigation label或focused test location changes。
