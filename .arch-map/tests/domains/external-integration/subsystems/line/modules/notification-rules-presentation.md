module: notification-rules-presentation
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/notification-rules-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx

# Owned verification
- `tests/domains/external-integration/subsystems/line/subsystems/test_line_message_preview.py` — 真實 typed facts、缺少對象／資料、純卡片組裝、closed action projection、授權、唯讀交易與 main mutation audit 零寫入。
- 同檔保護正式來源清單、排除退役／測試模板、現行歡迎／登記／綁定文案、客服訊息、工會草稿卡與完整確認包使用 owner 唯讀 projection，不建立下載憑證。
- 統一工作區 oracle 保護公版直接預覽、不呼叫真實對象搜尋、欄位與範例值表、僅試改不儲存、closed 查詢錯誤與舊預覽晚到不覆蓋新文案。
- `line_notification_rules_mutation_panel.test.tsx` — 保護欄位與引用訊息內容編輯、手機預覽、一次點擊後內部zero-write Preview與同一候選的Save／Delete、選填原因、取消待發工作結果及closed error presentation；不要求人工再次確認。
- 同檔統一工作區 oracle 保護歡迎整合、直接內容編輯、共享 revision 回讀、卡片說明文字、未儲存草稿、局部 Query failure 與移除獨立發送入口。
- 同檔流程圖 oracle 保護精簡步驟、延後展開、多則訊息精確定位、current 規則狀態與 shadow rule 不冒充停用、訊息 query 重新載入、未儲存草稿離頁保護、失效目標與 Query 失敗不假裝成功；所有設定變更與外送操作保持零呼叫。
- `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_inquiry_transaction.py` — 請假說明設定進入新卡片，原案件／postback 不變，編輯後不改寫既有工作。
- `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py` — 保護規則引用訊息模板之typed query、版本化內容更新及既有規則 mutation route。

- 同一 preview test root 保護公版無 real-reader 能力、付款／請假與所有內建卡片不受資格限制、文字僅列實際使用變數，及 sample API 不接受未知來源值。

test_root: tests/domains/external-integration/subsystems/line/subsystems/test_line_onboarding_api.py
