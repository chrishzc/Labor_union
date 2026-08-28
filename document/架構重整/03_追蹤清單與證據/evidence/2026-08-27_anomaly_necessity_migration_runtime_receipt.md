# Anomaly necessity migration runtime receipt

- Date：2026-08-27
- Work Package：`PROV-20260827-anomaly-necessity-migration-work-package.md`
- Scope：ANM-NM-A dedicated maintenance API 與 server-owned `SCHEDULE-005` first slice
- Database target：`lu_test_task96_anm_nm_a_r11_candidate_20260827`
- Production／`union_db`：未連線、未修改

## Observable contract

- Query 只列出 server policy 准入的 current active alerts，caller 不能傳 disposition、target、
  eligible codes、resolver 或 policy fingerprint。
- Preview 零寫入，`SCHEDULE-005` 固定投影 `retired_false_positive`、target `None`、
  rulebook／release evidence 與 policy fingerprint。
- Apply 使用 persisted enabled administrator，重建 server candidate，鎖定 fresh alert，以單一 outer
  UoW append immutable disposition／receipt／workflow event，再讀證明 predicate inactive。
- same-key same-payload replay 回原 receipt；batch 使用 bounded two-part cursor、per-item savepoint 與
  completion sweep，不把 partial page 當成完成。

## Verification

| Layer | Status | Evidence |
|---|---|---|
| API schema／server-owned policy | `passed` | `tests/test_anomaly_necessity_migration_api.py`；本次增補真 route auth failure 經全域 typed error boundary 轉為八欄 envelope，`8 passed in 2.70s`。 |
| Domain／application／repository | `passed` | necessity catalog、reclassification Domain／workflow／repository 與 API 合併最小回歸；後續無 DB env 重跑為 `26 passed, 3 skipped`，skip 只限明確 MySQL profile。 |
| True MySQL single Q/P/A／replay | `passed` | `tests/test_anomaly_necessity_migration_disposable_mysql_e2e.py::test_single_query_preview_apply_and_replay_are_real_mysql`；正式 reminder builder／`AnomalyApplication.project` 產生測試 alert，非 direct alert insert。 |
| True MySQL bounded batch／replay／completion sweep | `passed` | 同檔 batch scenario；request-only fingerprint、replay 與 zero remaining sweep 通過。 |
| True HTTP Q/P/A／replay + MySQL readback | `passed` | 同檔 FastAPI scenario；三個 MySQL scenarios 合併 `3 passed in 1.70s`。 |
| Runtime producer cutover | `passed` | `SCHEDULE-005` 已從 `infrastructure/mysql/process_reminder_anomaly_source.py` runtime scan 移除；`tests/test_anomaly_necessity_producer_cutover.py` 與相關回歸合併 `23 passed in 3.05s`。 |
| Developer local replacement acceptance | `not_run` | runner preview 因 credential 未由受控環境注入而被安全審查拒絕；未繞過、未執行 replacement／`--switch`。 |

## Database change gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved ANM-NM-A Work Package。 |
| Change inventory | PASS | schema-only three append-only owned objects；no seed／backfill／destructive。 |
| Static release | PASS | release 1009／manifest／descriptor／hash／dependencies。 |
| Descriptor | PASS | fresh 與 preserve candidate `exact`；six immutable triggers。 |
| Read-only plan | PASS | plan fingerprint `2e5fec42f11e9385e5021b2324428e960256caacd4ad4bd435917b11c1fca331`。 |
| Engine verification | PASS | `2026-08-27_anomaly_reclassification_schema_engine_receipt.md`。 |
| Developer acceptance | NOT_RUN | 受控 credential injection 尚未就緒。 |

總結：`DB_CHANGE_NOT_READY`。API／true MySQL runtime 的 pass 不取代 developer local replacement
acceptance，也不表示 ANM-NM-B／C／D 或33-code 人工 remediation 已完成。

## DDH execution record

- API contract 由 Luna High 唯讀 verifier 獨立稽核，主代理為唯一 API integration writer。
- API／MySQL 交界進入共享 composition root 後，工作模式由 E3 verifier 動態調整為 E2
  主代理單寫者，避免 route／auth／entry queue 競寫。
- 本工作鏈的所有已建立子代理均為 `gpt-5.6-luna` / `high`。
- 所有 native `apply_patch` 皆小於 30 秒；未觸發 patch 停止門檻。
