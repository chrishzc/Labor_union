module: react-application-shell
parent_subsystem: application-shell
architecture: ../../../../../../../domains/global/subsystems/application-shell/modules/react-application-shell.md
layout_status: custom_current
integration_root: ui_react/src/tests/challenger_auth_navigation.test.tsx

# Owned higher-boundary verification
- `challenger_auth_navigation.test.tsx` — jointly protects hash navigation、session/auth boundaries、nested ErrorBoundary isolation、custom fallback、retry及closed crash presentation。
