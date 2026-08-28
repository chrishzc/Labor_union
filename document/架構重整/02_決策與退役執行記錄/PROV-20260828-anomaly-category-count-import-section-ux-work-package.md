# 異常分類數量與匯入待辦區隔任務包

- `package_id`: `PKG-ANOMALY-CATEGORY-COUNT-IMPORT-SEPARATION`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `specification`: `PROV-20260828-anomaly-category-count-import-section-ux-spec.md`
- `owner`: Anomalies React
- `dependencies`: 無；但不與目前 H/R writer 共用 write paths。
- `write_set`: `ui_react/src/adapters/anomalies/anomaly_query_adapter.ts`、
  `ui_react/src/pages/AnomaliesPage.tsx`、專用 focused tests。
- `exclusions`: API/DB/Domain/schema、異常狀態變更、generic resolve、UI 全域風格整併。
- `steps`: shared predicate/count helper → tabs count → import section conditional render → focused regression → no-auth Browser。
- `safe_stop`: typed source 未載入時不假造數量；分類/status predicate 不一致時不驗收。
- `verification`: adapter unit → AnomaliesPage React → build → no-auth Browser。

```yaml
package_status: PACKAGE_READY
blockers: []
```
