module: react-application-shell
parent_subsystem: application-shell
architecture: ../../../../../../../domains/global/subsystems/application-shell/modules/react-application-shell.md
layout_status: custom_current
integration_root: ui_react/src/tests/challenger_auth_navigation.test.tsx
integration_root: ui_react/src/tests/domains/global/subsystems/application-shell/modules/react-application-shell/

# Owned higher-boundary verification
- `challenger_auth_navigation.test.tsx` — jointly protects hash navigation、session/auth boundaries、nested ErrorBoundary isolation、custom fallback、retry及closed crash presentation。
- `system_status_entry_cutover.test.tsx` and `system_status_slice.test.ts` — protect the authenticated shell status indicator while the retired standalone route stays absent.
- `react_entrypoint_registry.test.ts` — canonical 客戶名冊／月嫂名冊 navigation and legacy Data Browser redirect.
- `data_browser_entry_cutover.test.tsx`、`data_browser_request_budget.test.tsx` — archived Data Browser read-only compatibility query budget、cursor 與 closed presentation；不再擁有 canonical React entry。
