# Module: no-auth-development-launch

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以明確 local-bypass profile 啟動 Vite source runtime，並排除 inherited immutable React artifact bindings，避免未完成 artifact configuration 阻止本機 no-auth 開發。

## Implementation
- primary: `scripts/launchers/start_local_development_no_auth.sh`
- delegated entrypoint: `scripts/launchers/start_local_development.sh`

## Contracts
- no-auth launcher 必須在委派前設定 development／local_bypass，並以 source runtime 啟動；`start_local_development.sh` 仍唯一擁有 DB current gate 與 child-process supervision。

## Verification
- test_root: `tests/domains/global/subsystems/local-runtime/modules/no-auth-development-launch/`

## Provenance
- wrapper exports及 delegated current gate — `source_observed` — `scripts/launchers/start_local_development_no_auth.sh`、`scripts/launchers/start_local_development.sh`

## Change triggers
- Reconcile when local auth profile、React runtime selection、delegated launcher，或 startup readiness ownership changes.
