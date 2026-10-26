# Module: staff-contract-application

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
執行月嫂契約送出、簽回與人工簽約前承諾 application workflow；不建立 Scheduling execution assignment 或取代 Orders／Client Finance owner。

簽約前承諾服務日沿用「無休／未選休假星期為連續服務」的正式裁決；非空且無法辨識的服務方式仍拒絕，不將未知資料當成連續服務。

## Implementation
- primary:
  - `subsystems/contract_signing/staff_contract_application.py`
- composition: `api/dependencies/contract_signing.py`

## Dependencies
- outbound: `orders` — Contract Completion／contract identity typed owner command。
- outbound: `client-finance` — 契約使用 owner 金額投影；簽回只保存 commitment，不再建立訂金或期款。
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
