# Historical baseline storage 與 substitution supplement 規格缺口

- `spec_gap_id`: `PROV-20260827-historical-operational-storage-and-supplement`
- `declared_status`: `approved`
- `authority_status`: `CONFIRMED-2026-08-27`
- `controlling_spec`: `PROV-20260827-historical-order-operational-baseline-spec.md`
- `affected_packages`: `WP-HOB-A` storage lane、`WP-HOB-C` optional supplement lane
- `unaffected_packages`: `WP-HOB-B` behavior contract、`WP-HOB-C` substitution core、`WP-HOB-D`、`WP-HOB-E`、`WP-HOB-F`

## 1. 已確定且不重開的行為

1. Historical baseline 是 append-only operational root，不建立 LINE、簽章、付款、allocation、
   assignment 或 lifecycle 假事件；workflow source contract目前 focused `25 passed`。
2. 服務中 substitution 不要求代班新契約／簽回或客戶追加簽署；核心 gate目前 focused
   `28 passed`。`substitution_supplement` 只是 optional evidence，缺少或 archive failure 不得阻擋
   substitution、排班 lineage、actual service 或 Payroll。

## 2. 已採用 B1：Historical baseline storage bundle

建議一次核准下列同一 Orders operational projection bundle：

- 新增 append-only `historical_order_operational_baseline_events`、
  `historical_order_operational_baseline_receipts` 與 baseline-owned outbox；不得 reuse lifecycle、
  historical review remediation或tracking tables冒充 baseline。
- event 允許 optional self-FK `prior_baseline_event_identity`，只表達 successor lineage；FK
  `RESTRICT`，event／receipt business columns禁止 UPDATE／DELETE。
- event 保存 immutable candidate snapshot，包含 selected step、當時 Orders/provenance versions、
  owner-binding fingerprint、evidence與 step projection；current step仍由最新 baseline＋current owner
  roots重新投影，snapshot不倒退也不取代current owner facts。
- outbox intent/business payload append-only；只有 attempts／published／last-error等delivery metadata
  可由worker更新。無business-row backfill、無system seed、無destructive change。
- 新release predecessor為current `1009`；實際release ID、schema part number與descriptor由integration
  writer在fresh chain late-bind，不構成額外業務裁決。

本bundle已由人工採用；WP-HOB-A的Scope與Change inventory可進入release inventory，Static release／
Descriptor／plan／engine／developer acceptance仍須以實際candidate驗證，不因裁決自動PASS。

## 3. 已採用 S1：Substitution note owner／lineage／storage

建議一次核准下列 Scheduling-owned bundle：

- owner固定 `scheduling`，功能定位為不影響流程的`substitution_note`；可選附件才使用controlled-file
  purpose `substitution_supplement`，沒有附件仍可建立純文字備註。
- 每筆note綁定一個canonical `scheduling_leave_substitution_batches.batch_key`，並綁定該
  batch內非空、排序且不重複的 exact `substitute` outcome identities；不得綁到 leave-only／defer outcome，
  不得只用case number猜目標。
- 新增dedicated append-only note evidence table，controlled file object reference可為NULL；保存
  batch/outcomes、actor、note、method、version、fingerprint、idempotency與receipt。不得把typed fields藏在
  generic result JSON，也不得形成signed／customer-accepted fact。
- controlled-file object key使用purpose-specific canonical path，避免改寫既有跨purpose unique contract；
  staging/object purpose enum與owner-purpose checks依versioned additive release更新。
- note Query／Preview／Apply是獨立UoW；note未填、取消、保存失敗或附件archive failure都不回滾已提交的
  substitution，不建立substitution／Payroll blocker，也不改變任何assignment或薪資root。

## 4. 已採用 S2：Manual note method enum

採用closed enum：`phone | paper | email | in_person | line_manual_record | other`。
`line_manual_record` 只表示人員上傳／登錄的人工證據，不得偽造LINE provider delivery或callback；
選 `other` 時reason仍必填。若集合不足，需由人工直接增刪值後才能固定API/schema。

```yaml
convergence:
  status: READY
  blockers: []
```

2026-08-27人工已回覆採用B1／S1／S2，並補充S1／S2只是備註功能、不影響流程運行。本文件由
spec gap轉為approved storage／note contract；後續schema、API與runtime仍須通過各自gates。
