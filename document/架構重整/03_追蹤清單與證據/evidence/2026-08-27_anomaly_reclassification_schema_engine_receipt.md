# Anomaly reclassification schema engine receipt

- Evidence status：`current`（R11 final R9.1 artifact）
- Date：2026-08-27
- Work Package：`PROV-20260827-anomaly-necessity-migration-work-package.md`／`ANM-NM-A`
- Scope：schema part `1009_anomaly_reclassification_disposition.sql`、release
  `labor-union-anomaly-reclassification-disposition-2026-08-27-v1`
- Safety boundary：只使用 `lu_test_*`；未執行 `--switch`、未操作 `union_db`、未執行production migration。

## Gate results

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved ANM-NM-A write set涵蓋append-only disposition／receipt／batch receipt。 |
| Change inventory | PASS | schema-only 3 tables；system-seed、business-row-backfill、destructive均無。 |
| Static release | PASS | fresh assembly共136 parts，validation release v15 terminal part為1009；manifest validator與release build `--check`通過。 |
| Descriptor | PASS | R11 fresh真MySQL readback：三表欄位數22／20／11、6 immutable triggers，owned object=`exact`；preserve-data candidate再次讀回`exact`。 |
| Read-only plan | PASS | R11 preserve-data plan列1009 `absent`；artifact SHA-256=`d4c50cafdfeef450ab707707f6b5702582a71eb5adbaaaf1cc2434bc11ff77d5`，plan fingerprint=`2e5fec42f11e9385e5021b2324428e960256caacd4ad4bd435917b11c1fca331`。 |
| Engine verification | PASS | R11 fresh bootstrap成功；receipt-backed source→candidate Apply後1009為`exact`，Verify status=`verified`、view mismatches=0、backfills=[]。 |
| Developer acceptance | NOT_RUN | 未做local replacement、`--switch`或rollback演練。 |

總結：`DB_CHANGE_NOT_READY`，原因僅為Developer acceptance仍`NOT_RUN`；這不否定已完成的隔離engine evidence。

## Preservation evidence

- source：`lu_test_task96_fin_rules_r4_20260827`
- candidate：`lu_test_task96_anm_nm_a_r11_candidate_20260827`
- source dump：1,151,952 bytes，SHA-256
  `eff24cc2469d916ff6e5d0ce37109aa8add599d59f108f1eb9a03c3bf035891a`；dump command包含release要求的`--events`。
- `anomaly_current_alerts`：source/candidate皆3 rows，checksum與primary-key fingerprint相同。
- `staff_overpayment_recoveries`：source/candidate皆1 row，checksum與primary-key fingerprint相同。
- 新增三表在schema qualification時皆為0 rows，證明release沒有夾帶business row backfill。
- 原始plan／operation／backup receipts保存在ignored
  `scratch/task96-anm-nm-a-r11/`，其中operation receipt最終status=`verified`。
