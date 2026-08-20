# WP90／WP95 完成與封存前驗收收據（2026-08-15）

## Scope

WP90 的異常中心維持去敏警示、版本化追蹤與 owner navigation；WP95 以完整 HCM 修正版工作簿在
Case Import owner 邊界重跑 validator，只採納 prior warning 指定欄位的 formal target。原
`historical-workbooks` 整列覆寫 API 固定回傳 `410 Gone`。

## Gate results

| Gate | Status | Evidence |
|---|---|---|
| Scope／owner contract | PASS | WP90、WP95、正式規格 15／17 與 warning registry |
| Static release／descriptor | PASS | `python -m scripts.verify_validation_schema_manifest` → `valid: true` |
| Fresh bootstrap contract | PASS | `tests/test_wp95_hcm_resubmission_schema.py`、`tests/test_schema_assembly.py`、`tests/test_bootstrap_disposable_mysql_schema.py` |
| Preserve-data plan | PASS | `scripts.migrate_preserved_database_additive_schema --check/--dry-run --rehearsal`，source `lu_test_dataset_contract_signing_v4` |
| Preserve-data candidate engine | PASS | source backup → candidate restore → apply → verify；candidate `lu_test_wp95_candidate_20260815`，原 source 未替換 |
| HCM／BeClass disposable MySQL | PASS | 同一 candidate 設為明確 disposable target 後，`tests/test_wp77_disposable_mysql_e2e.py`：9 passed |
| HCM owner Domain／Subsystem | PASS | `tests/test_hcm_resubmission.py`、`tests/test_hcm_resubmission_workflow.py`、`tests/test_hcm_resubmission_workbook.py`：16 passed |
| Warning／API regression | PASS | `tests/test_import_warning_tracking.py`、`tests/test_import_warning_tracking_api.py`、HCM safety tests：36 passed |
| WP90 cross-lane regression | PASS | Finance、Client／Staff BeClass、Historical Orders test selection：100 passed，30 skipped（無需啟動的非本次 test gate） |
| Entry point governance | PASS | `tests/test_entrypoint_review_queue.py`：3 passed；HCM scoped routes active，legacy whole-row routes `retired_410` |

## Safety assertions

- 未操作 `union_db`、未替換 `.env` 指向的 source database，也沒有 source business-row backfill。
- candidate DB 的 HCM correction event、receipt、outbox 皆為 append-only；source review／warning 不被更新。
- HCM owner API 的輸入是完整 workbook；warning center 不接收也不回傳 corrected payload、raw workbook 或候選清單。
- 未登錄 issue／predicate 的 retry 為最多 3 次、至少相隔 1 秒，terminal 狀態保留去敏 dead-letter。

## Residual operation boundary

本收據不代表正式部署或 source DB replacement。未來操作人若要讓本機 source DB 採用 release，必須依
canonical local-update flow 重新取得 source backup、candidate／replacement receipt 與明確授權。
