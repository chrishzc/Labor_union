# GOVSUB-006 政府溢撥異常 code-only remediation receipt

- Result：`passed`（code-only）
- Full remediation：`not_completed`
- Runtime：`not_run`
- DB blocker：`BLOCKED_SCOPE`

## Delivered

- 多個active、future、缺失或空白return recipient一律fail closed；Query與fresh Apply共用BusinessClock eligibility。
- outbox lineage綁定source transaction對應projection，不取unrelated latest event。
- React只接受完整GOVSUB-006 action/recovery context與typed binding kind/value。
- timeout／unknown不再第二次Apply；stale會fresh owner Query、清除舊Preview並要求重新Preview。
- receipt不等於解除；只有owner root合法離開`pending_review`、原GOVSUB-006 exact fingerprint `predicate_active=false`、active list refresh成功且原fingerprint absent才completed。

## Verification

| Gate | 結果 | Evidence |
|---|---|---|
| Python integration | `passed` | parent final `42 passed`；E3 round2 `71 passed`。 |
| React focused | `passed` | parent final `25 passed`；E3 round2 `15 passed`。 |
| Build/diff/UTF-8 | `passed` | production build、`git diff --check`、strict UTF-8 PASS。 |
| E3 | `passed` | round1四項P1均回修；round2 P0/P1/P2無finding。 |
| Runtime/Browser | `not_run` | Docker/FastAPI/DB未啟動。 |

## DB gate

本包沒有schema／seed／backfill／destructive變更，DB summary為`NO_DB_CHANGE`。但現有`government_subsidy_overpayment_offsets(overpayment_identity, claim_item_id)` unique constraint可能使同target第二次partial offset stranded；修正它需要新的approved DB Work Package、release chain、descriptor、fresh與preserve-data gates，現況固定`DB_CHANGE_NOT_READY`。

## Remaining truth

此receipt只完成GOVSUB-006 code-only安全閉環，不代表partial-offset路徑或真MySQL/API/Browser已完成，也不得宣稱42碼全部完成。
