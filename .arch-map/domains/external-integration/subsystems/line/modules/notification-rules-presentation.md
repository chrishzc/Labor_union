# Module: notification-rules-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
呈現LINE-owned通知規則的既有欄位編輯、zero-write Preview、人工Confirm、Save／Delete與closed結果。一般畫面不得顯示typed error code、raw backend／provider detail；不得改寫revision、fingerprint、idempotency、規則定義或已提交後取消待發通知與工作之語意。

## Implementation
- primary: `ui_react/src/components/LineNotificationRulesMutationPanel.tsx`

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE notification configuration與delivery邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation.md`

## Change triggers
Reconcile when notification-rule presentation、Preview／Confirm／Save／Delete gating、closed result/error或focused test location changes。
