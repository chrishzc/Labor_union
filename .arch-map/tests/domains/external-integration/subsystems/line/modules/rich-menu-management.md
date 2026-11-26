module: rich-menu-management
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/rich-menu-management.md
layout_status: custom_current
test_root: tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_backup.py
test_root: tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_draft.py
test_root: tests/domains/external-integration/subsystems/line/infrastructure/test_line_rich_menu_provider_saga.py
test_root: ui_react/src/tests/line_rich_menu_draft_action_editor.test.tsx
test_root: ui_react/src/tests/line_rich_menu_draft_appearance_editor.test.tsx
test_root: ui_react/src/tests/line_rich_menu_publication_actions.test.tsx
test_root: ui_react/src/tests/line_rich_menu_query_flow.test.tsx
test_root: ui_react/src/tests/line_flex_design_preview.test.tsx
integration_root: ui_react/src/tests/line_management_page_real_data.test.tsx
test_root: ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_rich_menu_local_preview.test.tsx

# Owned verification
- Draft action and appearance editors cover controlled shared fields, a single button-name editor, processing and published-to-next-draft behavior. Appearance tests also cover the shared save confirmation and fresh readback mismatch.
- Publication actions cover Preview, explicit confirmation, queue receipt and retry.
- LIFF form preview covers form-only navigation, search/audience filters, legacy card links, readonly previews and absence of card catalog queries; standalone Flex diagrams retain redacted rendering checks.
- Management page integration covers role selection, adjacent save/publication actions, removal of history navigation and list queries, state-driven controls and background/name persistence after save and remount.

## 換版與發布讀回驗收

以下是需補的案例，尚未執行。優先擴充現有的前端查詢流程、草稿契約及 provider saga 測試；用替身 LINE 回應跑 CI，不接正式 LINE。

- **同一工作重查。** 發布已受理，自動查詢停止或發生暫時錯誤。按重新整理或重開該版後，讀回原發布編號；分別驗已發布及正式失敗的回應。不得再發出發布寫入；查詢失敗不得顯示 LINE 已拒絕。
- **分頁動作。** 合法的切換按鈕經草稿與預檢後輸出 `richmenuswitch`、`richMenuAliasId`、`data`。不存在或不允許的目標在送出前被拒絕；既有普通按鈕仍可發布。
- **原別名換版。** LINE 已有上一版別名且新版已上圖才允許更新並讀回；不存在走建立，已是新版則不重複寫，指向第三個版本則不覆蓋。模擬更新後回應遺失，重試先讀回，不能重新建立新版，也不刪舊版。別名步驟未確認時不標正式成功。
- **個人生效。** 新的預設選單與使用者仍綁舊版可同時成立。以個人選單讀回確認切換，不以預設或 enqueue 回執推定。真實聊天畫面需另外在核准的隔離帳號驗。
