# Module: rich-menu-management

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供已認證管理員的 Rich Menu typed draft 查詢、外觀／action 編輯、Preview／Apply readback 與 publication Preview／Confirm／Queue presentation。`processing` revision 保持唯讀；`published` configuration 可建立下一個 draft revision，既有 publication snapshot 不被覆寫。

## Implementation
- primary:
  - `subsystems/line/configuration_application.py`
  - `subsystems/line/configuration_contracts.py`
  - `domains/line/rich_menu_draft.py`
  - `subsystems/line/rich_menu_publication_workflow.py`
  - `api/routes/line_rich_menus.py`
  - `ui_react/src/components/LineRichMenuDraftAppearanceEditor.tsx`
  - `ui_react/src/components/LineRichMenuDraftActionEditor.tsx`
  - `ui_react/src/components/LineRichMenuDraftSaveActions.tsx` — shared draft Preview/Confirm/Apply with fresh Query readback.
  - `ui_react/src/pages/line_management/LineRichMenuWorkspace.css`
  - `ui_react/src/components/LineRichMenuPublicationActions.tsx`
  - `ui_react/src/pages/LineManagementPage.tsx`
  - `ui_react/src/pages/line_management/LiffCardStudio.tsx`
  - `ui_react/src/pages/line_management/LiffCardStudio.css` — 用途分組與兩欄預覽，保留既有正式／安全展示入口及案件專屬連結限制。
  - `ui_react/src/components/LineFlexDesignPreview.tsx` — 本頁採用精簡狀態呈現；通知設定頁保留完整狀態摘要。
  - `config/line_menu.json` — bootstrap definition only; published/current drafts remain versioned persistence.

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` §3.5
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6
- `document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md` §3

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_rich_menu_draft.py`
- test_root: `ui_react/src/tests/line_rich_menu_draft_action_editor.test.tsx`
- test_root: `ui_react/src/tests/line_rich_menu_draft_appearance_editor.test.tsx`
- test_root: `ui_react/src/tests/line_rich_menu_publication_actions.test.tsx`
- test_root: `ui_react/src/tests/line_rich_menu_query_flow.test.tsx`
- test_root: `ui_react/src/tests/line_flex_design_preview.test.tsx`
- integration_root: `ui_react/src/tests/line_management_page_real_data.test.tsx`
- test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_rich_menu_local_preview.test.tsx`
- routing: `.arch-map/tests/domains/external-integration/subsystems/line/modules/rich-menu-management.md`

## Change triggers
Reconcile when role menu draft editability, publication state gating, Preview／Apply／Queue flow, management presentation or focused verification paths change.

Management presentation opens the editor directly, with 發布 beside the common draft save action and explicit confirmation in a Drawer; publication history has no UI entry or list query. Appearance and button fields share one in-memory definition; button names are edited only in the button editor. The common save action verifies a fresh server Query after Apply. Queued publication status and retryable failures remain in the publication Drawer.
