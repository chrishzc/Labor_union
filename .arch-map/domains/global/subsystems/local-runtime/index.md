# Subsystem: local-runtime

## Parent
- domain: `global`

## Responsibility
提供本機開發 runtime 的受控啟動組成；隔離 no-auth source runtime 與 immutable artifact runtime，並委派 canonical schema current gate。

## Modules
- `no-auth-development-launch` — 本機免登入 source-runtime wrapper；path: `modules/no-auth-development-launch.md`
- `runtime-supervision` — Windows 標準啟動、owned child supervision 與 Private API 認證 readiness；path: `modules/runtime-supervision.md`

## Dependencies
- outbound: `global/migration` — canonical start entry 在啟動 children 前驗證 current schema。

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/global/subsystems/local-runtime/`
- integration_root: `tests/domains/global/subsystems/local-runtime/integration/`
