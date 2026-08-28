---
doc_type: work-package
declared_status: proposed
date: 2026-08-27
owner: finance-import / anomalies-projection
authority_status: AUTHORITY_REQUIRED
---

# IMPORT-006 canonical source version source-only 工作包

## 1. Scenario 與既有 Authority

Finance Import 批次完成或 historical reprocess 完成後，Anomalies projector 必須以同一批次的
current integrity roots 決定 `IMPORT-006` 是否 active。正式 `09_Finance_Import_Domain.md` §6.2
已固定：identity 是 `finance-import-batch:<batch_id>`，active predicate 只有
`integrity_inconsistent_count > 0`，普通待分類列不得啟動此碼。

既有 schema 已由 Finance Import owner 提供
`finance_import_batch_contracts.batch_version`；本包不新增 root、版本公式或 schema。這是 source-only
live-drift 修正候選，不改業務語意。正式施工前仍需將本包由人工確認為 `approved`；`proposed` 文件本身
不構成 production code mutation Authority。

## 2. Current live-drift

1. `subsystems/anomalies/finance_import_review_alert.py` 的 public projector 允許
   `source_version=0` default；caller 未傳版本時會把不具 freshness 證據的 projection 當成合法 current
   state。
2. `subsystems/anomalies/finance_import_anomaly_consumer.py` 的 historical reprocess consumer 使用 outbox
   event id 當 `source_version`。Event identity 可用於 replay checkpoint，但不是 Finance Import batch root
   version。
3. projector 目前分開讀 completed batch、membership、member rows、latest reprocess run，卻沒有先讀取並
   鎖定 canonical batch contract。若讀取期間 owner facts 改變，可能以混合 snapshot 錯誤解除或重開警示。

## 3. Required contract

### IMPORT006-SV-A1 Canonical version

- `source_version` 唯一來源為對應 batch 的
  `finance_import_batch_contracts.batch_version`。
- public projector 不接受 caller 自填 version，不保留 `0` default，也不得以 outbox id、reprocess run id、
  timestamp 或 `updated_at` 代替。
- 缺 batch contract、identity 不一致、version 非非負整數時 fail closed，零 alert mutation、零 checkpoint。

### IMPORT006-SV-A2 Fresh root read

- projector 在 caller 的 outer Unit of Work 中，以 `batch_id` 讀取並鎖定 batch contract，再於同一 transaction
  讀 completed batch、occurrence membership、canonical member rows 與 latest completed reprocess run。
- projection request 的 `source_version` 使用鎖定所得 `batch_version`；details、summary、active predicate、
  fingerprint 與 checkpoint 都必須屬於同一 root snapshot。
- 若 facts 在 Apply 前無法證明 fresh，固定回 typed unavailable／conflict，不能沿用舊 summary 解除。

### IMPORT006-SV-A3 Identity、replay 與 outbox

- `source_event_identity` 仍是 replay／checkpoint identity，可由 durable outbox event identity或 deterministic
  bounded scan identity提供；它不得承擔 aggregate version 語意。
- exact event replay＋相同 batch version／root snapshot 回既有結果，不新增 occurrence 或 workflow event。
- 相同 event identity 搭配不同 batch、version 或 root fingerprint 必須 fail closed。
- import／reprocess owner transaction 先 commit；projection consumer post-commit執行。Projection failure 不回滾
  Finance Import，但必須保留 durable retry；不能把 delivery receipt 當作 alert 已解除。

### IMPORT006-SV-A4 Predicate 與人工修正

- active predicate保持 `integrity_inconsistent_count > 0`，不得把普通
  `non_business_review + pending` 數量算入完整性異常。
- 人工處理只能導向 Finance Import owner 的 reprocess／source correction Q/P/A；claim、tracking、通用
  resolve 或 outbox delivered 都不能解除。
- owner correction 後重新讀取同一 batch 的 current version及完整性 roots。只有新的 current snapshot 中
  inconsistent count 為 0，`IMPORT-006` 才自動從 active list消失；仍有任一問題則保持或 reopen。

## 4. Write set 與 exclusions

唯一候選 production write set：

- `subsystems/anomalies/finance_import_review_alert.py`
- `subsystems/anomalies/finance_import_anomaly_consumer.py`
- `subsystems/finance_import/application.py`（只有 caller wiring確有需要時）
- 對應 focused tests：`tests/test_finance_import_review_alert.py`、
  `tests/test_remote_anomaly_schedule_merge.py`、`tests/test_finance_import_recovery_subsystem.py`

不得修改 schema、migration、Finance Import predicate、batch version increment公式、API public response、
React UI、其他 anomaly code、provider或 `union_db`。如需要 schema／new root／public interface，停止並另立
Work Package。

## 5. Acceptance 與驗證

1. Unit contract：缺 contract、錯 batch identity、invalid version、caller version injection皆零投影且 fail
   closed；valid contract 將 exact `batch_version` 傳入 canonical request。
2. Freshness：在鎖定後模擬 version drift不得解除；同 snapshot 的 active、resolve、reopen皆使用同一
   version。
3. Replay：exact outbox replay不新增 workflow event；event id只出現在event/checkpoint identity，不出現在
   source version。
4. Predicate regression：missing、unexpected、duplicate、non-pending inconsistency、partial batch任一非零
   均 active；全部為0才 inactive；普通待分類 rows不啟動。
5. Focused Python tests、相關 Finance Import disposable MySQL lifecycle、`git diff --check`、strict UTF-8
   全部 passed。真服務未啟動時 API／Browser標 `NOT_RUN`，不得用 mock升格。

## 6. DB change gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `BLOCKED` | source-only contract已界定，但本 proposed package尚待人工核准。 |
| Change inventory | `PASS` | schema-only、system-seed、business-row-backfill、destructive皆 `none`。 |
| Static release gate | `NOT_RUN` | 本包禁止 DB artifact；若 diff出現DB變更即停止。 |
| Descriptor gate | `NOT_RUN` | 無 owned-object schema變更。 |
| Read-only plan gate | `NOT_RUN` | 無 migration release。 |
| Engine verification gate | `NOT_RUN` | package未核准、source尚未施工。 |
| Developer acceptance gate | `NOT_RUN` | 前置 acceptance尚未執行。 |

總結：`DB_CHANGE_NOT_READY`。此結論不阻止核准後的 source-only 實作，但禁止以本包修改或套用 DB。
