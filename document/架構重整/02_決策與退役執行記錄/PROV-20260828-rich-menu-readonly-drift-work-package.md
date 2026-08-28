# Rich Menu processing／published readonly drift 工作包

- `package_id`: `PROV-20260828-rich-menu-readonly-drift-package`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `controlling_spec`: `PROV-20260828-rich-menu-readonly-drift-spec.md`
- `requirements`: `RM-RO-A1`～`RM-RO-A5`
- `effect_ceiling`: development／`lu_test_*`；fixture/test artifact mutation與Browser唯讀驗收

## Ordered work

1. 校正 React／validation fixtures，使 publication row、exact revision 與 lock state 一致。
2. 增補 application／route／React tests：processing、published、published precedence、old revision、
   malformed projection與readonly controls。
3. 只在已有合法 processing／published lineage時，以 no-auth Browser驗證狀態、reason、controls、network
   與 console；缺 lineage 即安全停止。
4. 保存最小去敏 receipt並同步 `CUR-LINE-RICHMENU-01`；不得把 provider publication或formal auth列為本包成果。

## Coverage 與 safe stop

| Acceptance | Oracle |
|---|---|
| A1 | application／route exact-lock focused tests |
| A2 | schema＋React reason/control assertions |
| A3 | fixture consistency＋malformed projection tests |
| A4 | 真 no-auth Browser network／console receipt |
| A5 | lineage inventory與 `blocked/not_run` receipt |

下列任一成立立即停止：target非development `lu_test_*`；publication無合法lineage；需provider token／formal
login；出現provider request、publication queue或非預期DB mutation；readonly reason缺失或locked snapshot仍有
mutation controls。

## DB change gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | `PASS` | current item＋controlling spec |
| Change inventory | `PASS` | schema/seed/backfill/destructive均none |
| Static release | `NOT_RUN` | 無DB artifact變更 |
| Descriptor | `NOT_RUN` | 無owned object變更 |
| Read-only plan | `NOT_RUN` | 無migration |
| Engine verification | `NOT_RUN` | 非schema lane |
| Developer acceptance | `NOT_RUN` | 不執行replacement／switch |

Package status：`PACKAGE_READY`。
