# Phase 3B-H-R verification receipt

日期：2026-08-22

狀態：`IMPLEMENTATION_PASS / RUNTIME_ACCEPTANCE_PASS / DEVELOPMENT_AUTH_BYPASS`

## Static and focused verification

- `npm test -- --run src/tests/holiday_client.test.ts src/tests/holiday_adapter.test.ts src/tests/scheduling_holiday_flow.test.tsx src/tests/scheduling_no_fake_mutation.test.tsx`
  → 4 files、14 tests PASS。
- `npm run build` → TypeScript與Vite production build PASS；175 modules。只留既有chunk-size warning。
- exact 11 source/test paths strict UTF-8、no BOM、structured header PASS；scoped `git diff --check` PASS。
- 2026-08-22 test-harness follow-up改為等待可見的server scheduling root後再切tab；2 files／4 tests
  PASS且stderr無React `act(...)` warning。

## Runtime

- 既有DB：Chrome GET與zero-write Preview PASS；沒有Apply。
- owned DB `lu_test_phase3bhr_browser_20260822a`：Chrome完成Query→Preview→Apply→receipt→re-query=`observed`。
- readback：holiday 1 row、`scheduling_holiday_maintenance/v2` receipt 1 row；owned DB cleanup後
  `exists_after_cleanup=false`。
- 原8000以development `local_bypass`恢復；`/health`=200、Holiday GET=200／16 rows，Chrome online/query-ready。
- final server-conflict run：同一production UI/client以controlled deterministic key先成功Apply，再送不同payload；
  FastAPI回409、DOM=`conflict`且顯示`idempotency_key_conflict`。readback保留winner row、該key receipt count=1。
- conflict owned DB cleanup後`EXISTS_AFTER_CLEANUP=0`；臨時Vite config已刪除，current 8000／5174恢復。
- 真TOTP依最新人工裁決採`NOT_RUN_ACCEPTED_DEVELOPMENT_BYPASS`，不宣稱執行。

## DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | exact H-R人工核准；owned disposable runtime mutation |
| Change inventory | PASS | schema/seed/backfill=0；destructive僅owned DB cleanup |
| Static release | NOT_RUN | 0 schema change |
| Descriptor | NOT_RUN | 0 schema change |
| Read-only plan | NOT_RUN | 0 schema change |
| Engine verification | PASS | 真實MySQL Apply/readback/cleanup |
| Developer acceptance | PASS | 原8000與既有DB GET恢復 |

固定總結：`DB_CHANGE_NOT_READY`（0 DB schema change）。
