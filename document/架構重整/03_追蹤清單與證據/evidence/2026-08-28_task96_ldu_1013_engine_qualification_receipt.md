# Task 96 LDU 1013 engine qualification receipt

- `package_id`: `LDU-1003-CURRENT-01`
- `scope`: `1013_order_lifecycle_pending_status_constraint.sql`
- `status`: `passed`
- `qualification`: `validation/receipts/PROV-20260828-local-additive-qualification-order-lifecycle-pending-status.json`
- `payload_digest`: `acbfd6d7179c1b89e7b4d8b7377fb3736b521f84be05d1a5eef9ee9c9d74be30`

## Engine evidence

- Source：`lu_test_task96_ldu_candidate_1012_r1`，1012 exact、1013 absent，含3筆clients、3筆orders及既有
  Task 96 runtime代表資料。
- Candidate：`lu_test_task96_ldu_candidate_1013_r1`；release-scoped plan ready後完成source dump、全新還原、
  單一atomic CHECK replacement與final verify。1013 owned object為`exact`，`backfills=[]`，source／candidate
  全部canonical table count與stable fingerprints一致。
- Fresh：`lu_test_task96_ldu_fresh_1013_r1`只bootstrap到part 1013；target descriptor exact、data rows written 0。
- Strict evidence producer與qualification builder preview／atomic publish／validator round-trip皆`passed`。

## Runner correction

Explicit single-release manifest的1013 descriptor只擁有既有parent table上的CHECK，沒有owned table。舊snapshot
只對`descriptor.tables`執行`SHOW CREATE TABLE`，因而退回使用被錯誤解碼的中文
`information_schema.CHECK_CLAUSE`，把exact predecessor誤判為drift。Runner現在也把`descriptor.checks`的
parent table納入`SHOW CREATE TABLE`；focused static與builder suite為`86 passed`。

## DB gate table

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved historical pending-status package與`LDU-1003-CURRENT-01` |
| Change inventory | PASS | schema-only CHECK replacement；seed／backfill／destructive均none |
| Static release | PASS | 1013 manifest、hash、descriptor、assembly與atomic allowlist exact |
| Descriptor | PASS | predecessor absent、successor exact、其他expression drift；release-scoped真DB plan passed |
| Read-only plan | PASS | exact-1012 source→new 1013 candidate，status ready |
| Engine verification | PASS | preserve candidate、fresh bootstrap、strict evidence與published qualification passed |
| Developer acceptance | NOT_RUN | 另一台Windows主機尚未以自身`.env` configured DB執行升級與原workbook重驗 |

必要Developer acceptance仍為`NOT_RUN`，所以整體維持`DB_CHANGE_NOT_READY`。不得用本receipt宣稱另一台
主機已升級，也不得手動ALTER、reset、`--switch`或操作production DB。
