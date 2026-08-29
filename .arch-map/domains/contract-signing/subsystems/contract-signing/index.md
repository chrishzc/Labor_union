# Subsystem: contract-signing

## Parent
- domain: `contract-signing`

## Responsibility
提供 Contract Signing Query／Preview／Apply、external/manual signing session、immutable document/evidence、unsigned/final PDF workflow 與 owner-specific persistence/transport adapters。可在單一 outer UoW 內協調 typed owner ports，但不得自行成為 Scheduling commitment/execution、Orders lifecycle、Client Finance ledger 或 LINE delivery 的 SSOT。

## Dependencies
- outbound: `scheduling` — matching/commitment and execution owner facts/commands。
- outbound: `orders` — Contract Completion and contract identity owner command。
- outbound: `client-finance` — deposit/remaining obligation owner command。
- outbound: `external-integration/line` — verified reporter identity and durable delivery intent。
- outbound: `controlled_files` current source boundary — opaque staged/active PDF storage and readback。

## Contracts
- `domains/contract_signing/` — Contract Signing rules, including external-signing state transitions
- `subsystems/contract_signing/` — Contract Signing application contracts/workflows
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — canonical Contract Signing contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/contract-signing/subsystems/contract-signing/`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/`.
