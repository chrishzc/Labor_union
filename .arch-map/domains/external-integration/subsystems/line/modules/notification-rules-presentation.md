# Module: notification-rules-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned通知規則的既有欄位與其目前引用之文字訊息內容編輯、手機預覽、zero-write規則Preview、人工Confirm、Save／Delete與closed結果。一般畫面不得顯示typed error code、raw backend／provider detail；不得改寫revision、fingerprint、idempotency、規則定義或已提交後取消待發通知與工作之語意。

## Implementation
- primary: `ui_react/src/components/LineNotificationRulesMutationPanel.tsx`
  - `ui_react/src/components/LineNotificationTemplateEditor.tsx`
  - `ui_react/src/api/line_notification_rules/line_notification_template_client.ts`
  - `api/routes/line_notification_rules.py`
  - `api/schemas/line_notification_rules.py`

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE notification configuration與delivery邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx`
- contract_test: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation.md`

## Change triggers
Reconcile when notification-rule presentation、referenced message-template content editing、Preview／Confirm／Save／Delete gating、closed result/error或focused test location changes。
