# Subsystem: case-import

## Parent
- domain: `case-import`

## Responsibility
編排 typed source intake、validation、review、dedupe、Preview／Apply 與 bootstrap；來源不完整或 ambiguous 時 fail closed／review，不猜 owner roots。

## Modules
- `hcm-current-workbook-import` — HCM Current workbook Preview／Apply、既有案件 exact replay 與 reconciliation；path: `modules/hcm-current-workbook-import.md`
- `staff-historical-workbook-adoption` — 月嫂歷史 workbook Preview／Apply、review intake、idempotency 與 receipt；path: `modules/staff-historical-workbook-adoption.md`

## Dependencies
- outbound: `orders` — formal bootstrap。
- outbound: `anomalies` — review/projection evidence only。

## Contracts
- `domains/case_import/` — Case Import rules
- `subsystems/case_import/` — Case Import workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — idempotency/receipt/outbox

## Modules
- `pairing-current-facts` — `BECLASS-001` owner follow-up facts；`IMPORT-003`不再形成 anomaly recheck；path: `modules/pairing-current-facts.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/subsystems/case_import/`
- current owner-local HCM resubmission domain/workbook/workflow coverage is routed to this root.
- higher_boundary: tests/domains/case_import/
- layout_gap: `tests/test_wp77_import_contracts.py` remains a protected current legacy path with a direct current inventory consumer.
