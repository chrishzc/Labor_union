# Task 96 RPRE MySQL persistence receipt

- 日期：2026-08-28
- Package：`PKG-RPRE-OWNER-SUCCESSOR`
- Target：`APP_ENV=development`、`lu_test_task96_ldu_candidate_1012_r1`
- Credential class：local configured root；target通過`lu_test_*` allowlist。
- 結果：`PASS`；此 package `completed`，不代表 projection／API／React／Browser完成。

## Fail-before-fix

1. fixture首次被 `scheduling_generations → orders` FK拒絕；補上本 scenario owned order/client，
   未放寬 FK。
2. 首次完整交易揭露 Apply receipt 與 replay receipt 的 superseded roots排序不同；修正 receipt
   在建立時即依root identity canonical排序，未改 digest契約。
3. cleanup verifier指出 immutable Matching/RPRE rows不可DELETE；integration test已移除所有DELETE，
   finally只rollback未提交交易並close connection，已提交scenario明確保留為evidence。

## Positive transaction/readback

- 正向 integration：`1 passed in 0.11s`。
- 保留 scenario：`RPRE-fa7a016c913342f59075`；修正前但完整提交的diagnostic scenario
  `RPRE-6c365682a78e4a4982c2`亦保留，未繞過immutable trigger。
- 兩筆唯讀readback一致：R-02、official service days=0、aggregate/generation `8→9`、event
  `13→14`；prior generation=`cancelled`、successor=`effective`。
- 每筆exact roots：retained=0、superseded=4（ordinal 1..4）、created=1（ordinal 1）；receipt
  digest/count與relation rows重算一致。
- 每筆各一個Matching successor package/event numeric FK、immutable receipt及
  `successor_projection_readback_requested` outbox；package=`candidate_pool_open`、Matching event
  `package_proposed` `8→9`。
- same-key same-payload回同一canonical receipt；沒有第二次replacement mutation。

## Verification

- 主代理相鄰pure regression：`93 passed`。
- cleanup修正後fresh Luna/high read-only verifier：P0=0、P1=0、P2=0；pure focused
  `64 passed`、`py_compile`、strict UTF-8／structured headers及`git diff --check`均PASS。
- verifier未重跑會新增資料的integration test，只以唯讀SQL核對兩筆既有evidence。

## Gate result

| Gate | Status | Evidence |
|---|---|---|
| target/environment/credential class readback | `PASS` | exact development `lu_test_*` target |
| single outer UoW／Apply／replay | `PASS` | integration test＋immutable receipt readback |
| generation／Matching successor／root／outbox exactness | `PASS` | relation與owner readback |
| scoped cleanup／retain policy | `PASS` | immutable evidence保留；test無DELETE |
| projector／API／React／no-auth Browser | `NOT_RUN` | 下一個`PKG-RPRE-PROJECTION-UI-RUNTIME` |
| 另一台實體電腦developer acceptance | `NOT_RUN` | Task96 DB總結仍`DB_CHANGE_NOT_READY` |

本輪無DDL／migration／seed／backfill、未操作`union_db`、provider或Graphify。
