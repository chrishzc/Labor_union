---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260816-react-admin-phase4a-hcm-backend-transaction-receipt-gap
date: 2026-08-16
owner: Case Import / Global Transaction Governance
domain: Case Import / Anomalies
subsystem: HCM Workbook Apply / Warning Disposition / Receipt Observation
successor_proposal: PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract
---

# Phase 4A-H：HCM Apply transaction／warning／receipt public contract 缺口

## 0. Blocked scenario

React HCM Current Workbook Apply 可能建立正式／partial case、warning/review evidence 與 receipt。現行
流程不能同時證明 workbook command 的唯一 outer UoW、完整 typed error、warning disposition 可操作及
receipt observation，因此 Phase 4A-P 只開 Preview；Apply 原位鎖定。

Exact backend-first successor與尚待人工裁決的source archive政策已分別提出於
`PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract-work-package.md`及
`PROV-20260817-hcm-workbook-source-archive-decision-gap.md`；兩者均不構成既有Apply授權。

## 1. 已證明 live-drift

1. `HcmWorkbookImportRepository.claim()` 與 `save_receipt()` 各自 commit；row intake 又逐列開
   `CaseImportMySqlUnitOfWork`，不是一個 workbook outer UoW。
2. route errors 主要只有 `detail.code`，缺 Global category/message/correlation/retryable/blockers。
3. Preview 未保存 correlation lineage。
4. 沒有 typed receipt lookup；Apply receipt 也未完整帶 preview fingerprint observation lineage。
5. aggregate Preview 無逐列 typed warning/review descriptor；UI 不得生成假 rows。
6. Phase 3D warning transition／repair navigation 仍未閉合，違反主計畫 Phase 4 Apply 前置門。
7. IP＋姓名唯一命中既有 Client 的 live warning 行為，與正式「停止並人工確認」裁決可能漂移。
8. temp cleanup OSError 可能覆蓋已提交結果，需獨立 operational outcome policy。

## 2. Successor 必須先裁決

- workbook atomicity：整批單 UoW，或正式接受 row-bounded transactions＋可恢復 aggregate coordinator；
- claim／resume／terminal receipt invariant、partial failure conservation、replay/conflict；
- source archive port 是否 required；
- duplicate identity blocker；
- typed error與Preview correlation；
- authenticated receipt lookup/re-query；
- warning task Query＋Preview/Apply disposition與recovery deep link；
- cleanup failure不偽造Domain failure。

## 3. Candidate write set（未授權）

`api/routes/hcm_import.py`、`api/schemas/hcm_import.py`、`subsystems/case_import/hcm_workbook_import.py`、
`infrastructure/mysql/hcm_workbook_import_repository.py`、必要 typed intake port／tests，以及對應 React Apply
client/store/page tests。若涉及 DB/schema/shared handler，必須另開 exact Work Package 並執行 DB gates。

## 4. Close condition

只有 successor exact Work Package 經人工確認，backend route/workflow/repository/disposable MySQL/React
state machine/controlled warning scenario/receipt observation 全部驗證後，才能解除
`imports.hcm-current.apply`。本 gap 不構成 production mutation 授權。
