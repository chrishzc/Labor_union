# `staff_overpayment_recoveries` schema change record

- 狀態：2026-08-11 實作追蹤；本文件是欄位 lineage，正式業務契約仍以 `16_Staff_Payables與Client_Refund正式規格.md` 為準。
- Schema：`db/schema_parts/168_staff_payout_difference_recovery.sql`、`173_staff_overpayment_recovery_matching.sql`、`174_staff_payout_difference_source.sql`
- Owner：Staff Payables。

| 欄位／關聯 | 用途與不可變量 |
|---|---|
| `recovery_identity`、`staff_id` | 月嫂超額付款追償根；連回唯一月嫂與來源 payout。 |
| `original_amount_ntd` | 建立時固定的超額金額，不可修改。 |
| `remaining_amount_ntd`、`status`、`aggregate_version` | 可重建的 current projection；僅由 CAS 的 collection／authorized adjustment 改變。 |
| source JSON identities | 保存 canonical outflow、payout event、obligation lineage；不是可自由編輯的帳務分配。 |
| `staff_overpayment_recovery_events` | append-only cash／adjustment event，保存 before/after、bank source、actor、reason、evidence、capability、correlation、idempotency。 |
| `staff_overpayment_recovery_apply_receipts` | stable-key replay receipt；同一 incoming bank row 只能使用一次。 |
| `staff_overpayment_recovery_matchings` | 不可變人工配對：唯一綁定 eligible 月嫂退匯入款與 open recovery，保存 staff、recovery/staff-payables version、actor、reason 與 idempotency；本身不改 remaining 或銀行核銷。 |
| `staff_overpayment_recovery_matching_receipts` | matching Preview／Apply receipt；Anomalies 只能使用其固定 source bindings。 |
| `staff_payables_outbox.staff_overpayment_recovery_collected` | 僅在 matched collection 收至零時發布；projector 以 recovery identity 寫入 inactive root fact，自動解除 recovery-open alert。部分收回等待下一筆 matching。 |
| `staff_payout_difference_sources` | 一次 difference Apply 完成後的不可變 multi-bank audit/replay source；保存 staff、under/over mode、銀行／義務總額、recovery、resulting version、actor、reason、correlation。它證明當時使用的完整集合，不是下一次 Apply 的可重用指令。 |
| `staff_payout_difference_source_bank_rows`、`staff_payout_difference_source_obligations` | 以 FK 與 update/delete trigger 保存不可變的完整 bank-row set 與 obligation set，避免日後只能從一筆 row 猜測整次差額；由於列已消耗，Anomalies 不得用它重新發動 payout Apply。 |

collection 僅接受唯一月嫂的 canonical incoming TWD staff-return bank fact；部分收回保留 `partially_recovered`，歸零轉 `recovered`。每一筆新分類為 eligible staff-return 的銀行列，都由 Finance Import manual-review root 作為查詢入口；Staff Payables 在 Preview／Apply 重新讀取銀行列、月嫂帳戶與追償版本後才可寫入 immutable matching。追償永遠不進應付清冊，也不得自動扣未來薪資。
