# Writer Inventory v3 Owner Resolution

## Scope

This note resolves the source-level owner ambiguity for the 13 v3 candidate
findings whose generated `unresolved_reason` is
`owner_not_deterministic_from_path`.

It does not change the generated candidate manifest, approve writer removal,
or substitute for caller and replacement-receipt evidence.

## Resolved owner evidence

| Source | Findings | Owner | Transaction boundary | Disposition |
| --- | ---: | --- | --- | --- |
| `infrastructure/mysql/historical_reprocess_repository.py` | 7 | Finance Import | The typed Historical Reprocess workflow owns the outer Unit of Work; this repository appends classification events, run, receipt, source outbox and the optimistic batch-version update within that boundary. | Retain as the canonical Finance Import persistence adapter. |
| `infrastructure/mysql/process_reminder_anomaly_source.py` | 2 | Anomalies | `consume_process_reminder_anomaly_sources()` starts one connection transaction and delegates current-alert projection to `AnomalyApplication` and `MySqlAnomalyRepository`. | Retain as an Anomalies projection source adapter; it does not own or synthesize business root facts. |
| `infrastructure/mysql/subsidy_advance_recovery_repository.py` | 2 | Client Finance | The repository persists the canonical subsidy-advance recovery link and its Client Finance source outbox intent against an already-established Government Subsidy allocation. | Retain as the Client Finance recovery adapter; it is not a legacy subsidy projection. |
| `infrastructure/mysql/admin_command_repository.py` | 2 | Access Control | `source_data_correction` permits only the three confirmed source tables and their approved fields; Apply rechecks the preview fingerprint under a row lock and persists the receipt in the same transaction. | Retain the fact loader as restricted and the source-row update as the canonical Access correction writer. |

## Current caller evidence

| Adapter | Production caller chain | Result |
| --- | --- | --- |
| Historical Reprocess | `api/dependencies/finance_import.py` -> `HistoricalReprocessWorkflow` -> `MySqlHistoricalReprocessRepository` | Typed Finance Import API remains a live caller. |
| Process Reminder Anomalies | `subsystems/anomalies/outbox_worker.py` -> `consume_process_reminder_anomaly_sources()` | Canonical Anomalies outbox worker remains a live caller. |
| Subsidy Advance Recovery | `subsystems/client_finance/subsidy_advance_outbox_consumer.py` -> `SubsidyAdvanceRecoveryWorkflow` -> `MySqlSubsidyAdvanceRecoveryRepository` | Government Subsidy source-outbox delivery remains a live caller. |
| Source Data Correction | `api/routes/data_browser_admin.py` -> `subsystems/access/source_data_correction.py` -> `AdminCommandRepository` | Typed Data Browser correction can change only confirmed source facts through Preview -> Apply -> receipt. |

## Remaining evidence required

- Replacement receipt remains unproven for all 13 items.
- None of these items is an approved removal candidate.
- The generated `writer_inventory_v3_candidate.*` artifacts remain the
  authoritative machine inventory until their generator consumes this evidence
  through an explicitly approved disposition workflow.

## Disposition-layer adoption

The reviewed `writer_inventory_v3_disposition.*` layer now records these 13
findings as `retain_canonical`. Its validator binds every reviewed identity and
fingerprint to the current candidate evidence hash. The candidate artifacts
remain machine-generated and `blocked`; the new records grant no removal
authority.

## Broad adapter migration slice

All current 20 `migrate_then_remove_candidate` rows from
`infrastructure/mysql/mysql_adapter.py` are now covered by the reviewed layer.
Sixteen inactive legacy client-payment, order-bootstrap, and matching writers
are `migrate_then_remove`; four `save_order_rest_dates` rows are
`retain_restricted` because `scripts/generate_fake_data.py` uses them only for
fixture data; and nine active Holiday, order-details, and Data Browser rows are
`needs_decision`. One generic Data Browser UPDATE appears twice in the source
candidate with the same identity and fingerprint, so one disposition correctly
covers both candidate rows. No row is approved for removal.

## WP63 full owner-review completion

2026-08-12 已完成 merge-introduced owner review queue 的逐 source-path 裁決。Reconciler 使用明確
exact-path registry，不以目錄前綴自動推論 owner；每筆 record 保存 candidate identity、fingerprint、
owner、outer transaction boundary、runtime caller、replacement evidence 與 final disposition。

| Disposition | Count | Meaning |
|---|---:|---|
| `retain_canonical` | 745 | typed owning Domain／Global workflow、repository、receipt 或 outbox boundary |
| `retain_restricted` | 278 | worker claim、heartbeat、query、migration、validation 或受限 compatibility boundary |
| `migrate_then_remove` | 4 | replacement direction 已存在，但 code removal 尚未獲授權 |
| `needs_decision` | 0 | owner review queue 已清空 |
| `approved_to_remove=true` | 0 | 本 review 不授權移除任何 writer |

四筆 `migrate_then_remove` 分屬：

- `api/routes/clients.py::update_client_identity_status` 的 commit／UPDATE：typed LINE identity workflow
  是 canonical replacement；仍須另立 entrypoint retirement package。
- `subsystems/scheduling/staff_leave_review_service.py::decide_staff_leave_review` 的 commit／UPDATE：
  無 canonical route，後續由已確認的 Scheduling LINE request evidence 計畫承接；實作與退役仍需
  獨立核准。

完成證據：`../2026-08-12_writer_inventory_v3_owner_review_completion_receipt.md`。
