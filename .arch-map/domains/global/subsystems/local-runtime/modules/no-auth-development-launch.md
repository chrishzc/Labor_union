# Module: no-auth-development-launch

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以明確 local-bypass profile 啟動 Vite source runtime，並排除 inherited immutable React artifact bindings，避免未完成 artifact configuration 阻止本機 no-auth 開發。

## Implementation
- primary: `scripts/launchers/start_local_development_no_auth.sh`
- Windows parity: `scripts/launchers/start_local_development_no_auth.bat`
- Windows configuration helper: `scripts/launchers/configure_local_admin_no_auth.ps1`
- delegated entrypoint: `scripts/launchers/start_local_development.sh`

## Contracts
- no-auth launchers 必須在委派前設定 development／local_bypass，設定 source runtime、provision 或 attest local entry-target state，並在缺少 `ANOMALY_ISSUE_IDENTITY_KEY_V1` 時以一次性 process-only 隨機值供 current-anomaly read-only query 使用；明確既有值必須保留且不得寫入 `.env`。`--dry-run` 不得 provision 或寫入 runtime state；`start_local_development.sh`／`.bat` 仍唯一擁有 DB current gate 與 child-process supervision。

## Verification
- test_root: `tests/domains/global/subsystems/local-runtime/modules/no-auth-development-launch/`

## Provenance
- wrapper exports、local state bootstrap、及 delegated current gate — `source_observed` — `scripts/launchers/start_local_development_no_auth.sh`、`scripts/launchers/start_local_development_no_auth.bat`、`scripts/launchers/start_local_development.sh`

## Change triggers
- Reconcile when local auth profile、React runtime selection、delegated launcher，或 startup readiness ownership changes.
