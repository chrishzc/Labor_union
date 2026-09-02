# `government_subsidy_overpayments` schema change record

- 狀態：2026-08-11 實作追蹤；本文件是欄位 lineage，正式業務契約仍以 `14_Government_Subsidy_Domain.md` 為準。
- Schema：`db/schema_parts/169_government_subsidy_overpayment_disposition.sql`、`178_government_subsidy_overpayment_apply_receipts.sql`
- Owner：Government Subsidy。

| 欄位／關聯 | 用途與不可變量 |
|---|---|
| `overpayment_identity` | canonical government receipt 差額的 root identity。 |
| receipt／bank／payer lineage | 原始入款全額、正常 claim allocation 與差額之間的不可變可追溯關係。 |
| `remaining_amount_ntd`、`status`、`projection_version` | current disposition projection；只可由同 payer 的合法 approved target offset 或政府退款 payable 流程以 CAS 改變。 |
| offset／return payable／對帳紀錄／events／receipts | immutable allocation、目標 claim account projection event、政府帳戶 snapshot、canonical outgoing bank fact、idempotency 與 outbox evidence；`government_subsidy_overpayment_apply_receipts` 以 command fingerprint 保存 offset、return、return-reconciliation 的首次結果，同 key 同命令必須回放同一 receipt，不同命令 fail closed。差額不可寫入 Client Finance、Staff Payables 或提高 claim approved amount。退款單先產生下一期應付明細；會計在系統外匯款，後續帳單只依退款對象與金額對帳，退款單日期不是配對條件。 |

尚無合法 target 時維持 `pending_review`；offset 與 return payable 互斥。政府退款的實際出款另以 canonical outgoing bank fact 核銷。
