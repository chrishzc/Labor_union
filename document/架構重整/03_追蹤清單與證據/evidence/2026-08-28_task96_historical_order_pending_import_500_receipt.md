# Task 96 Historical Orders 待補件匯入 500 修正 receipt

- `date`: 2026-08-28
- `package`: `PKG-HISTORICAL-ORDER-PENDING-LIFECYCLE-EVENT`
- `result`: final candidate功能與fresh驗證`passed`；preserve-data與另一台主機升級仍未完成，DB總結`DB_CHANGE_NOT_READY`。

## Root cause and correction

- 真實匯入命中`待補件`Order時，repository如實寫入immutable event的`before_status=待補件`；舊
  `chk_order_lifecycle_state_event_before_status`只有五種狀態，MySQL 3819使row UoW rollback並冒成500。
- 新1013 additive successor只把`待補件`加入before status；after status維持原五種，禁止把待補件
  放寬成結果狀態。未升級環境改回typed `503 historical_order_database_upgrade_required`。

## Verification

- Static／migration／historical focused：final主lane `147 passed, 10 skipped`；manifest verification、compile、
  `git diff --check`均passed。
- fresh Luna/high final verifier：42 focused＋118 migration＋40 historical，P0／P1／P2=0，判定可scoped commit/push。
- Fresh MySQL bootstrap：本次scoped candidate validation v17、140 parts，passed。
- 真MySQL workflow：三筆`待補件`Order匯入`0／1／2`，Apply與same-key replay passed。
- no-auth API 8000：Preview／Apply／replay counts均為取消1／完成1／洽談1／invalid0；Apply adopted 3。
- DB readback：三筆event皆`before_status=待補件`，after各為洽談中／訂單取消／訂單完成；row receipts 3、
  workbook receipt 1，replay未增加。

## DB gate table

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | confirmed spec＋approved package；只操作唯一`lu_test_*` fixtures |
| Change inventory | PASS | schema-only before-check replacement；seed/backfill/destructive均none |
| Static release | PASS | 1013 manifest/hash、140-part assembly、validation v17、generated release一致 |
| Descriptor | PASS | predecessor／exact successor／drift可機械區分；after check未放寬 |
| Read-only plan | BLOCKED | runner需安全credential injection；平台拒絕明文暫存檔與command argument |
| Engine verification | PASS | fresh bootstrap＋真MySQL workflow／API／replay／readback |
| Developer acceptance | NOT_RUN | 另一台主機尚未以`.env` configured DB升級與重驗 |

必要DB gate仍有`BLOCKED／NOT_RUN`，因此總結固定為`DB_CHANGE_NOT_READY`。另一台主機升級後應使用原
idempotency key resume，不另建新key；原3819失敗row由outer UoW rollback。
