# Module: notification-rules-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
統一歡迎訊息與LINE-owned通知內容維護，直接編輯各則文字並預覽；既有規則欄位收在發送設定，依 Global §2.4 一次點擊送出、原因選填，內部仍沿用zero-write Preview與同一候選的Save／Delete及closed結果，不設人工再次確認。卡片說明文字由新通知組裝時讀取目前訊息設定，案件欄位／回覆操作仍由原流程決定。一般畫面不得顯示typed error code、raw backend／provider detail；不得改寫revision、fingerprint、idempotency、已提交通知或工作快照。

「通知與發送」採清單、inline 編輯與手機預覽整合工作台。依 2026-10-22 最新人工裁決，工作台改用明確標示的公版範例，以無業務 DB 能力的 typed sample port 重用原純組裝函式；欄位表列出中文名稱、變數／路徑與帶入值。移除真實案件／月嫂選取與資格限制，不建立投遞任務、操作憑證、異動稽核或 provider effect。既有 record API 保留原 readonly 契約，工作台不再呼叫。

文案欄位依 2026-10-22 後續人工裁決預設 504px；手機效果只保留一般手機，無窄螢幕切換模式。

## Implementation
- primary: `ui_react/src/components/LineNotificationWorkbench.tsx`
  - `ui_react/src/components/LineMessagePreviewWorkspace.tsx` — 公版欄位值表、abort／generation 與 display-only Flex／carousel renderer。
  - `ui_react/src/api/line_notification_rules/line_message_preview_client.ts` — authenticated closed preview catalog／subjects／preview transport。
  - `subsystems/line/message_preview.py` — LINE-owned typed preview contracts、純渲染協調與移除可執行 action 的 projection。
  - `subsystems/line/message_preview_samples.py` — 明列的公版值、無 DB sample port、卡片範例與帶入欄位對照。
  - `subsystems/line/message_copy.py` — 正式客服與身分固定文案，供實際通知與唯讀預覽共用。
  - `infrastructure/mysql/line_message_preview_repository.py` — readonly transaction、參數化分頁、owner facts 與既有付款 source 轉接。
  - `api/routes/line_message_preview.py`
  - `api/schemas/line_message_preview.py`
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

補列 current 身分／登記模板、客服導覽及受理／結案、候選資訊一／二／每週說明、工會詢問／回覆及完整推薦確認包。卡片重用 `subsystems/scheduling/matching_line_cards.py` 純組裝；公版使用明列範例，訂單資訊欄位沿用 Orders owner `subsystems/orders/order_information.py` 的純格式化；既有 record API 透過 Orders／Matching owner 唯讀 projection。工會詢問與回覆接受僅預覽草稿，不提供儲存。D+1～D+3 與未具正式用途的測試模板不列入。零候選固定協調通知已由現行人工協調取代，預覽、有效規則／模板與 bootstrap 均移除，writer 拒絕重新加入。補列訂金、服務群組成功／錯誤、配對回覆、請假回覆、進度與身分入口、完整去敏告警；公版共用原純組裝函式，欄位值明列，record API 對新增純公版項目明示不可用。告警收件者改稱已設定管理員個人對象，不寫死幹部群；群組告警已取消。

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — LINE-PREVIEW-01～08、三個 authenticated zero-write entry points 與資料／副作用邊界。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE notification configuration與delivery邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx`
- contract_test: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_message_preview.py`
- integration_test: `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_inquiry_transaction.py`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation.md`

## Change triggers
Reconcile when unified notification content presentation、welcome composition、configured card copy、Preview／Confirm／Save／Delete gating、closed result/error或focused test location changes。
