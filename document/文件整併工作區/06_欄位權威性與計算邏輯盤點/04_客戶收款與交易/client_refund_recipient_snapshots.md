# 客戶退款收款帳戶快照

| 欄位 | 權威性與規則 |
|---|---|
| `refund_obligation_identity` | 對應唯一 `payable_to_client` 的客戶退款單；一筆退款單恰有一筆快照。 |
| `bank_code`、`bank_account` | 退款單建立當下從已確認客戶退款資料讀取後固化；不是可編輯的付款明細欄位，也不得隨 BeClass 後續異動回寫。 |
| `source_kind` | 建立退款單的 owning-domain 路徑，用於稽核，不參與金額或核銷計算。 |

銀行流水事後核銷只接受已解析的 `resolved_counterparty_account` 等於 `bank_account` 且金額可完整分配的退款單；`due_date`、明細產出日及銀行交易日均不參與配對。帳戶缺失或不一致時保留為 typed manual review，不得建立正式退款核銷。此表為 2026-08-11 additive schema，既有沒有歷史快照的退款單不得自動推定帳戶。
