---
doc_type: evidence-matrix-draft
declared_status: draft
identity: PROV-20260817-react-admin-reports-query-page-slice-evidence-matrix
date: 2026-08-17
owner: Reports React Page Integration Owner
not_a_receipt: true
---

# Reports Query Page-Slice Evidence Matrix（Draft）

本草案只記錄live shape與activation；不裁決未核准report fields，也不是contract freeze或實作授權。

## 1. Route matrix

| Surface | Live state | Required final state | UI disposition |
|---|---|---|---|
| quarterly GET | unauthenticated `BaseResponse[dict[str,Any]]`，移除`xlsx_bytes`後raw rows | `require_admin` + strict redacted quarterly view | blocked until authority |
| annual GET | unauthenticated `BaseResponse[dict[str,Any]]`，移除`xlsx_bytes`後raw rows | `require_admin` + strict redacted annual view | blocked until authority |
| quarterly export | binary GET | out-of-scope | native disabled |
| annual export | binary GET | out-of-scope | native disabled |
| weekly summary | 無approved typed query | 不在本包創建 | unavailable |
| weekly active/hours | 無approved typed query | 不在本包創建 | unavailable |

## 2. Candidate strict view（欄位仍受authority matrix約束）

| Field group | Required disposition |
|---|---|
| report period | application year、quarter nullable、period kind；server-owned |
| lineage | generated_at、source/version identity、correlation |
| partitions | general citizen／subsidized citizen rows與aggregates |
| case identity | 只有authority核准DISPLAY欄位；不得以live Chinese-key dict直通 |
| employer/staff | server-masked display或unavailable |
| identity card/address | default REDACTED／EXPORT_ONLY；完整值禁止JSON/DOM |
| dates/hours/days/rate/amount | server權威值；React 0公式推導 |
| aggregate | row counts／amount totals與partition conservation由server提供 |
| workbook bytes | 永不出現在query JSON |

任何欄位authority仍為`DECISION_REQUIRED`時不得加入Pydantic/Zod fixture；slot顯示unavailable。

## 3. ReportsPage slot disposition

| Existing slot | Disposition |
|---|---|
| 週報總表／案件受理 | unavailable；0 mock rows、0 GET |
| 補助經費明細 | quarterly／annual query，authority後wired |
| 每週服務中／工時 | unavailable；0 mock rows、0 GET |
| 四張KPI | 只用strict report aggregates；缺欄即unavailable |
| 完整3-sheet XLSX | native disabled |
| quarterly／annual XLSX | native disabled |

## 4. Required evidence

- auth deny path、strict response/error、PII absence、query 0 side effect。
- decoder missing/wrong/null/extra/PII leakage/aggregate mismatch negative tests。
- request budget、abort/stale、loading/empty/error/reload/deep-link。
- real browser只用既有DB做季度／年度GET Network→DOM；Happy DOM不能替代。
- AP hot-spot writer freeze與Reports writer activation不得重疊。

## 5. Forbidden substitutions

- 不以ReportsPage literals、live SQL、XLSX內容、historical receipt或HTTP 200裁決authority。
- 不將完整身份證、地址或其他EXPORT_ONLY欄位交給React再mask。
- 不為weekly或單一缺欄另拆gap；原位unavailable。
- 不呼叫任何export route，不建立DB或mutation。

Final matrix須在reporting authority decision完成後由Integration Owner重新凍結。
