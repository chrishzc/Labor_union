# Subsystem: case-import

## Parent
- domain: `case-import`

## Responsibility
編排 typed source intake、validation、review、dedupe、Preview／Apply 與 bootstrap；來源不完整或 ambiguous 時 fail closed／review，不猜 owner roots。

## Dependencies
- outbound: `orders` — formal bootstrap。
- outbound: `anomalies` — review/projection evidence only。

## Contracts
- `domains/case_import/` — Case Import rules
- `subsystems/case_import/` — Case Import workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — idempotency/receipt/outbox

## Modules
- `pairing-current-facts` — `BECLASS-001/IMPORT-003` exact pairing readback與bounded recheck；path: `modules/pairing-current-facts.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/subsystems/case_import/`
- current owner-local HCM resubmission domain/workbook/workflow coverage is routed to this root.
- higher_boundary: `tests/domains/case_import/`
- layout_gap: `tests/test_wp77_import_contracts.py` remains a protected current legacy path with a direct current inventory consumer.
