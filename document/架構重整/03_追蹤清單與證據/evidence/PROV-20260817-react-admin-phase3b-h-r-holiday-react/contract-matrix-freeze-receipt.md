# Phase 3B-H-R contract matrix freeze receipt

日期：2026-08-22

| Contract | Result |
|---|---|
| Query success payload strict decode、unknown extra fail closed | PASS |
| Preview request包含action/date/name/horizon；結果採server version/fingerprint/impacts | PASS |
| Apply包含reason、expected version、fingerprint；pending時native disabled | PASS |
| timeout/503 outcome_unknown只能以相同payload/idempotency key retry | PASS（adapter focused） |
| receipt後re-query，只有observed顯示完成，receipt不被re-query清除 | PASS（focused＋Chrome） |
| UI不推導double pay／coverage／eligibility／日期結果 | PASS |
| 其他Holiday controls維持native disabled，無alert/confirm/prompt | PASS |
| canonical scenario涵蓋mutation/replay/stale/conflict/rollback | BLOCKED（revision 1仍為query-only） |

規格飄移由`PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor`承接。
