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
| canonical scenario涵蓋mutation/replay/stale/conflict/rollback | PASS（revision 2 metadata） |
| stale browser typed rejection與rollback零partial write | PASS |
| same-key browser replay未重複receipt | PASS |
| payload改變後清除receipt並停用Apply | PASS（pre-transport guard） |
| server-conflict 409 typed DOM | PASS（Chrome＋真FastAPI 409＋MySQL zero-partial readback） |
| true-TOTP browser | NOT_RUN_ACCEPTED_DEVELOPMENT_BYPASS（最新人工裁決） |

規格飄移已由`PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor`解除；
此metadata PASS本身不升格runtime；browser variants另有上述獨立真實證據。
