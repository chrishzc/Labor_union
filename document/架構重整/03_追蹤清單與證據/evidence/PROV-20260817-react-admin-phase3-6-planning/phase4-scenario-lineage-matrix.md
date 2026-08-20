---
doc_type: evidence-inventory
declared_status: active
date: 2026-08-17
owner: React Migration Integration Owner
scope: Phase 4 scenario adoption and missing-artifact gates
authority: evidence-only
---

# Phase 4 Scenario Lineage Matrix

本表只記錄Phase 4工作包應採用的既有Scenario與仍缺少的React／browser／receipt artifacts；不把既有
scenario自動升格成新public contract，也不構成production、外部provider或資料庫操作授權。

## 1. Canonical rule

每個Phase 4工作包在production writer開始前，必須明確選擇`ADOPT`、`SUPPLEMENT`或
`TEST_DATA_GAP`。只有列出Scenario JSON並不算閉合；還必須能追到去敏fixture、expected oracle與
本次fresh receipt。缺少任一層時固定fail closed，不得由writer自造fixture後自行證明完成。

## 2. Lineage inventory

| Work Package family | Existing canonical scenario | Successor scenario ID / path | Disposition | Fixture / expected / receipt / checklist lineage | Activation blocker / shared hot spot |
|---|---|---|---|---|---|
| HCM Apply | `CI-CASE-IMPORT-001`、`CI-CANONICAL-ROOTS-002` | `ADOPT_IN_PLACE` / `validation/scenarios/CI-CASE-IMPORT-001.json` | `SUPPLEMENT` | fixture/expected存在；`CI-CASE-IMPORT-001` fresh receipt缺失；warning task、rollback／re-query與`validation/ui_business_workflows/part_01_import/checklist.md`仍缺 | workbook policy/archive/UoW；`DataImportPage.tsx` sole writer |
| BeClass／Staff Historical／Historical Orders | `CI-CASE-IMPORT-001`、`CI-CANONICAL-ROOTS-002` | `ADOPT_IN_PLACE` / `validation/scenarios/CI-CANONICAL-ROOTS-002.json` | `SUPPLEMENT` | 三個family各自補source identity、fixture/expected/receipt/replay oracle；canonical checklist為`part_01_import`，review另連`part_02_import_review` | workbook policy/archive/UoW；`DataImportPage.tsx`串行 |
| Finance Import | `FI-IMPORT-AND-RECONCILIATION-001`、`FI-CANONICAL-STAGING-003`、`FI-STAGING-DEDUP-002`、`FI-UI-PREVIEW-PARITY-003` | `ADOPT_IN_PLACE` / `validation/scenarios/FI-IMPORT-AND-RECONCILIATION-001.json` | `SUPPLEMENT` | fixture/expected存在；fresh receipt、durable terminal outcome與`part_07_finance_import/checklist.md`缺失 | Core＋Finance caller adoption＋Public Outcome；`DataImportPage.tsx`/`FinancePage.tsx` sole writer |
| Accounts Payable | `APX-PAYABLE-VIEWMODEL-002`、`APX-EXPORT-DATA-001` | `ADOPT_IN_PLACE` / `validation/scenarios/APX-PAYABLE-VIEWMODEL-002.json` | `SUPPLEMENT` | fixture/expected存在；fresh receipt及`part_11_staff_payables/checklist.md`authenticated browser download steps缺失 | AP public contract；`FinancePage.tsx`串行 |
| Client Finance | `CF-REFUND-RECOVERY-001`、`CF-EXPLICIT-REFUND-RECOVERY-002` | `ADOPT_IN_PLACE` / `validation/scenarios/CF-EXPLICIT-REFUND-RECOVERY-002.json` | `SUPPLEMENT` | fixture/expected存在；fresh receipt及`part_08_client_reconciliation/checklist.md` re-query DOM steps缺失 | Client Finance public contract；`FinancePage.tsx`串行 |
| Staff Payout | `SP-PAYABLE-QUERY-001`、`SP-EXACT-PAYOUT-STATE-002`、`JOB-DURABLE-001`、`JOB-QUEUE-LIFECYCLE-002` | `ADOPT_IN_PLACE` / `validation/scenarios/SP-EXACT-PAYOUT-STATE-002.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/staff_payout_durable_job.json`; `validation/expected/phase4/staff_payout_durable_job.json`; fresh receipt、Durable Public Outcome及`part_12_staff_payout/checklist.md`仍缺失 | Core＋Staff Payout caller adoption＋Public Outcome；`FinancePage.tsx`串行；fixture存在不解除runtime blocker |
| Government Subsidy report | `GS-CLAIM-FUNDING-001`、`GS-PLANNING-RECEIPT-FUNDING-002` | `ADOPT_IN_PLACE` / `validation/scenarios/GS-CLAIM-FUNDING-001.json` | `TEST_DATA_GAP` | authority未裁決；fresh receipt與`part_13_government_subsidy/checklist.md` masked browser oracle缺失 | authority decision＋report hardening；`ReportsPage.tsx` sole writer |
| LINE Delivery query | Part 00 P00-G54／P00-G56 | `LINE-REACT-DELIVERY-QUERY-001` / `validation/scenarios/react_admin_line_delivery_query.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/react_admin_line_delivery_query.json`; `validation/expected/phase4/react_admin_line_delivery_query.json`; receipt ID於`validation/receipts/phase4/manifest.json`; checklist owner=`validation/ui_business_workflows/part_15_documents/checklist.md` | Global Error＋Auth normalization＋Delivery query H/R；`LineManagementPage.tsx` sole writer |
| Knowledge catalogue query | Part 00 P00-G54／P00-G56、`KN-KNOWLEDGE-LIFECYCLE-001` | `KN-REACT-CATALOG-QUERY-001` / `validation/scenarios/react_admin_knowledge_catalog_query.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/react_admin_knowledge_catalog_query.json`; `validation/expected/phase4/react_admin_knowledge_catalog_query.json`; receipt ID於Phase4 manifest；checklist owner=`part_15_documents` | Global Error＋Auth normalization＋Knowledge query H/R；`LineManagementPage.tsx` sole writer |
| Knowledge lifecycle | `KN-KNOWLEDGE-LIFECYCLE-001` | `KN-REACT-LIFECYCLE-001` / `validation/scenarios/react_admin_knowledge_lifecycle.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/react_admin_knowledge_lifecycle.json`; `validation/expected/phase4/react_admin_knowledge_lifecycle.json`; receipt ID於Phase4 manifest；checklist owner=`part_15_documents` | Query hardening＋auth normalization＋Knowledge lifecycle H/R；multi-actor author-separation與receipt→re-query oracle；`LineManagementPage.tsx`串行 |
| Rich Menu publication | none | `LINE-RICH-MENU-PUBLICATION-001` / `validation/scenarios/react_admin_rich_menu_publication.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/react_admin_rich_menu_publication.json`; `validation/expected/phase4/react_admin_rich_menu_publication.json`; receipt ID於Phase4 manifest；checklist owner=`part_15_documents` | provider saga/step receipt backend未閉合；`LineManagementPage.tsx` sole writer；真provider禁止 |
| Notification Rules mutation | none | `LINE-NOTIFICATION-RULE-001` / `validation/scenarios/react_admin_notification_rule_mutation.json` | `TEST_DATA_GAP` | `validation/fixtures/phase4/react_admin_notification_rule_mutation.json`; `validation/expected/phase4/react_admin_notification_rule_mutation.json`; receipt ID於Phase4 manifest；checklist owner=`part_15_documents` | registered-source/kill-switch/replay contract未閉合；`LineManagementPage.tsx` sole writer |
| Durable Job public outcome | `JOB-DURABLE-001`、`JOB-QUEUE-LIFECYCLE-002` | `JOB-PUBLIC-OUTCOME-001` / `validation/scenarios/durable_job_public_outcome.json` | `SUPPLEMENT` | `validation/fixtures/phase4/durable_job_public_outcome.json`; `validation/expected/phase4/durable_job_public_outcome.json`; receipt ID於Phase4 manifest；無單一Part UI，`browser_checklist_path=null`、`browser_execution_mode=not_applicable` | Core＋caller integration bridge＋六caller adoption未PASS；各caller UI checklist回到其owning Part；Jobs public route為shared hot spot |

## 3. Mechanical gate

1. `ADOPT`或`SUPPLEMENT`必須驗證列出的既有`validation/scenarios/*.json`存在且可strict decode。
2. `TEST_DATA_GAP`不得啟動production writer；先由對應Work Package exact write set建立scenario、fixture、
   expected與receipt路徑，並由不同驗證者確認lineage。
3. browser receipt必須記錄scenario identity與去敏controlled-data identity，不接受僅截圖、writer mock或
   未說明來源的inline fixture。
4. 本表的路徑與狀態由唯一Integration Writer更新；各lane只交付精確delta。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 本文件僅作scenario inventory |
| Change Inventory | NOT_RUN | 0 DB write set |
| Static Release | NOT_RUN | 不適用 |
| Descriptor | NOT_RUN | 不適用 |
| Read-only Plan | NOT_RUN | 不適用 |
| Engine Verification | NOT_RUN | 不適用 |
| Developer Acceptance | NOT_RUN | 不適用 |

結論：`DB_CHANGE_NOT_READY`。
