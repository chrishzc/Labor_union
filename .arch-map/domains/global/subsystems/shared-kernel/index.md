# Subsystem: shared-kernel

## Parent
- domain: `global`

## Responsibility
提供不擁有業務根事實的純驗證、canonicalization 與 deterministic fingerprint primitives。

## Modules
- `numeric-and-fingerprint-contracts` — 共用數值精度驗證與 fingerprint canonicalization；path: `modules/numeric-and-fingerprint-contracts.md`
- `read-projection-cache` — 執行緒安全 TTL 唯讀投影快取、單飛防擊穿與選用本機 Redis 快取後端；path: `modules/read-projection-cache.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/global/subsystems/shared-kernel/`
