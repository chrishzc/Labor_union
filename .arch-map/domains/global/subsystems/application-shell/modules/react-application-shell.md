# Module: react-application-shell

## Parent
- domain: `global`
- subsystem: `application-shell`

## Responsibility
組成React應用程式的hash navigation、session/auth shell與nested ErrorBoundary。預設crash畫面只提供closed recovery，不顯示render exception message；不得擁有任何Domain business rule、root fact或mutation workflow。

## Implementation
- primary: `ui_react/src/App.tsx`
- primary: `ui_react/src/components/ErrorBoundary.tsx`

## Contracts
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — Global UI shell、recovery與closed error presentation。
- `document/架構重整/01_規格基線/25_Access_Control正式規格.md` — session/auth boundary。

## Verification
- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/challenger_auth_navigation.test.tsx`
- routing: `.arch-map/tests/domains/global/subsystems/application-shell/modules/react-application-shell.md`

## Change triggers
Reconcile when React shell navigation、session/auth composition、ErrorBoundary recovery、closed crash presentation或higher-boundary test location changes。
