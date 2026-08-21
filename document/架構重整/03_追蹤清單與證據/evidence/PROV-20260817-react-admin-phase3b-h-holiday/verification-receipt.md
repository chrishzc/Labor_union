# Phase 3B-H Holiday final verification receipt

- 日期：2026-08-21
- status：`completed-backend`
- scope：Holiday typed Query／Preview／Apply／Receipt、single outer UoW、cache observation；React不在本包。

## Final-state evidence

| Claim | Evidence | Status |
|---|---|---|
| closed public contract／Global errors／transaction boundary | `pytest ... test_holiday_router.py test_holiday_public_contract.py test_admin_command_workflows.py test_holiday_query_cache_boundary.py test_g15_cache_boundary_contract.py test_leave_substitution_public_contract.py test_leave_substitution_router.py`：29 passed | PASS |
| 真實MySQL Preview／rollback／commit／replay | 唯一`lu_test_phase3bh_20260821a`：1 passed in 29.75s；cleanup readback `DISPOSABLE_DB_REMAINING=0` | PASS |
| exact GET OpenAPI／HTTP screening | api-test-workflow run `20260821T153250Z_cf626e67`：expected/observed 1 operation、2 successful scenarios discarded、0 failed、0 unique | PASS |
| current 8000 runtime | 舊project uvicorn PID 19960正常停止失敗；重新核對完整命令列後只force-stop該PID，啟動PID 28372；health 200、ranged Holiday 200、source `mysql:holidays/v1`、version 64 chars、rows 2、單一non-empty correlation header | PASS |
| workflow context reduction | raw 16,418 bytes（heuristic 4,105 tokens）、filtered 0 bytes；estimated reduction 100%；非Codex帳單token | PASS |
| existing DB safety | current configured DB未mutation；API workflow只有GET；disposable database由test owned並已刪除 | PASS |

第一次HTTP screening曾發現OpenAPI 422仍宣告legacy validation schema；已補
`GlobalTypedErrorResponseView` responses並加入OpenAPI regression，最終run為0 failure。raw NDJSON由workflow
在finally刪除，未保留大型重複log。

## DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope | PASS | exact approved runtime WP |
| Change inventory | PASS | schema/seed/backfill/destructive皆0；runtime只寫owned holiday＋receipt |
| Static release | NOT_RUN | 無schema release |
| Descriptor | NOT_RUN | 無owned schema object變更 |
| Read-only plan | NOT_RUN | 無migration |
| Engine verification | PASS | disposable MySQL final-state evidence如上 |
| Developer acceptance | NOT_RUN | 未操作既有DB |

DB結論：`DB_CHANGE_NOT_READY`（本包不提出DB/schema change completion claim）。
