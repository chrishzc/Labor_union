# PAYOUT-003 Staff bank-master correction 規格缺口

- `declared_status`: `proposed`
- `pipeline_status`: `AUTHORITY_REQUIRED`
- `research`: `NO_RESEARCH (R0)`；阻塞是owner／completion業務裁決
- `code`: `PAYOUT-003`

`PAYOUT-003` 表示月嫂銀行主檔 missing／ambiguous／incomplete。`staff_bank_accounts` 是current SSOT，但正式
mutation owner、aggregate version與branch policy尚未固定；現有registry只有 `QueryStaffPayables`，沒有銀行主檔
correction Q/P/A或terminal predicate。

候選 flow：typed `QueryStaffBankMaster` 顯示masked完整account set／version／issues／open obligations；
`PreviewStaffBankMasterCorrection` 只接受完整 replacement set，驗證唯一primary、3碼bank code、純數字account、
owner唯一性與fresh version；Apply在單一UoW append correction event／receipt／outbox並fresh readback。後續 payout
只能reuse既有 `Preview/ApplyStaffPayout`，不得修改canonical bank facts或直接建立ledger。

## Authority blockers

| ID | 必要裁決 |
|---|---|
| `P003-OWNER` | Staff／Staff Profile／Staff Payables之中誰是bank-master mutation owner、root/version contract |
| `P003-CLOSURE` | bank correction即解除，或必須bank correction＋exact payout＋fresh recheck才解除 |
| `P003-BRANCH` | branch code依銀行必填／選填的正式policy |

blockers未解除前，候選B～E package只能作proposal，不得宣稱 `PACKAGE_READY`；Scope／Change inventory為
`BLOCKED`，其餘DB gates `NOT_RUN`，總結 `DB_CHANGE_NOT_READY`。完整帳號不得進UI/log/receipt。

```yaml
convergence:
  status: NOT_READY
  blockers: [P003-OWNER, P003-CLOSURE, P003-BRANCH]
```
