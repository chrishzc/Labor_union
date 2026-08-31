# Module: reconciliation-register-query

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
依Government Subsidy既有公式與服務完成日期產生季度、年度及bounded completion-period唯讀核銷rows；不接受Reporting重算補助單價、上限或root facts。

## Implementation
- primary:
  - `subsystems/government_subsidy/reconciliation_register_query.py`

## Dependencies
- inbound: `global/reporting/weekly-operations-report` — selected-week completion-period readback。
- outbound: Orders／Client／Staff current completed-case read facts。

## Contracts
- Government Subsidy reconciliation formula — `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- 營運週報selected-week補助契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/`
- higher-boundary consumer verification is owned by the Global Reporting weekly-operations-report Module.

## Provenance
- 補助row公式及completion date由Government Subsidy owner擁有 — `architecture_declared` — `14_Government_Subsidy_Domain.md`與current source。

## Change triggers
Reconcile whencompletion-period inclusion、subsidy formula、source roots或reporting contract改變。
