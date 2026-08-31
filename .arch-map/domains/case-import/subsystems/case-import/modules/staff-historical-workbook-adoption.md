# Module: staff-historical-workbook-adoption

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
編排月嫂歷史 workbook 的唯讀 Preview、fresh Apply、逐列採納／人工檢查、idempotency claim 與 terminal receipt；來源列不旁路 Case Import review contract。

## Implementation
- primary:
  - `subsystems/case_import/staff_historical_workbook_adoption.py`
  - `subsystems/case_import/staff_historical_workbook.py`
  - `infrastructure/mysql/staff_historical_workbook_repository.py`
  - `infrastructure/mysql/staff_historical_adoption_repository.py`
- entrypoints:
  - `api/routes/staff_historical_workbook.py`
  - `api/dependencies/staff_historical_workbook.py`
  - `api/schemas/staff_historical_workbook.py`

## Dependencies
- outbound: `case-import/case-import` — invalid or conflicting source rows enter the owned BeClass review intake contract.

## Contracts
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` — current Case Import decisions.
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Preview／Apply、idempotency 與 receipt contract.

## Verification
- layout_status: `current`
- test_root: `tests/domains/case-import/subsystems/case-import/modules/staff-historical-workbook-adoption/`

## Provenance
- Case Import ownership and review boundary — `architecture_declared` — Case Import Domain／Subsystem indexes and current specifications.
- implementation and API paths — `source_observed` — current repository.
- owner-local regression root — `source_observed` — current repository test layout convention.

## Change triggers
Reconcile when workbook parsing, review intake translation, adoption persistence, API entrypoint, idempotency／receipt behavior or owner-local test root changes.
