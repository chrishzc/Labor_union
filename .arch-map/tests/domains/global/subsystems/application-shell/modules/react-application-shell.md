module: react-application-shell
parent_subsystem: application-shell
architecture: ../../../../../../../domains/global/subsystems/application-shell/modules/react-application-shell.md
layout_status: custom_current
integration_root: ui_react/src/tests/challenger_auth_navigation.test.tsx
integration_root: ui_react/src/tests/setup.ts
integration_root: ui_react/src/tests/domains/global/subsystems/application-shell/modules/react-application-shell/

# Owned higher-boundary verification
- `unsaved_changes.test.tsx`、`unsaved_navigation.test.tsx`、`unsaved_contract_form.test.tsx`（上述 integration_root 目錄）— 差異清單、繼續／捨棄／沿原流程儲存、主選單／Hash／登出、抽屜焦點、原生離頁事件，以及預覽成功不能清除未儲存草稿。
- `challenger_auth_navigation.test.tsx` — jointly protects hash navigation、session/auth boundaries、nested ErrorBoundary isolation、custom fallback、retry及closed crash presentation。
- `system_status_entry_cutover.test.tsx` and `system_status_slice.test.ts` — protect the authenticated shell status indicator while the retired standalone route stays absent.
- `react_entrypoint_registry.test.ts` — canonical 客戶名冊／月嫂名冊 navigation and legacy Data Browser redirect.
- `data_browser_entry_cutover.test.tsx`、`data_browser_request_budget.test.tsx` — archived Data Browser read-only compatibility query budget、cursor 與 closed presentation；不再擁有 canonical React entry。
