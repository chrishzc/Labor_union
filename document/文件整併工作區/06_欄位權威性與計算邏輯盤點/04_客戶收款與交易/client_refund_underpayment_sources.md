# 客戶退款少匯來源

| 欄位 | 權威性與規則 |
|---|---|
| `underpayment_identity` | 一次已確認的退款少匯 Apply 的不可變根識別；不是 UI 可輸入或可改寫的餘額。 |
| `bank_total_ntd` | 該次已匯出的 canonical outgoing 銀行列總額；僅作事實與稽核，不是後續自動扣抵來源。 |
| `remaining_after_ntd` | Apply 當下所選退款單剩餘合計的快照；目前剩餘仍以 `client_obligations` 的正式投影為準。 |
| `resulting_account_version` | 該次退款 Apply 成功後的 Client Finance account version，用於 stale/replay 稽核。 |
| `client_refund_underpayment_source_bank_rows` | 已消耗的實際出款銀行列集合；每列只能綁定一個少匯來源，更新／刪除皆禁止。 |
| `client_refund_underpayment_source_obligations` | 當次仍未結清的退款單集合與各自剩餘快照；更新／刪除皆禁止。 |

退款少匯先由系統建立退款單、交會計明細後才可能在銀行列出現。事後對帳只保存實際已出款金額；未結餘額仍是原退款單的正式應付款，不會因為少匯來源另生第二張退款單。後續新的出款列必須重新選擇並核銷既有退款單；退款單日期、明細日期及銀行交易日期都不參與配對。
