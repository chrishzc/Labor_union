# Domain: global

## Responsibility
擁有跨 Domain shared contracts、migration／release、outer Unit of Work、receipt、
outbox 與 runtime governance；不擁有各 business Domain 的根事實或公式。

## Subsystems
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
