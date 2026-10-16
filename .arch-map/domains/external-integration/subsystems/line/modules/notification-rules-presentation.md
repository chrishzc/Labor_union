# Module: notification-rules-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
統一歡迎訊息與LINE-owned通知內容維護，直接編輯各則文字並預覽；既有規則欄位收在發送設定，沿用zero-write Preview、人工Confirm、Save／Delete與closed結果。卡片說明文字由新通知組裝時讀取目前訊息設定，案件欄位／回覆操作仍由原流程決定。一般畫面不得顯示typed error code、raw backend／provider detail；不得改寫revision、fingerprint、idempotency、已提交通知或工作快照。

## Implementation
- primary: `ui_react/src/components/LineNotificationWorkbench.tsx`
  - `ui_react/src/components/LineNotificationWorkbench.css`
  - `ui_react/src/pages/LineManagementPage.tsx` — 只組裝 push_queue 內容設定；不再掛載獨立歡迎／發送歷程分頁，也不查發送摘要與清單。
  - `ui_react/src/components/LineNotificationRulesMutationPanel.tsx` — scoped settingsOnly 模式保留原規則 mutation。
  - `ui_react/src/components/LineNotificationTemplateEditor.tsx`
  - `ui_react/src/api/line_notification_rules/line_notification_template_client.ts`
  - `api/routes/line_notification_rules.py`
  - `api/schemas/line_notification_rules.py`
  - `ui_react/src/api/line_onboarding/line_onboarding_client.ts`
  - `subsystems/line/message_configuration.py` — notification_description 消費同一版本化文字設定；genesis 沿用既有設定檔。
  - `subsystems/line/staff_leave_customer_coordination.py` — 新請假確認卡片只替換說明文字，不變更日期、對象或 postback。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE notification configuration與delivery邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx`
- contract_test: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py`
- integration_test: `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_inquiry_transaction.py`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation.md`

## Change triggers
Reconcile when unified notification content presentation、welcome composition、configured card copy、Preview／Confirm／Save／Delete gating、closed result/error或focused test location changes。
