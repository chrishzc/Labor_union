---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3d-claim-resolve-preview-policy-gap
date: 2026-08-17
owner: Anomalies / Global Contract Governance
domain: Anomalies
source_gap: PROV-20260817-react-admin-phase3d-anomalies-warning-mutation-gap
---

# Phase 3D：Claim／Resolve Preview policy矛盾

## Contradiction

Global共同契約規定人工處理異常須遵守Preview／Confirm／Apply；Anomalies Domain commands則列
`ClaimAnomaly`與`ResolveAnomalyWorkflow`直接短交易，live HTTP也只有`POST /claim`、`POST /resolve`，
沒有Preview/fingerprint/idempotency contract。

兩者不能由React implementation自行選擇。直接接現有POST可能違反Global；臨時新增Preview則會改public
interface與正式Domain commands。

## Human decision required

- Option A：明確裁決claim/resolve是只更新workflow待辦的短交易例外；仍要求expected version、reason、
  correlation、single-flight、receipt與re-query，但不需要Preview fingerprint/idempotency。
- Option B：新增Claim/Resolve Preview→Apply public contract、fingerprint/idempotency與receipt lookup，並同步
  修正式Anomalies規格。

無論哪個選項，Resolve只表示人工處置，不代表source repaired；predicate仍在時必須reopen。

未裁決前`anomalies.card.claim`與`anomalies.drawer.resolve`維持native disabled。本gap不授權production／DB變更。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
