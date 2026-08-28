# GOVSUB-006 政府溢撥異常 code-only 修補工作包

- 狀態：`completed`
- package status：`COMPLETED_CODE_ONLY`
- controlling spec：`PROV-20260826-finance-recovery-anomaly-closure-spec.md`
- Authority：既有SPEC_READY只授權bounded Q/P/A、fresh predicate與React wiring；不授權schema變更。

## Scope

### WP-A Backend fail-closed

- 多個active return recipient不得`LIMIT 1`任選；Preview／Apply回typed blocker且零寫入。
- owner readback與outbox lineage必須綁source transaction對應projection，不取unrelated latest event。
- focused repository/workflow tests；不改schema、migration、public business formula。

### WP-B React exact action與no-resend

- GOVSUB-006只接受完整`government_subsidy.overpayment.disposition.v1` action contract與recovery context；unknown/missing binding fail closed。
- timeout／unknown不得自動第二次Apply；保留同一command identity，改查owner root／receipt狀態。
- receipt不等於解除；fresh owner root離開`pending_review`且原anomaly exact fingerprint `predicate_active=false`才完成。
- 補AnomaliesPage integration、timeout/no-resend、receipt-only、stale/readback failure tests。

## Exclusions／blocker

`government_subsidy_overpayment_offsets(overpayment_identity, claim_item_id)`現有unique key可能使同target第二次partial offset stranded。任何constraint/index/schema修正均為`BLOCKED_SCOPE`，需另立DB Work Package並完整通過3.1 gates。本包不得用code workaround、改寫原offset或宣稱partial-offset全流程完成。

## Acceptance

- Backend ambiguous recipient、future/unusable recipient、unrelated projection lineage fail closed。
- React unknown/timeout Apply count固定1；same command可reconcile，receipt-only不completed。
- exact action contract/page renderer與fresh owner/anomaly readback測試PASS。
- Python/React focused、build、diff PASS；服務未啟動則runtime`NOT_RUN`。
- Luna High/high E3無P0/P1。

## DB inventory

schema-only／system-seed／business-row-backfill／destructive均`none`。若diff出現DB變更立即停止並回報`DB_CHANGE_NOT_READY`。

## DDH projection

Backend repository與React workbench write set隔離，可用E4兩條Luna High/high writers；parent保留spec/integration。final candidate轉E3唯讀verifier。

## Execution result（2026-08-27）

- Backend／React code-only acceptance：`passed`。
- E3 round 1發現四項P1後，分成backend／React Luna High/high隔離回修；round 2 P0/P1=0。
- Parent final：Python `42 passed`、React `25 passed`、production build與diff PASS。
- Runtime：`not_run`；服務未啟動。
- Partial-offset unique-key：`BLOCKED_SCOPE`，未修改schema，且不屬本包完成聲明。
- Receipt：`03_追蹤清單與證據/evidence/2026-08-27_govsub006_code_only_remediation_receipt.md`。
