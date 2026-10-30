# Module: notification-rules-presentation

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
統一歡迎訊息與LINE-owned通知內容維護，直接編輯各則文字並預覽；既有規則欄位收在發送設定，依 Global §2.4 一次點擊送出、原因選填，內部仍沿用zero-write Preview與同一候選的Save／Delete及closed結果，不設人工再次確認。卡片說明文字由新通知組裝時讀取目前訊息設定，案件欄位／回覆操作仍由原流程決定。一般畫面不得顯示typed error code、raw backend／provider detail；不得改寫revision、fingerprint、idempotency、已提交通知或工作快照。

「通知與發送」採清單、inline 編輯與手機預覽整合工作台。依 2026-10-22 最新人工裁決，工作台改用明確標示的公版範例，以無業務 DB 能力的 typed sample port 重用原純組裝函式；欄位表列出中文名稱、變數／路徑與帶入值。移除真實案件／月嫂選取與資格限制，不建立投遞任務、操作憑證、異動稽核或 provider effect。既有 record API 保留原 readonly 契約，工作台不再呼叫。

依 2026-10-29 最新人工裁決，所有訊息與卡片欄位均固定 504px。一次顯示一個欄位，切換保留整則草稿；訊息清單每頁 6 則，範例資料預設收合，完整預覽與編輯外框沿單一頁面捲動，多張卡片使用前後切換。手機效果只保留一般手機，無窄螢幕切換模式。

依 2026-10-29 人工裁決，目前目錄全部訊息開放文案維護；卡片摘要、固定標題、說明與按鈕名稱採分欄編輯及同一 revision 儲存，多欄卡片使用單一大欄位切換。動態 owner 欄位及 action 不屬文案。客戶、月嫂及工會人員各有獨立綁定成功設定，直接完成與審核通過按實際身分選用；舊客戶／月嫂成功訊息 ID 分別解析到對應身分設定。只在建立新訊息時讀取設定，不改已提交的 payload；重複綁定沿原 key 查既有工作，避免重新以新文案入列。

2026-10-30 最新人工裁決取代單欄切換：所有可編輯卡片集中顯示標題、504px 自由說明與按鈕名稱，其他標籤／摘要收合；原本沒有說明節點的卡片也可新增段落，支援插入已知的顯示資料變數。正式客戶確認與初步候選月嫂承接各用原獨立 template ID 儲存，保留版本化 CAS 與草稿離頁保護；預覽預設顯示目前編輯的最後確認卡。動態資料及 action 保持原 owner，圖片唯讀。

2026-10-30 正式媒合目錄收斂：正式媒合的卡片僅列「正式媒合－客戶完整推薦確認包」，不再單列月嫂案件資訊卡（一）／（二）與月嫂資料及客戶確認卡；原三項編輯深連結導向完整推薦包。初步候選各項與不同身分／流程的文案仍獨立；既有唯讀單卡 preview、設定與發送操作未退役。

## Implementation

依 2026-10-30 人工裁決，初步候選與正式媒合推薦包的資訊一／二及每週安排改用系統資料表格圖片；預覽支援逐張選擇及放大。這些流程只維護最後確認卡的文字與按鈕名稱，每週安排唯讀。圖片資料與取用由 `table-image-delivery` module 擁有；此處只投影封閉 PNG 預覽節點，不回傳實際發送連結。
- primary: `ui_react/src/components/LineNotificationWorkbench.tsx`
  - `ui_react/src/components/LineCardCopyEditor.tsx` — 整張卡片標題／自由說明／按鈕集中編輯、插入顯示資料及同次儲存，不接收 provider actions。
  - `ui_react/src/components/LineMessageFlow.tsx`、`ui_react/src/components/LineMessageFlow.css` — 同一 LINE 專區的精簡流程導覽；只讀正式目錄與規則，點選步驟才展開訊息，返回時保留步驟並重新查詢狀態。
  - `ui_react/src/adapters/line_configuration/line_message_flow_adapter.ts` — 流程分類引用正式 descriptor／template，解析 current ID 與 enabled／流程控制呈現；不保存文案或業務 gate。
  - `ui_react/src/components/LineMessagePreviewWorkspace.tsx` — 公版欄位值表、abort／generation 與 display-only Flex／carousel renderer。
  - `ui_react/src/api/line_notification_rules/line_message_preview_client.ts` — authenticated closed preview catalog／subjects／preview transport。
  - `subsystems/line/message_preview.py` — LINE-owned typed preview contracts、純渲染協調與移除可執行 action 的 projection。
  - `subsystems/line/message_preview_samples.py` — 明列的公版值、無 DB sample port、卡片範例與帶入欄位對照。
  - `subsystems/line/message_copy.py` — 文案預設、三身分成功設定、原交易內設定讀取，以及僅 display text 的欄位投影／替換；不處理 provider action。
  - `subsystems/line/message_copy_catalog.py` — 明列目前內建訊息的虛擬 genesis、卡片欄位與共用純替換，保留動態區塊及舊工作快照。
  - `infrastructure/mysql/line_message_copy.py` — 借用原 connection 的設定 reader；不另開 writer／commit。
  - shared dependency: `subsystems/line/service_start_day.py::start_day_response_text` — 服務當天群組受理回覆由原 owner 提供純文案；代班／群組日期公版明列指定日期及月嫂欄位。
  - `infrastructure/mysql/line_message_preview_repository.py` — readonly transaction、參數化分頁、owner facts 與既有付款 source 轉接。
  - `api/routes/line_message_preview.py`
  - `api/schemas/line_message_preview.py`
  - `ui_react/src/components/LineNotificationWorkbench.css`
  - `ui_react/src/pages/LineManagementPage.tsx` — 組裝 message_flow 導覽與 push_queue 內容設定，以 message query 定位目前訊息並沿未儲存草稿保護切換；不再掛載獨立歡迎／發送歷程分頁，也不查發送摘要與清單。
  - `ui_react/src/components/LineNotificationRulesMutationPanel.tsx` — scoped settingsOnly 模式保留原規則 mutation。
  - `ui_react/src/components/LineNotificationTemplateEditor.tsx`
  - `ui_react/src/api/line_notification_rules/line_notification_template_client.ts`
  - `api/routes/line_notification_rules.py`
  - `api/schemas/line_notification_rules.py`
  - `ui_react/src/api/line_onboarding/line_onboarding_client.ts`
  - `subsystems/line/message_configuration.py` — notification_description 消費同一版本化文字設定；genesis 沿用既有設定檔。
  - `subsystems/line/staff_leave_customer_coordination.py` — 新請假確認卡片只替換說明文字，不變更日期、對象或 postback。

服務完工滿意度問卷邀請沿現有流程導覽、可編輯文字模板及公版預覽；問卷網址先留空，不提供無網址按鈕，後續可直接加入文字內容。

流程圖顯示簽約與訂金付款可先後交錯、訂金核銷後建群；正式目錄缺規則／模板時呈現「缺少訊息設定」，不提供假的可用預覽。客服導覽說明明確呼叫門檻；「其他問題」舊連結及 API 解析至唯一 `service-menu` 設定，目錄不再列獨立 `service-other`；訂單異動導覽只提供正式 LIFF URI，舊五按鈕文案作唯讀投影，服務流程及收費補助統一導向 AI 客服 LIFF；`service-flow`／`service-payment` 不再列入公版、文案編輯或預設模板，客服流程只保留維護位置說明。資料修改與訂單修改受理通知仍可編輯，歷史設定不刪除。

補列 current 身分／登記模板、客服導覽及受理／結案、候選資訊一／二／每週說明、工會詢問／回覆及完整推薦確認包。卡片重用 `subsystems/scheduling/matching_line_cards.py` 純組裝；公版使用明列範例，訂單資訊欄位沿用 Orders owner `subsystems/orders/order_information.py` 的純格式化；既有 record API 透過 Orders／Matching owner 唯讀 projection。工會逐案詢問與回覆草稿僅預覽，共用卡片的標題、說明與按鈕名稱沿文案設定儲存。D+1～D+3 與未具正式用途的測試模板不列入。零候選固定協調通知已由現行人工協調取代，預覽、有效規則／模板與 bootstrap 均移除，writer 拒絕重新加入。補列訂金、服務群組成功／錯誤、配對回覆、請假回覆、進度與身分入口、完整去敏告警；公版共用原純組裝函式，欄位值明列，record API 對新增純公版項目明示不可用。告警收件者改稱已設定管理員個人對象，不寫死幹部群；群組告警已取消。

經 current source、規格及本機 DB 引用查核的 11 個舊身分／選單模板不再列 standalone 編輯及預覽入口，清單與範圍依規格 29 §3；原設定與歷史保留，若仍有有效 rule 引用則保留 rule-backed 維護。現行受理、身分成功及審核拒絕通知維持原設定。

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — LINE-PREVIEW-01～08、LINE-COPY-01～05、authenticated zero-write preview 與原版本化文案維護。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE notification configuration與delivery邊界。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation/`
- test_root: `ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx`
- contract_test: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_message_preview.py`
- integration_test: `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_inquiry_transaction.py`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/notification-rules-presentation.md`

## Change triggers
Reconcile when unified notification content presentation、welcome composition、configured card copy、Preview／Confirm／Save／Delete gating、closed result/error或focused test location changes。

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_onboarding_api.py`

2026-10-30：目錄與文案編輯清單排除重大客訴／系統異常管理員告警模板及 runtime-system-health。流程圖改為主動查看系統／客服狀態；保留歷史設定，不提供重新啟用 Push。

2026-10-30 最新裁決：18 項給操作人員的 group-bound／group-invitations-queued／group-error-*／group-format-* 改固定 Reply-only，目錄、default copy 與舊編輯／公版入口均移除。管理員告警 rule 文案 Query／PUT 同樣關閉，保留原設定及歷史；客戶／月嫂邀請與有效業務通知不變。
