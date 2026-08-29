# Domain: contract-signing

## Responsibility
擁有核准模板引用、不可變契約文件版本、月嫂／客戶 signed-received evidence、provider-neutral external-signing session/status、Contract Signing command receipt 與 final signed document lineage/readback。不得把契約文件或簽回 evidence 當成 Orders lifecycle、Client Finance ledger、Scheduling execution／commitment 或 LINE delivery 的 owner fact。

## Subsystems
- `contract-signing` — Contract Signing Query／Preview／Apply、manual/external signing、unsigned/final PDF 與 owner-specific adapters；path: `subsystems/contract-signing/index.md`

## External relationships
- depends_on: `scheduling` — matching plan/segment 與 precontract commitment/execution ownership。
- outbound: `orders` — Contract Completion／`contract_identity` mutation 以 typed owner command 完成。
- outbound: `client-finance` — precontract deposit／remaining obligation mutation 由 Client Finance owner 處理。
- depends_on: `external-integration` — LINE verified identity、delivery task／attempt transport；delivery success 不代表簽署完成。
- depends_on: `controlled_files` current source boundary — staged/immutable PDF bytes 與 opaque file identity；該 source boundary 尚未獨立建模成 Domain。

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — Contract Signing ownership、state machine、Q/P/A、transaction 與 evidence contract
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global mutation、receipt、outbox、idempotency contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/contract-signing/`
- integration_root: `tests/domains/contract-signing/subsystems/contract-signing/integration/`; see Test Map.
