# Subsystem: runtime-governance

## Parent

- domain: `global`

## Responsibility

擁有 runtime observability、versioned operational-retention registry、capacity Query、
automatic age／pressure cleanup、Manual Preview／Apply、aggregate cleanup evidence 與
reconciliation orchestration。各資料 Domain／Subsystem 只提供 typed source adapter；不得自行
放寬 allowlist、刪除跨 owner evidence 或成為第二個 cleanup commit owner。

## Modules

- `operational-retention` — 30-day／capacity policy、storage-management surface and bounded cleanup；path:
  `modules/operational-retention.md`

## Contracts

- `document/架構重整/01_規格基線/18_Global_Deployment與治理正式規格.md` §7.1、§9、§10

## Verification routing

- default_boundary: Subsystem
- module_verification: `modules/operational-retention.md`
- current_implementation: `WP-GOV-RETENTION-001 repository implementation present; production enablement remains target-authorized operations work`

## Change triggers

Reconcile when retention owner、registry contract、age／capacity semantics、Query／Preview／Apply
surface、cleanup UoW／reconciliation、worker boundary or canonical test root changes.
