# Subsystem: application-shell

## Parent
- domain: `global`

## Responsibility
組成React application navigation、session/auth boundary與global error recovery，不承擔Domain mutation。

## Modules
- `react-application-shell` — React shell與closed ErrorBoundary；path: `modules/react-application-shell.md`
- `data-import-composition` — 跨 Domain 資料匯入頁的 typed preview／apply composition；path: `modules/data-import-composition.md`
