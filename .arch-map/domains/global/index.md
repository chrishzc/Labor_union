# Domain: global

## Responsibility
擁有跨 Domain application shell、shared contracts、migration／release、outer Unit of Work、receipt、
outbox 與 runtime governance；不擁有各 business Domain 的根事實或公式。

## Subsystems
- `application-shell` — React navigation、session/auth composition與global recovery；path: `subsystems/application-shell/index.md`
- `local-runtime` — 本機開發 runtime 與 no-auth source-runtime entry；path: `subsystems/local-runtime/index.md`
- `reporting` — 跨Domain營運報表Query／export、typed presentation與現行週報批次寫入；規格差異見Module；path: `subsystems/reporting/index.md`
- `migration` — fresh bootstrap、preserve-data upgrade、release qualification 與
  cutover governance；path: `subsystems/migration/index.md`
- `controlled-files` — cross-domain controlled storage API composition and opaque
  file readback boundary；path: `subsystems/controlled-files/index.md`
- `runtime-governance` — runtime observability、technical／operational retention、capacity
  policy 與 bounded maintenance ownership；path: `subsystems/runtime-governance/index.md`

## External relationships
- depended_by: `all domains` — schema／release 與跨域 mutation governance。

## Contracts
- Global migration／cutover contract —
  `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- Global deployment／operational retention contract —
  `document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/global/`
- integration_root: `tests/domains/global/integration/`
