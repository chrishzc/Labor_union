# `finance_reports.py` AP-only Delta Freeze

後續Reports writer開始前必須fresh-read並保留下列已凍結AP delta：

1. 新增`require_admin`與`AdminPrincipal` imports。
2. 只有`preview_accounts_payable`新增principal dependency並維持query-only。
3. `_accounts_payable_row`只輸出`bank_account_masked`、`recipient_identity_card_masked`。
4. `_mask_bank_account`與`_mask_identity_card`在server boundary完成redaction。
5. `AccountsPayableRowView`同步只接受兩個masked欄位。

Quarterly／annual subsidy preview/export、AP export/archive、legacy summary與其公式完全未改。本delta與Reports subsidy writer不得以ours/theirs覆蓋；發現base drift時先做collision inventory。

