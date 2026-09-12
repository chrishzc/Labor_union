module: matching-coordination-presentation
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/matching-coordination.md
layout_status: custom_current
test_root: ui_react/src/tests/matching_coordination_workbench.test.tsx
integration_root: `ui_react/src/tests/matching_candidate_workflow_client.test.ts`

# Owned verification
- `matching_coordination_workbench.test.tsx` — 保護既有十七種媒合操作、零候選與安全重試 oracle，以及業務主畫面與預設收合的技術 contract 資料。
- `matching_candidate_workflow_client.test.ts` — 驗證媒合方案建立與原操作結果查詢的 typed client，以及案件、操作者、日期與分段身份核對。
