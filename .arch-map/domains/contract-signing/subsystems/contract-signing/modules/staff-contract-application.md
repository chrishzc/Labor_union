# Module: staff-contract-application

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
執行月嫂契約送出、簽回與人工簽約前承諾 application workflow；不建立 Scheduling execution assignment 或取代 Orders／Client Finance owner。

## Implementation
- primary:
  - `subsystems/contract_signing/staff_contract_application.py`

## Dependencies
- outbound: `orders` — Contract Completion／contract identity typed owner command。
- outbound: `client-finance` — precontract deposit／terms impact owner adapter。
- outbound: `scheduling` — matching segment／commitment facts。
- outbound: `external-integration/line` — verified recipient and delivery task transport。

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — staff contract and precontract commitment boundary。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_staff_contract_signing_application.py`

## Provenance
- Staff contract application ownership — `architecture_declared` — Contract Signing subsystem contract and current source。
- Application implementation/test path — `source_observed` — current repository。

## Change triggers
Reconcile when staff contract command／receipt、commitment handoff、document lineage or test location changes。
