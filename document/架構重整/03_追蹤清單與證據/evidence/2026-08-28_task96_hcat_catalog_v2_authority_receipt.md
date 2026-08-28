# Task 96 HCAT catalog-v2 authority receipt

- 日期：2026-08-28
- 人工裁決：`核准 catalog-v2`
- Current effect：解除 HCAT concrete owner adapters／HPROJ projector 的
  `BLOCKED_AUTHORITY`，spec §9 與 task pack §8 分別回到 `SPEC_READY`／`PACKAGE_READY`。

## 採用範圍

- 同一步可有多個 owner descriptor，每個 descriptor 可有一或多筆 typed observation。
- 每筆保留 root identity、source event identity、source version；whole-vector fingerprint涵蓋完整集合。
- owner adapter先驗單筆，descriptor collection predicate再驗 cardinality／all-required。
- Step 3／5／9 owner map與Step 6／8／10／11多筆 observation依current spec §9執行。
- referral由owner回傳typed target/capability，不使用全域placeholder。

## 不授權事項

- 不新增DDL、backfill、production／provider effect或generic anomaly resolve。
- 1011是否足夠先由static contract驗證；不足時另立DB change package，不直接修改release。
- v1 persisted baseline history保持immutable，只讓新的projector intent使用catalog-v2。

```yaml
spec_status: SPEC_READY
package_status: PACKAGE_READY
blockers: []
```
