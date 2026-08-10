# 201 筆 legacy_active Finding Disposition 清單

- 原始 snapshot：201 findings
- 原始產生時間：2026-08-03
- 語意審查時間：2026-08-03
- 狀態：`not-authorized-for-bulk-removal`
- 盤點授權：`inventory-v2-classification-authorized`

`legacy_active` 是依 path pattern 產生的 discovery classification，不代表該 finding
已被證明可刪除。下方原始 `status` 欄只保存起始提案，不是執行授權；任何模型不得
依該欄直接刪檔、刪函式、改成 `410` 或移除 SQL。
本次核准允許 fresh scan／blocked reconciliation、逐列語意分類、source digest 與
versioned evidence artifact；不會自動把任何 finding 升為 `approved_to_remove`。

## 正確性結論

1. owner 筆數加總為 201，算術正確；但 owner／legacy status 只依 path pattern，
   沒有判斷 symbol、SQL 語意、caller 或是否為正式新架構 writer。
2. 201 findings 包含 50 個 `COMMIT` transaction-boundary findings、14 個
   `DYNAMIC` findings，以及真正的 INSERT／UPDATE／DELETE writer；不能把它們視為
   201 個可移除 writer。
3. 14 個 `DYNAMIC` 中，已辨認 12 個 read／locking-read false positives；
   另 2 個是 Data Browser audit dynamic INSERT，稽核能力必須保留並移入正式
   `SecurityAuditRepository`。
4. 至少 Orders lifecycle、Scheduling waiting locks／matching、Finance Import
   ingestion、Access authentication/session、Anomalies projector 等正式能力被 path rule
   誤標為 legacy；它們只能等價遷移到 typed port／adapter，不能直接刪除。
5. 原清單第 1、2 筆已與 live symbol 漂移，不是 current finding。
6. current checker 尚不能完成 fresh count／fingerprint：共享 dirty
   `services/anomaly_alert_detection.py` 在語意審查時存在 SyntaxError。修復並 fresh-run
   inventory 前，`201` 只能稱為歷史 snapshot。

## Disposition 類型

| disposition | 意義 | 是否可直接刪除 |
|---|---|---|
| `canonical_target` | 已是正式 root／event／projector writer | 否；重分類或搬至 infrastructure adapter |
| `migrate_writer` | 能力仍需要，但 SQL／commit owner 不符合目標架構 | 否；先等價遷移並驗證 |
| `retire_candidate` | 已有正式替代能力的 legacy writer | 否；仍須證明所有 caller 已退出 |
| `allowed_transaction_boundary` | 合法 outer UoW commit | 否 |
| `allowed_read` | SELECT／FOR UPDATE 被 scanner 誤判為 dynamic writer | 否 |
| `stale_finding` | path／symbol／operation 已與 live source 漂移 | 否；fresh inventory 後移除 snapshot row |
| `approved_to_remove` | caller=0、正式替代已驗證、資料保留與回歸 Gate 全通過 | 是；本清單目前為 0 |

## 依 owner 統計（path-rule snapshot，不是移除工作量）

| owner | 筆數 |
| --- | ---: |
| anomalies | 18 |
| api_adapter | 3 |
| client_finance | 15 |
| finance_import | 21 |
| orders | 27 |
| payroll | 1 |
| platform_admin | 46 |
| scheduling | 66 |
| staff_payables | 4 |

## Owner／功能群裁決

| Owner／功能群 | 起始 findings | 正式 disposition | 移除前置條件 |
|---|---:|---|---|
| Orders | 27 | lifecycle persistence／control events／outbox projector 為 `canonical_target`；assignment synchronization 與舊 transaction boundary 為 `retire_candidate` | 先證明 service-to-service caller 已退出；不得刪 lifecycle root／event writer |
| Assignments／Scheduling | 66 | waiting locks、Matching Plan、leave／substitution 語意必須保留；direct SQL 為 `migrate_writer`，部分舊 route 才是 `retire_candidate` | 先遷入 Scheduling repository／UoW；lock conversion 仍依賴 generation 時不得先刪 |
| Payroll | 1 | `_q` 為 `allowed_read` | 修 scanner／重分類，不需移除業務能力 |
| Client Finance | 15 | legacy payment／subsidy writers 為 `retire_candidate` | 先移除 retired Finance Import dispatch chain，證明正式 ledger caller 唯一 |
| Staff Payables | 4 | legacy transfer／monthly-settlement writer 為 `retire_candidate` | 先關閉舊 dispatch；歷史資料唯讀保留，不刪 table／rows |
| Finance Import | 21 | ingestion／staging／anomaly consumer 為 `canonical_target` 或 `migrate_writer`；舊 diagnostic／reprocess 另行退休 | 正式 ingestion 不得刪；reprocess 新契約與 owning-Domain composite 完成後才能退舊 SQL |
| Anomalies | 18 | canonical projector／workflow 為 `canonical_target` 或 `migrate_writer`；legacy alert store 分流退休 | 先遷 UI caller、worker checkpoint 並驗證 replay、CAS、active→inactive |
| API Adapter | 3 | route-owned commit 為 `migrate_writer` | commit 移至 typed application command；route 只映射 input／output |
| Platform Admin | 46 | auth／session／audit 為 `migrate_writer`；generic Data Browser／`db_service` mutation 逐函式裁決 | 先完成 Access capability、session revoke、同交易 audit；不得整檔刪 `db_service` |
| Read false positives | 12 | `allowed_read` | scanner 能辨認 function-local SQL／SQL parameter 後移出 writer 分母 |
| Dynamic audit mutations | 2 | `migrate_writer` | 搬至 `SecurityAuditRepository`，不得刪除稽核 |
| Stale rows | 2 | `stale_finding` | fresh inventory 取代原 snapshot |

## 可交接移除 Gate

其他模型只能處理已切成獨立 Work Package 的 `retire_candidate`，且每個 package 必須具備：

1. exact path＋symbol＋operation＋table，不使用模糊 path glob；
2. owning Domain 與正式 replacement port／adapter；
3. branch、HEAD、source digest、dirty overlap 與本包 exact writable paths；
4. machine-readable caller manifest，覆蓋 FastAPI router inclusion、Streamlit client、
   worker registry、CLI／batch、startup scripts、config-driven symbol、dynamic import
   與 service-to-service caller；
5. caller=0 或 caller 全部改接 typed replacement 的證據；單獨 `rg` 無引用不充分；
6. replacement old／new read comparison 或 shadow evidence；
7. 同一 outer UoW owner且無 hidden commit；
8. replay、stale、conflict、partial failure、row count、ledger balance、event ordering、
   projection rebuild、typed API error 與 UI acceptance；
9. root fact、transaction、idempotency、outbox、audit 與 rollback 等價證據；
10. schema／歷史資料保留策略；退出 code 不代表 DROP table 或刪資料；
11. 測試只使用 disposable DB／credential；禁止正式 `.env`、`union_db`、LINE、
    外部平台或 production credentials；
12. code rollback、config switch、migration recovery、worker replay 與人工 recovery入口；
13. Module、Subsystem、Domain、Global 分層驗收；
14. fresh writer inventory 與 before／after fingerprint；
15. 人工確認該 Work Package 的 write scope 與 external side effects。

### Disposition 狀態機

```text
discovered
  → dispositioned
    ├→ canonical_target
    ├→ allowed_read
    ├→ allowed_transaction_boundary
    ├→ migrate_writer → replacement_verified → migrated → post_migration_verified
    └→ retire_candidate
         → replacement_verified
         → caller_zero
         → awaiting_human_approval
         → approved_to_remove
         → removed
         → post_removal_verified

任一步驟證據失效 → blocked
removed 後驗證失敗 → recovery_required → recovered | escalated
```

`approved_to_remove` 必須綁定 approver、exact identities、source digests、replacement
receipt、caller manifest digest、allowed write scope、granted time 與 expiry。批准過期、
source 漂移或 Work Package 擴張時回 `retire_candidate` 重新驗證。

### Inventory v2 每列必要欄位

- exact finding identity 與 source digest；
- writer kind：SQL mutation／transaction boundary／read false-positive；
- effective disposition 與 decision owner；
- owning Domain／Global Subsystem；
- replacement path／port／adapter 與 verification receipt；
- caller manifest digest；
- dirty overlap result；
- current state、blocker、approval receipt 與 post-change receipt。

COMMIT 與 concrete SQL mutation 必須分表／分欄統計，不能重複當成兩個待移除 writer。

## 原始可追蹤明細（discovery snapshot，非移除名單）

| # | path | symbol | method | operation | table | owner | exit_slice | status | 筆記 |
| --: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | services/anomaly_alert_detection.py | _scan_presence_check | execute | DYNAMIC | unknown | anomalies | slice-4 | 410 |  |
| 2 | services/architecture_outbox_worker.py | _project_scheduling_page | commit | COMMIT | - | anomalies | slice-4 | 410 |  |
| 3 | services/finance_alert_detection.py | create_or_get_finance_alert | execute | INSERT | finance_alert_events | anomalies | slice-4 | 410 |  |
| 4 | services/finance_alert_detection.py | create_or_get_finance_alert | execute | INSERT | finance_alerts | anomalies | slice-4 | 410 |  |
| 5 | services/finance_alert_events.py | append_finance_alert_event | execute | INSERT | finance_alert_events | anomalies | slice-4 | 需移除 |  |
| 6 | services/finance_alert_workflow.py | claim_finance_alert | execute | UPDATE | finance_alerts | anomalies | slice-4 | 需移除 |  |
| 7 | services/finance_alert_workflow.py | resolve_finance_alert | execute | UPDATE | finance_alerts | anomalies | slice-4 | 需移除 |  |
| 8 | services/staff_payables_anomaly_source.py | consume_staff_payables_anomaly_sources | commit | COMMIT | - | anomalies | slice-4 | 需移除 |  |
| 9 | services/system_alert_service.py | claim_system_alert | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 10 | services/system_alert_service.py | delete_system_alert | execute | DELETE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 11 | services/system_alert_service.py | resolve_absent_alerts | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 12 | services/system_alert_service.py | resolve_absent_current_state_alerts | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 13 | services/system_alert_service.py | resolve_current_state_alert | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 14 | services/system_alert_service.py | resolve_if_exists | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 15 | services/system_alert_service.py | resolve_system_alert | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 16 | services/system_alert_service.py | upsert_system_alert | execute | INSERT | system_alerts | anomalies | slice-4 | 需移除 |  |
| 17 | services/system_alert_service.py | upsert_system_alert | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 18 | services/system_alert_service.py | upsert_system_alert | execute | UPDATE | system_alerts | anomalies | slice-4 | 需移除 |  |
| 19 | api/routes/finance_alerts.py | _run_action | commit | COMMIT | - | api_adapter | slice-5 | 需移除 |  |
| 20 | api/routes/system_alerts.py | _run_action | commit | COMMIT | - | api_adapter | slice-5 | 需移除 |  |
| 21 | api/routes/system_alerts.py | scan_alerts | commit | COMMIT | - | api_adapter | slice-5 | 需移除 |  |
| 22 | services/client_payment_snapshots.py | create_client_payment_snapshot | execute | INSERT | client_payments | client_finance | slice-3 | 需移除 |  |
| 23 | services/client_payment_writer.py | _clear_subsidy_return_review | execute | UPDATE | client_payments | client_finance | slice-3 | 需移除 |  |
| 24 | services/client_payment_writer.py | _persist_subsidy_return_review | execute | UPDATE | client_payments | client_finance | slice-3 | 需移除 |  |
| 25 | services/client_payment_writer.py | record_client_payment_transaction_with_cursor | execute | UPDATE | client_payments | client_finance | slice-3 | 需移除 |  |
| 26 | services/client_payment_writer.py | record_client_payment_transaction_with_cursor | execute | INSERT | client_payment_transactions | client_finance | slice-3 | 需移除 |  |
| 27 | services/client_receipt_reconciliation.py | reconcile_client_receipt | execute | UPDATE | finance_import_rows | client_finance | slice-3 | 需移除 |  |
| 28 | services/client_subsidy_return_obligations.py | activate_subsidy_return_obligation | execute | UPDATE | client_payments | client_finance | slice-3 | 需移除 |  |
| 29 | services/client_subsidy_return_transactions.py | record_client_subsidy_return | execute | UPDATE | client_payments | client_finance | slice-3 | 需移除 |  |
| 30 | services/client_subsidy_return_transactions.py | record_client_subsidy_return | execute | INSERT | client_payment_transactions | client_finance | slice-3 | 需移除 |  |
| 31 | services/client_subsidy_return_transactions.py | record_client_subsidy_return | execute | UPDATE | finance_import_rows | client_finance | slice-3 | 需移除 |  |
| 32 | services/government_subsidy_reconciliation.py | reconcile_government_subsidy | execute | UPDATE | subsidy_claim_batches | client_finance | slice-3 | 需移除 |  |
| 33 | services/government_subsidy_reconciliation.py | reconcile_government_subsidy | execute | UPDATE | finance_import_rows | client_finance | slice-3 | 需移除 |  |
| 34 | services/government_subsidy_reconciliation.py | reconcile_government_subsidy | execute | INSERT | government_subsidy_allocations | client_finance | slice-3 | 需移除 |  |
| 35 | services/government_subsidy_reconciliation.py | reconcile_government_subsidy | execute | UPDATE | subsidy_claim_batch_items | client_finance | slice-3 | 需移除 |  |
| 36 | services/government_subsidy_reconciliation.py | reconcile_government_subsidy | execute | INSERT | government_subsidy_transactions | client_finance | slice-3 | 需移除 |  |
| 37 | services/finance_import_anomaly_consumer.py | _consume_next | commit | COMMIT | - | finance_import | slice-3 | 需移除 |  |
| 38 | services/finance_import_anomaly_consumer.py | _mark_delivered | execute | UPDATE | finance_import_outbox | finance_import | slice-3 | 需移除 |  |
| 39 | services/finance_import_anomaly_consumer.py | _mark_failed | commit | COMMIT | - | finance_import | slice-3 | 需移除 |  |
| 40 | services/finance_import_anomaly_consumer.py | _mark_failed | execute | UPDATE | finance_import_outbox | finance_import | slice-3 | 需移除 |  |
| 41 | services/finance_import_application.py | import_finance_workbook | commit | COMMIT | - | finance_import | slice-3 | 需移除 |  |
| 42 | services/finance_import_application.py | import_finance_workbook | execute | UPDATE | finance_import_batches | finance_import | slice-3 | 需移除 |  |
| 43 | services/finance_import_ingestion.py | _append_classification_outbox | execute | INSERT | finance_import_outbox | finance_import | slice-3 | 需移除 |  |
| 44 | services/finance_import_ingestion.py | _complete_batch | execute | UPDATE | finance_import_batches | finance_import | slice-3 | 需移除 |  |
| 45 | services/finance_import_ingestion.py | _insert_batch_contract | execute | INSERT | finance_import_batch_contracts | finance_import | slice-3 | 需移除 |  |
| 46 | services/finance_import_ingestion.py | _insert_initial_classification | execute | INSERT | finance_import_classification_events | finance_import | slice-3 | 需移除 |  |
| 47 | services/finance_import_ingestion.py | _save_receipt | execute | INSERT | finance_import_ingestion_receipts | finance_import | slice-3 | 需移除 |  |
| 48 | services/finance_import_ingestion.py | ingest_finance_workbook | commit | COMMIT | - | finance_import | slice-3 | 需移除 |  |
| 49 | services/finance_import_reprocessing.py | reprocess_finance_import_batch | commit | COMMIT | - | finance_import | slice-3 | 需移除 |  |
| 50 | services/finance_import_reprocessing.py | reprocess_finance_import_batch | execute | INSERT | finance_import_reclassification_events | finance_import | slice-3 | 需移除 |  |
| 51 | services/finance_import_reprocessing.py | reprocess_finance_import_batch | execute | UPDATE | finance_import_rows | finance_import | slice-3 | 需移除 |  |
| 52 | services/finance_import_reprocessing.py | reprocess_finance_import_batch | execute | INSERT | finance_import_reprocess_runs | finance_import | slice-3 | 需移除 |  |
| 53 | services/finance_import_staging.py | stage_finance_rows | execute | INSERT | finance_import_rows | finance_import | slice-3 | 需移除 |  |
| 54 | services/finance_import_staging.py | stage_finance_rows | execute | UPDATE | finance_import_rows | finance_import | slice-3 | 需移除 |  |
| 55 | services/finance_import_staging.py | stage_finance_rows | execute | INSERT | finance_import_batches | finance_import | slice-3 | 需移除 |  |
| 56 | services/finance_import_staging.py | stage_finance_rows | execute | INSERT | finance_import_occurrences | finance_import | slice-3 | 需移除 |  |
| 57 | services/finance_import_staging.py | stage_finance_rows | execute | INSERT | finance_import_occurrences | finance_import | slice-3 | 需移除 |  |
| 58 | services/order_actual_start_reconfirmation.py | reconfirm_order_actual_start | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 59 | services/order_assignment_synchronization.py | _fetchall | execute | DYNAMIC | unknown | orders | slice-1 | 需移除 |  |
| 60 | services/order_assignment_synchronization.py | apply_order_assignment_sync | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 61 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | orders | orders | slice-1 | 需移除 |  |
| 62 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | case_staff_assignments | orders | slice-1 | 需移除 |  |
| 63 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | DELETE | staff_schedule | orders | slice-1 | 需移除 |  |
| 64 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | case_staff_assignments | orders | slice-1 | 需移除 |  |
| 65 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | INSERT | case_staff_assignments | orders | slice-1 | 需移除 |  |
| 66 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | case_staff_assignments | orders | slice-1 | 需移除 |  |
| 67 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | INSERT | order_assignment_change_audits | orders | slice-1 | 需移除 |  |
| 68 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | case_staff_assignments | orders | slice-1 | 需移除 |  |
| 69 | services/order_assignment_synchronization.py | apply_order_assignment_sync | execute | UPDATE | clients | orders | slice-1 | 需移除 |  |
| 70 | services/order_cancellation_command.py | cancel_order | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 71 | services/order_lifecycle_alert_projector.py | _claim_next | execute | UPDATE | order_lifecycle_projection_outbox | orders | slice-1 | 需移除 |  |
| 72 | services/order_lifecycle_alert_projector.py | _failed | execute | UPDATE | order_lifecycle_projection_outbox | orders | slice-1 | 需移除 |  |
| 73 | services/order_lifecycle_alert_projector.py | _process_next | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 74 | services/order_lifecycle_alert_projector.py | _process_next | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 75 | services/order_lifecycle_alert_projector.py | _projected | execute | UPDATE | order_lifecycle_projection_outbox | orders | slice-1 | 需移除 |  |
| 76 | services/order_lifecycle_control_commands.py | apply_order_lifecycle_control_command | execute | INSERT | order_lifecycle_control_events | orders | slice-1 | 需移除 |  |
| 77 | services/order_lifecycle_control_commands.py | apply_order_lifecycle_control_command | execute | INSERT | order_lifecycle_control_state | orders | slice-1 | 需移除 |  |
| 78 | services/order_lifecycle_control_commands.py | apply_order_lifecycle_control_command | execute | UPDATE | order_lifecycle_control_state | orders | slice-1 | 需移除 |  |
| 79 | services/order_lifecycle_hold_commands.py | apply_order_lifecycle_hold_command | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 80 | services/order_lifecycle_manual_correction.py | correct_order_lifecycle | commit | COMMIT | - | orders | slice-1 | 需移除 |  |
| 81 | services/order_lifecycle_persistence.py | persist_order_lifecycle_decision | execute | UPDATE | orders | orders | slice-1 | 需移除 |  |
| 82 | services/order_lifecycle_persistence.py | persist_order_lifecycle_decision | execute | INSERT | order_lifecycle_projection_outbox | orders | slice-1 | 需移除 |  |
| 83 | services/order_lifecycle_persistence.py | persist_order_lifecycle_decision | execute | UPDATE | orders | orders | slice-1 | 需移除 |  |
| 84 | services/order_lifecycle_persistence.py | persist_order_lifecycle_decision | execute | INSERT | order_lifecycle_state_events | orders | slice-1 | 需移除 |  |
| 85 | services/assignment_payroll_reconciliation_service.py | _q | execute | DYNAMIC | unknown | payroll | slice-2 | 需移除 |  |
| 86 | services/admin_auth_service.py | authenticate_admin | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 87 | services/admin_auth_service.py | authenticate_admin | execute | UPDATE | admin_users | platform_admin | slice-6 | 需移除 |  |
| 88 | services/admin_auth_service.py | authenticate_admin | execute | INSERT | admin_sessions | platform_admin | slice-6 | 需移除 |  |
| 89 | services/admin_auth_service.py | create_admin_user | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 90 | services/admin_auth_service.py | create_admin_user | execute | INSERT | admin_users | platform_admin | slice-6 | 需移除 |  |
| 91 | services/admin_auth_service.py | get_admin_session | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 92 | services/admin_auth_service.py | get_admin_session | execute | UPDATE | admin_sessions | platform_admin | slice-6 | 需移除 |  |
| 93 | services/admin_auth_service.py | record_admin_audit | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 94 | services/admin_auth_service.py | record_admin_audit | execute | INSERT | admin_audit_logs | platform_admin | slice-6 | 需移除 |  |
| 95 | services/admin_auth_service.py | renew_admin_session | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 96 | services/admin_auth_service.py | renew_admin_session | execute | UPDATE | admin_sessions | platform_admin | slice-6 | 需移除 |  |
| 97 | services/admin_auth_service.py | revoke_admin_session | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 98 | services/admin_auth_service.py | revoke_admin_session | execute | UPDATE | admin_sessions | platform_admin | slice-6 | 需移除 |  |
| 99 | services/data_browser_admin_audit_log_service.py | record_data_browser_patch_audit | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 100 | services/data_browser_admin_audit_log_service.py | record_data_browser_patch_audit | execute | DYNAMIC | unknown | platform_admin | slice-6 | 需移除 |  |
| 101 | services/data_browser_admin_audit_log_service.py | record_data_browser_patch_audit | execute | DYNAMIC | unknown | platform_admin | slice-6 | 需移除 |  |
| 102 | services/data_browser_admin_schema_service.py | patch_data_browser_table_row | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 103 | services/db_service.py | _sync_client_payment_due_dates_with_cursor | execute | UPDATE | client_payments | platform_admin | slice-6 | 需移除 |  |
| 104 | services/db_service.py | _sync_client_payment_due_dates_with_cursor | execute | UPDATE | client_payments | platform_admin | slice-6 | 需移除 |  |
| 105 | services/db_service.py | add_or_update_holiday | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 106 | services/db_service.py | add_or_update_holiday | execute | INSERT | holidays | platform_admin | slice-6 | 需移除 |  |
| 107 | services/db_service.py | backfill_client_payment_due_dates | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 108 | services/db_service.py | create_order | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 109 | services/db_service.py | create_order | execute | INSERT | unknown | platform_admin | slice-6 | 需移除 |  |
| 110 | services/db_service.py | create_order | execute | INSERT | orders | platform_admin | slice-6 | 需移除 |  |
| 111 | services/db_service.py | delete_holiday | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 112 | services/db_service.py | delete_holiday | execute | DELETE | holidays | platform_admin | slice-6 | 需移除 |  |
| 113 | services/db_service.py | mark_resume_sent | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 114 | services/db_service.py | mark_resume_sent | execute | UPDATE | matching_records | platform_admin | slice-6 | 需移除 |  |
| 115 | services/db_service.py | mark_resume_sent_for_case | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 116 | services/db_service.py | mark_resume_sent_for_case | execute | UPDATE | matching_records | platform_admin | slice-6 | 需移除 |  |
| 117 | services/db_service.py | reply_matching_inquiry | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 118 | services/db_service.py | reply_matching_inquiry | execute | UPDATE | matching_records | platform_admin | slice-6 | 需移除 |  |
| 119 | services/db_service.py | save_order_rest_dates | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 120 | services/db_service.py | save_order_rest_dates | execute | DELETE | staff_schedule | platform_admin | slice-6 | 需移除 |  |
| 121 | services/db_service.py | save_order_rest_dates | execute | UPDATE | orders | platform_admin | slice-6 | 需移除 |  |
| 122 | services/db_service.py | save_order_rest_dates | execute | INSERT | staff_schedule | platform_admin | slice-6 | 需移除 |  |
| 123 | services/db_service.py | sync_client_payment_due_dates_for_case_no | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 124 | services/db_service.py | update_matching_info_sent | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 125 | services/db_service.py | update_matching_info_sent | execute | UPDATE | matching_records | platform_admin | slice-6 | 需移除 |  |
| 126 | services/db_service.py | update_matching_info_sent | execute | UPDATE | matching_records | platform_admin | slice-6 | 需移除 |  |
| 127 | services/db_service.py | update_order_full_details | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 128 | services/db_service.py | update_order_full_details | execute | UPDATE | clients | platform_admin | slice-6 | 需移除 |  |
| 129 | services/db_service.py | update_table_row | commit | COMMIT | - | platform_admin | slice-6 | 需移除 |  |
| 130 | services/db_service.py | update_table_row | execute | UPDATE | unknown | platform_admin | slice-6 | 需移除 |  |
| 131 | services/db_service.py | update_table_row | execute | UPDATE | unknown | platform_admin | slice-6 | 需移除 |  |
| 132 | services/assignment_schedule_rest_date_service.py | apply_assignment_leave_resolution | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 133 | services/assignment_schedule_rest_date_service.py | apply_assignment_leave_resolution | execute | INSERT | assignment_schedule_leave_substitution_events | scheduling | slice-1 | 需移除 |  |
| 134 | services/assignment_schedule_rest_date_service.py | apply_assignment_leave_resolution_batch | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 135 | services/assignment_schedule_rest_date_service.py | apply_assignment_leave_resolution_batch | execute | INSERT | assignment_schedule_leave_substitution_events | scheduling | slice-1 | 需移除 |  |
| 136 | services/assignment_schedule_rest_date_service.py | apply_assignment_leave_resolution_batch | execute | INSERT | assignment_schedule_leave_substitution_batches | scheduling | slice-1 | 需移除 |  |
| 137 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 138 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | UPDATE | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 139 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 140 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | INSERT | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 141 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | INSERT | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 142 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_batch_mutations | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 143 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | INSERT | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 144 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | UPDATE | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 145 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | UPDATE | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 146 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | INSERT | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 147 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 148 | services/assignment_schedule_rest_date_service.py | execute_assignment_leave_resolution_mutations | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 149 | services/assignment_schedule_rest_date_service.py | read_assignment_leave_resolution_batch_replay_snapshot | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 150 | services/assignment_schedule_rest_date_service.py | read_assignment_leave_resolution_batch_replay_snapshot | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 151 | services/assignment_schedule_rest_date_service.py | save_assignment_rest_dates | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 152 | services/assignment_schedule_rest_date_service.py | save_assignment_rest_dates | execute | INSERT | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 153 | services/assignment_schedule_rest_date_service.py | save_assignment_rest_dates | execute | DELETE | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 154 | services/assignment_schedule_rest_date_service.py | save_assignment_rest_dates | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 155 | services/caregiver_availability_lock_cancellation_service.py | _load_event_for_key | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 156 | services/caregiver_availability_lock_cancellation_service.py | cancel_caregiver_availability_lock_for_order | execute | INSERT | caregiver_availability_lock_events | scheduling | slice-1 | 需移除 |  |
| 157 | services/caregiver_availability_lock_cancellation_service.py | cancel_caregiver_availability_lock_for_order | execute | UPDATE | caregiver_availability_locks | scheduling | slice-1 | 需移除 |  |
| 158 | services/caregiver_availability_lock_cancellation_service.py | cancel_caregiver_availability_lock_for_order | execute | UPDATE | caregiver_availability_lock_days | scheduling | slice-1 | 需移除 |  |
| 159 | services/caregiver_availability_lock_conversion_service.py | _load_preflight_lock_days | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 160 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 161 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 162 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | execute | UPDATE | orders | scheduling | slice-1 | 需移除 |  |
| 163 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | execute | INSERT | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 164 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | execute | UPDATE | caregiver_availability_lock_days | scheduling | slice-1 | 需移除 |  |
| 165 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | execute | INSERT | caregiver_availability_lock_events | scheduling | slice-1 | 需移除 |  |
| 166 | services/caregiver_availability_lock_conversion_service.py | convert_availability_lock_to_assignments | execute | UPDATE | caregiver_availability_locks | scheduling | slice-1 | 需移除 |  |
| 167 | services/caregiver_availability_lock_release_service.py | release_caregiver_availability_lock | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 168 | services/caregiver_availability_lock_release_service.py | release_caregiver_availability_lock | execute | UPDATE | caregiver_matching_plans | scheduling | slice-1 | 需移除 |  |
| 169 | services/caregiver_availability_lock_release_service.py | release_caregiver_availability_lock | execute | INSERT | caregiver_availability_lock_events | scheduling | slice-1 | 需移除 |  |
| 170 | services/caregiver_availability_lock_release_service.py | release_caregiver_availability_lock | execute | UPDATE | caregiver_availability_locks | scheduling | slice-1 | 需移除 |  |
| 171 | services/caregiver_availability_lock_release_service.py | release_caregiver_availability_lock | execute | UPDATE | caregiver_availability_lock_days | scheduling | slice-1 | 需移除 |  |
| 172 | services/caregiver_availability_lock_service.py | _occupancy_conflicts | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 173 | services/caregiver_availability_lock_service.py | _occupancy_conflicts | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 174 | services/caregiver_availability_lock_service.py | _occupancy_conflicts | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 175 | services/caregiver_availability_lock_service.py | _occupancy_conflicts | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 176 | services/caregiver_availability_lock_service.py | acquire_caregiver_availability_lock | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 177 | services/caregiver_availability_lock_service.py | acquire_caregiver_availability_lock | execute | UPDATE | caregiver_matching_plans | scheduling | slice-1 | 需移除 |  |
| 178 | services/caregiver_availability_lock_service.py | acquire_caregiver_availability_lock | execute | INSERT | caregiver_availability_lock_days | scheduling | slice-1 | 需移除 |  |
| 179 | services/caregiver_availability_lock_service.py | acquire_caregiver_availability_lock | execute | INSERT | caregiver_availability_lock_events | scheduling | slice-1 | 需移除 |  |
| 180 | services/caregiver_availability_lock_service.py | acquire_caregiver_availability_lock | execute | INSERT | caregiver_availability_locks | scheduling | slice-1 | 需移除 |  |
| 181 | services/caregiver_matching_communication_service.py | cancel_matching_plan | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 182 | services/caregiver_matching_communication_service.py | cancel_matching_plan | execute | INSERT | caregiver_matching_plan_events | scheduling | slice-1 | 需移除 |  |
| 183 | services/caregiver_matching_communication_service.py | cancel_matching_plan | execute | UPDATE | caregiver_matching_plans | scheduling | slice-1 | 需移除 |  |
| 184 | services/caregiver_matching_communication_service.py | record_matching_plan_willingness | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 185 | services/caregiver_matching_communication_service.py | record_matching_plan_willingness | execute | INSERT | caregiver_matching_plan_events | scheduling | slice-1 | 需移除 |  |
| 186 | services/caregiver_matching_communication_service.py | send_matching_plan_information | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 187 | services/caregiver_matching_communication_service.py | send_matching_plan_information | execute | INSERT | caregiver_matching_plan_events | scheduling | slice-1 | 需移除 |  |
| 188 | services/caregiver_matching_communication_service.py | send_matching_plan_resumes | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 189 | services/caregiver_matching_communication_service.py | send_matching_plan_resumes | execute | INSERT | caregiver_matching_plan_events | scheduling | slice-1 | 需移除 |  |
| 190 | services/caregiver_matching_plan_service.py | create_matching_plan_version | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 191 | services/caregiver_matching_plan_service.py | create_matching_plan_version | execute | UPDATE | caregiver_matching_plans | scheduling | slice-1 | 需移除 |  |
| 192 | services/caregiver_matching_plan_service.py | create_matching_plan_version | execute | INSERT | caregiver_matching_plan_segments | scheduling | slice-1 | 需移除 |  |
| 193 | services/caregiver_matching_plan_service.py | create_matching_plan_version | execute | INSERT | caregiver_matching_plans | scheduling | slice-1 | 需移除 |  |
| 194 | services/multi_caregiver_schedule_generation.py | _generate_assignment_schedule_with_cursor | execute | INSERT | staff_schedule | scheduling | slice-1 | 需移除 |  |
| 195 | services/multi_caregiver_schedule_generation.py | _generate_assignment_schedule_with_cursor | execute | UPDATE | case_staff_assignments | scheduling | slice-1 | 需移除 |  |
| 196 | services/multi_caregiver_schedule_generation.py | generate_assignment_schedule | commit | COMMIT | - | scheduling | slice-1 | 需移除 |  |
| 197 | services/staff_occupancy_mutex_service.py | lock_staff_occupancy_mutex | execute | DYNAMIC | unknown | scheduling | slice-1 | 需移除 |  |
| 198 | services/staff_actual_transfers.py | reconcile_staff_actual_transfer | execute | INSERT | staff_transfer_allocations | staff_payables | slice-4 | 需移除 |  |
| 199 | services/staff_actual_transfers.py | reconcile_staff_actual_transfer | execute | UPDATE | staff_monthly_settlements | staff_payables | slice-4 | 需移除 |  |
| 200 | services/staff_actual_transfers.py | reconcile_staff_actual_transfer | execute | INSERT | staff_actual_transfers | staff_payables | slice-4 | 需移除 |  |
| 201 | services/staff_actual_transfers.py | reconcile_staff_actual_transfer | execute | UPDATE | finance_import_rows | staff_payables | slice-4 | 需移除 |  |
