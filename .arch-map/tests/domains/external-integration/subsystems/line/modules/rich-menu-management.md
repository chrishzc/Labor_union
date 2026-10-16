module: rich-menu-management
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/rich-menu-management.md
layout_status: custom_current
test_root: tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_draft.py
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
- LIFF Flex design preview covers redacted asset rendering and current formal-data connection status.
- Management page integration covers role selection, adjacent save/publication actions, removal of history navigation and list queries, state-driven controls and background/name persistence after save and remount.
