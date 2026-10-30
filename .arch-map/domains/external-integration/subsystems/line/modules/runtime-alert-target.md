# Module: runtime-alert-target

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
2026-10-30 管理員個人自動告警退役；保留歷史 target／分類／receipt／audit Query。個人 add／enable／disable／Preview／偏好寫入於開啟 UoW 前拒絕，HTTP 回 typed 410；2026-10-22 群組退役契約維持。通知對象不再構成待辦，管理員只在既有 LIFF 待辦工作台查看系統狀態。

## Implementation
- primary: `subsystems/line/runtime_alert_target_application.py`
- contract: `subsystems/line/runtime_alert_target_contracts.py`
- transport: `api/routes/runtime_health.py`
- retired unmounted presentation: `ui_react/src/pages/line_management/AlertGroupSecurity.tsx`
- presentation: `ui_react/src/pages/LineManagementPage.tsx` — 保留未掛載的 runtimeOnly 歷史呈現；不作正式入口。
- client: `ui_react/src/api/line_runtime_targets/`
- persistence dependency: `infrastructure/mysql/runtime_monitor_repository.py`

- `has_available_admin_target` 唯讀核對 enabled target、enabled Admin 與一致 canonical bound Admin LINE；只作歷史查詢，不產生通知設定待辦。

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — runtime target 與 NAS-LINE-03。
- 分類 GET 唯讀；舊 PATCH 明確回報管理員 Push 退役，不假裝儲存、不新增偏好表。
- 管理員個人 target 舊命令回 `line_admin_push_retired`；群組 reset／Preview／登錄回原 typed retired conflict，均不開 UoW 或寫入。

## Verification
- layout_status: `custom_current`
- layout_basis: 沿用上位 LINE subsystem 已宣告的現行 application 契約測試位置，保留歷史查詢／去敏與退役零寫入 oracle；React 採專案 `ui_react/src/tests/` 的相同 Domain／Subsystem／Module 鏡像位置，由既有 Vitest 執行。
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_runtime_alert_target_application.py`
- test_root: `tests/domains/external-integration/subsystems/line/modules/runtime-alert-target/`
- test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/runtime-alert-target/`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/test_runtime_alert_target_preview_route.py`
- integration_root: `tests/domains/external-integration/subsystems/line/integration/test_runtime_alert_target_application_flow.py`

## Change triggers
告警對象 mutation、固定分類規則、管理畫面或查詢契約改變時核對。
