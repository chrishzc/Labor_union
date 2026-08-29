# Subsystem: payroll

## Parent
- domain: `payroll`

## Responsibility
編排 payroll obligations 的 Query／Preview／Apply、rebuild 與調整，僅消費 Scheduling-owned facts，不反向重算 assignment。

## Dependencies
- outbound: `scheduling` — 讀取正式 assignment/service facts。

## Contracts
- `domains/payroll/` — Payroll rules
- `subsystems/payroll/` — Payroll workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/subsystems/payroll/`
- integration_root: unknown (`layout_gap`; no domain-specific higher root observed).
