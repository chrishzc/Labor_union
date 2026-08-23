---
doc_type: work-package
identity: PROV-20260820-react-admin-matching-recommendation-query-transport-hardening
declared_status: completed
date: 2026-08-20
owner: Integration Owner
domain: Scheduling
subsystem: matching-recommendation-query
approval_evidence: 使用者要求優先完成非LINE模組遷移並確保可正常使用；本包只修既有GET的current-schema讀取與輸入邊界
database_change: none
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260820-react-admin-matching-recommendation-query-transport-hardening/
---

# React Admin Matching Recommendation Query Transport Hardening Work Package

## Business scenario

管理員在配對工作流查詢既有案件的月嫂推薦清單；不存在案件應回空清單，超過canonical 50字元的
`case_no`應在transport邊界回422，任何一者都不得因live schema drift形成HTTP 500。

## Architecture and invariants

- Global：FastAPI Query validation只接受1–50字元案件編號；typed internal error仍遮罩例外內容。
- Domain：不修改推薦排序、區域、排班、胎數或時段規則。
- Subsystem：`query_matching_recommendations`維持唯讀，missing case回空清單。
- Adapter：repository以current `orders.start_date/end_date`讀取根事實，alias成既有application fact names；不修改DB。
- Module：Hurl只執行GET，驗證missing case 200及oversized input 422。

## Exact write set

- `api/routes/matches.py`
- `infrastructure/mysql/matching_recommendation_repository.py`
- `tests/hurl/matching_recommend_staff.hurl`
- 本工作包與對應evidence／index delta

## Out of scope

- React按鈕或版面改造、正式Matching Plan mutation、LINE通知、provider action。
- 推薦公式或candidate ranking裁決。
- schema、migration、seed、backfill、既有DB mutation。
- Phase5 entry switch、Phase6 retirement。

## Acceptance

1. 51字元`case_no`在進入repository前回422。
2. 不存在且長度合法的案件回200、`success=true`、`data=[]`。
3. current schema查詢不引用不存在的`planned_start_date/planned_end_date`欄位。
4. Focused Hurl兩個GET通過，0 non-GET；owned API process完成後精確清理。
5. `git diff --check`與strict UTF-8／no-BOM通過。

## Completion

2026-08-20 completed：Schemathesis先發現500，focused Hurl重現兩個根因；transport boundary與repository
current-schema alias修正後，正式Hurl 1 file／2 GET PASS。這不代表React Matching UI、正式方案或entry cutover完成。

## DB gates

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | exact GET-only hardening；0 DB write set |
| Change inventory | PASS | schema-only=0、system-seed=0、business-row-backfill=0、destructive=0 |
| Static release | NOT_RUN | no DB release |
| Descriptor | NOT_RUN | no DB object |
| Read-only plan | NOT_RUN | no migration |
| Engine verification | NOT_RUN | no DB change；existing DB only through GET |
| Developer acceptance | NOT_RUN | existing DB untouched |

Conclusion：`DB_CHANGE_NOT_READY`。
