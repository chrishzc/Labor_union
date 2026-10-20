# Module: runtime-alert-target

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
既有 LINE 告警對象 Query／Preview／Apply、啟停與群組重設、版本檢查、receipt 與 audit。分類沿用固定群組／管理員規則，沒有個別偏好寫入；管理介面保留唯讀分類及訊息預覽。

## Implementation
- primary: `subsystems/line/runtime_alert_target_application.py`
- contract: `subsystems/line/runtime_alert_target_contracts.py`
- transport: `api/routes/runtime_health.py`
- presentation: `ui_react/src/pages/line_management/AlertGroupSecurity.tsx`
- client: `ui_react/src/api/line_runtime_targets/`
- persistence dependency: `infrastructure/mysql/runtime_monitor_repository.py`

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — runtime target 與 NAS-LINE-03。
- 分類 GET 唯讀；舊 PATCH 明確回報固定規則衝突，不假裝儲存、不新增偏好表。
- target 啟停／reset 保留既有 Preview／Apply 與唯一 outer UoW。

## Verification
- layout_status: `custom_current`
- layout_basis: 沿用上位 LINE subsystem 已宣告的現行 application 契約測試位置，保留既有 CAS／singleton／receipt oracle；React 採專案 `ui_react/src/tests/` 的相同 Domain／Subsystem／Module 鏡像位置，由既有 Vitest 執行。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_runtime_alert_target_application.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/runtime-alert-target/`
- test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/runtime-alert-target/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/test_runtime_alert_target_preview_route.py`

## Change triggers
告警對象 mutation、固定分類規則、管理畫面或查詢契約改變時核對。
