# Module: hcm-current-workbook-import

## Parent
- domain: `case-import`
- subsystem: `case-import`

## Responsibility
編排 HCM Current workbook 的 Preview／Apply、既有來源 exact replay、review 與 Case Import reconciliation；相同 canonical source 必須回原 receipt，不得由暫存上傳檔名改變 replay 判定。

## Implementation
- primary:
  - `subsystems/case_import/hcm_workbook_import.py`
  - `scripts/imports/import_client_hcm.py`
- entrypoints:
  - `api/routes/hcm_import.py`
  - `api/dependencies/hcm_import.py`

## Dependencies
- outbound: `orders` — HCM reconciliation 只透過 Case Import typed boundary 補入已授權 Orders facts。
- inbound: `case-import/case-import` — authenticated HCM workbook intake。

## Contracts
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — canonical payload exact replay 與 idempotency mismatch。
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — HCM Current workbook policy 與 Case Import ownership。

## Verification
- test_root: `tests/domains/case-import/subsystems/case-import/modules/hcm-current-workbook-import/`

## Provenance
- HCM Current workbook 與 Case Import ownership — `architecture_declared` — `17_External_Integration_LINE_Access正式規格.md`。
- implementation、entrypoint 與 replay flow — `source_observed` — current repository。

## Change triggers
Reconcile when HCM Current workbook contract、source fingerprint、replay/idempotency、entrypoint、reconciliation boundary 或 test root 改變。
