# Phase 5 current runtime test receipt（2026-08-17）

## Existing launcher／monitor baseline

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp/phase5b-readiness -q `
  tests/test_launcher_dry_run.py `
  tests/test_launcher_inventory.py `
  tests/test_local_development_launcher_smoke.py `
  tests/test_private_runtime_operations.py `
  tests/test_online_script.py
```

Result：`49 passed in 3.80s`。

這只證明current API 8000／Streamlit 8501 launcher、smoke與private runtime契約沒有立即回歸；現有
tests沒有React 5173並行process、獨立React HTTP health、三服務owned-process cleanup或三服務monitor
斷言；Phase 5B要求的`tests/test_react_dual_run_infrastructure.py`目前也不存在，不能作為Phase 5B完成證據。

## Existing React route guard baseline

```powershell
cd ui_react
npm test -- src/tests/route_guard.test.tsx
```

Result：`1 file / 7 tests passed`。但stderr仍有多筆React `act(...)` warning；而Phase 5A要求的
`src/tests/react_entrypoint_registry.test.ts`目前不存在。此結果只證明既有hash navigation未立即失敗，
不證明10 Streamlit＋11 React registry、rollback URL或entry governance已完成。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | 唯讀runtime／test readiness驗證 |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無schema/release變更 |
| Descriptor gate | NOT_RUN | 無DB object變更 |
| Read-only plan gate | NOT_RUN | 無migration |
| Engine verification gate | NOT_RUN | 無migration |
| Developer acceptance gate | NOT_RUN | 未操作任何既有DB |

總結：`DB_CHANGE_NOT_READY`。
