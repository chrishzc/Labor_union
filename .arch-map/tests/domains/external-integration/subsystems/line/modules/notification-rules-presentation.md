module: notification-rules-presentation
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/notification-rules-presentation.md
layout_status: custom_current
test_root: ui_react/src/tests/line_notification_rules_mutation_panel.test.tsx

# Owned verification
- `line_notification_rules_mutation_panel.test.tsx` — 保護欄位與引用訊息內容編輯、手機預覽、zero-write Preview、人工Confirm、Save／Delete、取消待發工作結果及closed error presentation。
- 同檔統一工作區 oracle 保護歡迎整合、直接內容編輯、共享 revision 回讀、卡片說明文字、未儲存草稿、局部 Query failure 與移除獨立發送入口。
- `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_inquiry_transaction.py` — 請假說明設定進入新卡片，原案件／postback 不變，編輯後不改寫既有工作。
- `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_rule_api.py` — 保護規則引用訊息模板之typed query、版本化內容更新及既有規則 mutation route。
