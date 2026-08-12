# `client_over_refund_recoveries` schema change record

- 狀態：2026-08-11 實作追蹤；本文件是欄位 lineage，正式業務契約仍以 `16_Staff_Payables與Client_Refund正式規格.md` 為準。
- Schema：`db/schema_parts/167_client_finance_overage_dispositions.sql`、`170_client_over_refund_recovery_collection.sql`、`171_client_over_refund_recovery_adjustment.sql`、`172_client_over_refund_recovery_matching.sql`
- Owner：Client Finance。

| 欄位／關聯 | 用途與不可變量 |
|---|---|
| `recovery_identity` | 退款超額追償根識別；同一來源退款 ledger／出款銀行列只可建立一次。 |
| `amount_due_ntd` | current remaining projection；只能由 canonical incoming collection 或具 capability 的 adjustment 以 CAS 更新，不能由 UI 直接寫入。 |
| `projection_version` | Preview／Apply optimistic concurrency version。 |
| `client_over_refund_recovery_events` | append-only event；保存 before/after、bank／ledger source、actor、reason、idempotency。 |
| `client_over_refund_recovery_apply_receipts` | idempotent replay receipt；同一銀行列不能二次收款。 |
| `client_over_refund_recovery_adjustment_receipts` | 無銀行入款的授權 adjustment receipt；以 command／preview fingerprint、版本與不可變 event 保存人工裁決。 |
| `client_over_refund_recovery_matchings` | Client Finance 所有的不可變人工配對；唯一綁定一筆 eligible incoming bank row 與一個 open recovery，保存配對當下 recovery/account version、actor、reason 與 idempotency。配對本身不核銷銀行列、不改 remaining。 |
| `client_over_refund_recovery_matching_receipts` | 配對 Preview／Apply 的 idempotent receipt；供異常中心取得固定 source bindings，不能由 alert details 或 UI 推算。 |
| `client_finance_outbox.client_over_refund_recovery_collected` | 僅於 matched collection 將 remaining 收至零時發送；projector 以同一 recovery identity 寫入 inactive root fact，自動解除 recovery-open alert。部分收回不重用已消耗 matching，必須等待下一筆 matching。 |

收款金額必須不超過 remaining；部分收款為 `partially_recovered`，歸零為 `recovered`，且不得自動抵銷其他應收。
銀行流水的 case／recovery 歸屬不是 Finance Import classification 欄位；由此 matching aggregate 的人工 reason/evidence 與 immutable binding 表達。每一筆新分類為 eligible incoming 的銀行列，都由 Finance Import manual-review root 作為查詢入口；Client Finance 在 Preview 時重新讀取該列與 open recovery，再於 Apply 寫入上述 immutable matching，不信任 alert 或 UI 傳回的衍生資料。
