# Subsystem: government-subsidy

## Parent
- domain: `government-subsidy`

## Responsibility
編排整期補助 Query／Apply、涵蓋與沖正；月／季／年共用服務結束月份及案件公式。政府申請／核准在系統外，代墊回收依同一期實付 ledger 彙總。

## Dependencies
- inbound: `finance-import` — typed owner delegation only。

## Contracts
- `domains/government_subsidy/` — Subsidy rules
- `subsystems/government_subsidy/` — Subsidy workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Modules
- `period-reconciliation` — 整期銀行核銷、跨單位涵蓋與移期防重；path: `modules/period-reconciliation.md`
- `overpayment-recovery-presentation` — GOVSUB-006既有處置workflow的business-first React projection; path: `modules/overpayment-recovery-presentation.md`
- `current-anomaly-facts` — retired GOVSUB anomaly validation／migration readback only；path: `modules/current-anomaly-facts.md`
- `reconciliation-register-query` — 依服務完成期間產生owner-calculated補助核銷rows；path: `modules/reconciliation-register-query.md`
- `anomaly-owner-remediation` — GOVSUB correctness／owner correction evidence；不形成 runtime Anomalies current issue；path: `modules/anomaly-owner-remediation.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/`
- integration_root: `tests/domains/government-subsidy/subsystems/government-subsidy/integration/`
- retired GOVSUB anomaly correctness 留在 Government Subsidy owner validation／reconciliation／migration evidence；不回指 Anomalies consumer tests。
- routing: `.arch-map/tests/domains/government-subsidy/subsystems/government-subsidy/index.md`.
