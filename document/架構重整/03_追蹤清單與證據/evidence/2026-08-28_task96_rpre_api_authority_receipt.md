# Task96 RPRE API authority receipt

- `date`: 2026-08-28
- `status`: `passed`
- `authority`: 人工明確回覆「核准 RPRE API」。
- `scope`: Scheduling-owned service-before-replacement typed Query／Preview／Apply public contract。
- `capability`: 沿用 `orders.historical_review.remediate`，actor/capability 不由 client body 傳入。
- `invariants`: Preview zero-write；Apply fresh lock／單一 outer UoW／exact receipt-readback；
  actual-service 轉 substitution；M3 `rematch_required` 不是 terminal success。
- `exclusions`: schema/migration、provider、production/`union_db`、generic resolve/status editor、
  actual-service writer與新 permission tier。
- `canonical_spec`: `02_決策與退役執行記錄/PROV-20260828-service-before-replacement-successor-contract-spec-gap.md` §8.5。
- `task_pack`: `02_決策與退役執行記錄/PROV-20260828-service-before-replacement-successor-work-packages.md`。
- `implementation_status`: `not_run`；本 receipt 只證明 Authority，不冒充 source/runtime 驗收。
