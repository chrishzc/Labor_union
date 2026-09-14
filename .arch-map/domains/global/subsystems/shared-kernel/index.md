# Subsystem: shared-kernel

## Parent
- domain: `global`

## Responsibility
提供不擁有業務根事實的純驗證、canonicalization 與 deterministic fingerprint primitives。

## Modules
- `numeric-and-fingerprint-contracts` — 共用數值精度驗證與 fingerprint canonicalization；path: `modules/numeric-and-fingerprint-contracts.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/global/subsystems/shared-kernel/`
