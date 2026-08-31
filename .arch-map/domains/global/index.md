# Domain: global

## Responsibility
擁有跨 Domain application shell、shared contracts、migration／release、outer Unit of Work、receipt、
outbox 與 runtime governance；不擁有各 business Domain 的根事實或公式。

## Subsystems
- `application-shell` — React navigation、session/auth composition與global recovery；path: `subsystems/application-shell/index.md`
- `reporting` — 跨Domain唯讀營運報表協調與typed presentation；path: `subsystems/reporting/index.md`
- `migration` — fresh bootstrap、preserve-data upgrade、release qualification 與
  cutover governance；path: `subsystems/migration/index.md`

## External relationships
- depended_by: `all domains` — schema／release 與跨域 mutation governance。

## Contracts
- Global migration／cutover contract —
  `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/global/`
- integration_root: `tests/domains/global/integration/`
