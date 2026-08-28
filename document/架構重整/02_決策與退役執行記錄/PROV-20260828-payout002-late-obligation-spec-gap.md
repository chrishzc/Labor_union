# PAYOUT-002 late obligation correction 規格缺口

- `declared_status`: `proposed`
- `pipeline_status`: `AUTHORITY_REQUIRED`
- `research`: `NO_RESEARCH (R0)`；阻塞是業務 Authority，不是技術證據
- `code`: `PAYOUT-002`

`PAYOUT-002` 表示 immutable Staff obligation event 在原 due date 後建立或改變金額；它是 Payroll
root／lineage完整性問題，不代表目前金額必然錯誤。Anomalies只保存alert/detail/recheck，Staff Payables只負責
payout/allocation；不能靠tracking、改日期、改projection或generic resolve解除。

候選 owner flow 為 Payroll Query late event／before-after delta／case-assignment-staff/version/payout history，
zero-write Preview依正式服務日、rate snapshot、special pay與既有adjustments重建candidate，Apply append immutable
correction/disposition／allocation／receipt／outbox。正差額另交既有 exact Staff payout；負差額不得偷偷併入，
需明確裁決是否轉 Staff overpayment recovery。

## Authority blockers

| ID | 必要裁決 |
|---|---|
| `P002-B1` | 合法但晚到的event是否需要immutable disposition/review completion root |
| `P002-B2` | constrained reuse現有PayrollAdjustmentWorkflow，或建立綁定source delta的專用typed command |
| `P002-B3` | zero／positive／negative delta及既有payout history的互斥分支；負差額successor |
| `P002-B4` | correction/disposition後的versioned terminal predicate與action contract |

以上未裁決前不得標 `SPEC_READY`、不得編譯task pack、不得修改source／DB／Browser。stale、identity drift、
delta不符、partial payout、receipt-only、readback unavailable均保持active。

```yaml
convergence:
  status: NOT_READY
  blockers: [P002-B1, P002-B2, P002-B3, P002-B4]
```
