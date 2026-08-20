# Verification Receipt — Phase 2D Anomalies Query

**Document Code**: `PROV-20260816-react-admin-phase2d-verification-receipt`  
**Timestamp**: 2026-08-16 fresh independent audit  
**Status**: `BLOCKED`

## Phase 2D-H update

Focused backend現為34 passed，backend enum候選修正已通過；Phase 2D frontend仍為59 passed，build PASS。
disposable MySQL為1 skipped，full frontend仍420 passed／12 failed，lint仍2 warnings；最新Chrome在重啟
正確API後已取得兩query family→DOM。詳細fresh數據以Phase 2D-H evidence目錄為準。

## Fresh command results

| Check | Command | Fresh result |
|---|---|---|
| Backend focused | `.venv\Scripts\python.exe -m pytest tests/test_anomaly_registry_router.py tests/test_import_warning_tracking_api.py --basetemp .pytest_tmp/react-phase2d-audit -q` | PASS: 22 tests; 1 pytest cache permission warning |
| Frontend Phase 2D | `npx vitest run src/tests/anomaly_query_client.test.ts src/tests/anomaly_query_adapter.test.ts src/tests/anomalies_page_real_data.test.tsx src/tests/anomalies_no_fake_mutation.test.tsx` | PASS: 4 files／59 tests |
| Build | `npm run build` | PASS: 73 modules; bundle 567.63 kB; Vite >500 kB warning |
| Lint | `npm run lint` | exit 0, but 2 warnings in `src/components/MasterLayout.tsx` |
| Full frontend suite | `npm test -- --reporter=dot` | FAIL: 3 files／12 tests failed; 420 passed／432 total |
| Real Chrome | existing password→TOTP authenticated session, navigate to Anomalies | Import Warning loaded; Anomalies strict decode failed because live `severity` is `""` |

先前 receipt 宣稱的 58 focused tests、368 full tests、0 lint warnings 與全量 PASS 均已被本次 fresh
結果取代。完整 suite 的 12 failures 主要位於既有 Orders service-date tests，超出 Phase 2D exact write
set；不得在本包內越界修正，但 G6 仍必須判定 BLOCKED。
