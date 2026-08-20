---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-anomalies-warning-mutation-gap
date: 2026-08-17
owner: Anomalies / Import Warning Integration Owner
domain: Anomalies / Case Import
---

# Phase 3D：Anomalies／Import Warning mutation 缺口

## 0. 缺口

Phase 2D只接兩個Query。現行Anomaly detail仍含raw `display_snapshot`、timeline與source bindings；Claim／Resolve
雖有route，Resolve只代表人工處置，不代表來源修復。Import Warning已有Preview／Apply transition，但尚未
與React state machine、owner recovery deep link及Phase 2D-H Closure Amendment的MySQL／affected-scope gate閉合。

因此目前不能啟用Claim、Resolve、warning transition或repair；存在route不等於cutover ready。

## 1. Successor必須拆分

1. Backend public-detail hardening：typed/redacted detail、timeline、available action/recovery contract；Phase 2D-H
   Closure Amendment的disposable MySQL與affected-scope regression先閉合，其他owner debt另行追蹤。
2. Import Warning React transition已拆成
   `PROV-20260817-react-admin-phase3d-w-r-warning-transition-react`；只接Preview→Apply→receipt→re-query。
   Claim／Resolve仍等待獨立policy/public-contract successor；owner repair只導向正式bounded workflow，不在
   Anomalies UI直接改root facts。

## 2. 不可破壞語意

- Resolve是operator acknowledgement/disposition，不是source repaired。
- root predicate仍active時必須可reopen/保持警示，不得顯示「修復完成」。
- warning transition與owner re-import/repair是不同command；不得合併假成功。
- 所有status/version/action由server typed result提供，UI不推導。

## 3. Close condition

只有後端detail/recovery contract、2D-H engine/affected-scope regression、React state machines、controlled browser與owner-specific
recovery都通過，才可解除mutation controls。本gap不授權production或DB變更。

## 4. DB gate

本gap無DB變更；Scope `PASS`，其餘`NOT_RUN`，結論`DB_CHANGE_NOT_READY`。
