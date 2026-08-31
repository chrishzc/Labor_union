# Subsystem: government-subsidy

## Parent
- domain: `government-subsidy`

## Responsibility
編排 subsidy Query／Preview／Apply、allocation/reversal 與 owner receipts，拒絕由 generic finance importer 直接改寫 domain roots。

## Dependencies
- inbound: `finance-import` — typed owner delegation only。

## Contracts
- `domains/government_subsidy/` — Subsidy rules
- `subsystems/government_subsidy/` — Subsidy workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Modules
- `overpayment-recovery-presentation` — GOVSUB-006既有處置workflow的business-first React projection; path: `modules/overpayment-recovery-presentation.md`
- `current-anomaly-facts` — `GOVSUB-001/002/004` owner current-fact readback與bounded recheck request；path: `modules/current-anomaly-facts.md`
- `reconciliation-register-query` — 依服務完成期間產生owner-calculated補助核銷rows；path: `modules/reconciliation-register-query.md`
- `anomaly-owner-remediation` — GOVSUB-003/005/007 typed owner facts與已核准修正路徑；path: `modules/anomaly-owner-remediation.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/`
- integration_root: `tests/domains/government-subsidy/subsystems/government-subsidy/integration/`
- anomaly-focused subsidy projections remain under `tests/domains/anomalies/`.
- routing: `.arch-map/tests/domains/government-subsidy/subsystems/government-subsidy/index.md`.
