---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Anomalies / Case Import / Finance Import / Orders
priority: P0
---

# 94 匯入警示查詢與人工追蹤 Work Package

## 決策與目的

本包承接 WP90 與 WP92 已裁定但尚未落地的 warning center typed Query 與人工狀態
Preview／Apply。公會人員只可查看去敏警示並記錄外部聯絡進度；不得修正來源列、建立
正式 root、推測 LINE recipient，或把 `closed` 解讀為資料已修正。

## Business scenario 與 owner

當 HCM、Client／Staff BeClass、Historical Orders 或 Finance Import 產生欄位級 source
warning 時，公會人員在異常中心查看去敏 subject、issue code 與目前 tracking status，依序
記錄「待聯絡填寫者」、「等待回覆」、「要求重新提交」或結束聯絡工作。Anomalies 擁有
tracking event、current task、receipt 與 outbox；各 owning lane 仍擁有 source fact、正式
root、reimport 與 auto-resolve predicate。

## Scope 與 write set

- `domains/anomalies/import_warning_tracking.py`：沿用既有六狀態 reducer；不新增業務語意。
- `subsystems/anomalies/import_warning_tracking_workflow.py`：typed Query、Preview／Apply、
  idempotency、stale 與 receipt 編排。
- `infrastructure/mysql/import_warning_tracking_repository.py`：只存取 part 195 的 occurrence、
  event、current task、receipt 與 outbox，且由單一 outer Unit of Work commit。
- `api/schemas/import_warning_tracking.py`、`api/dependencies/import_warning_tracking.py`、
  `api/routes/import_warning_tracking.py`、`api/main.py`：authenticated typed API。
- `ui/api_clients/import_warning_tracking_api_client.py` 與
  `ui/pages/06_finance_alerts.py`：typed client、去敏清單與 Preview／Apply 操作區。
- `tests/test_import_warning_tracking_workflow.py`：replay、different-payload conflict、stale、
  forbidden auto-resolve 與 zero-write Preview。

## Non-goals

- `WarningReferral`、來源重新提交關聯與 `auto_resolved` predicate 不在本包；每個 owner
  command 必須另包，並鎖定其 root 後重新驗證。
- 不新增或修改 schema、migration、backfill、production data、LINE delivery、recipient
  binding、corrected payload、generic correction form 或 Data Browser writer。
- 不改寫 `anomaly_current_alerts` 的 generic claim／resolve workflow。

## 契約與不變量

1. Query 唯讀；Preview 零寫入；Apply 在同一 outer Unit of Work 內重新讀取並鎖定 current
   task，再 append immutable event、receipt 與 outbox，最後一次 commit。
2. `union_operator` 只能依既有 reducer 推進 active status 或 `closed`；只有 system actor 可
   `auto_resolved`。`closed` 不代表 source 或 root 已修正。
3. same idempotency key 且 fingerprint 相同回既有 receipt；同 key 不同 payload 回
   `idempotency_mismatch`；expected version 不一致回 `import_warning_version_conflict`。
4. API 與 UI 不接受 corrected fields、raw workbook、完整個資、LINE conversation 或任意
   owning-Domain endpoint。
5. UI 僅顯示 masked subject、field path、issue codes、狀態與去敏 evidence reference；未知
   response schema、狀態或 typed error 一律 fail closed。

## Acceptance

- focused Module／Subsystem tests 覆蓋狀態機、replay、conflict、stale、transaction failure。
- disposable MySQL 驗證 part 195 event／receipt／outbox 原子性與 immutable trigger。
- authenticated API／Streamlit 只顯示去敏內容，Preview 無寫入，Apply 後重新 Query。
- 不執行 developer-local replacement、production migration、外部通知或 owner referral。

## DB gate

| Gate | 狀態 | 證據／命令 |
|---|---|---|
| Scope | PASS | 本包限定既有 part 195 tables，無 schema mutation。 |
| Change inventory | PASS | `schema-only`、seed、backfill、destructive 均無。 |
| Static release | NOT_RUN | 不適用於本包；沿用 WP92 release。 |
| Descriptor | NOT_RUN | 不適用於本包；沿用 WP92 descriptor。 |
| Read-only plan | NOT_RUN | 不適用於本包；無 schema mutation。 |
| Engine verification | NOT_RUN | 待 disposable MySQL acceptance。 |
| Developer acceptance | NOT_RUN | 本包不授權操作既有資料庫。 |

驗收完成：詳見 `../../03_追蹤清單與證據/evidence/2026-08-15_wp94_import_warning_tracking_receipt.md`。
本包沒有 schema mutation；隔離 engine evidence 不構成既有 developer-local database 的操作授權。
