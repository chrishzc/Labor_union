# Module: runtime-supervision

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以單一 owned Windows supervisor 啟動並監督 FastAPI、React 與各背景 worker。Private API shared key 依序沿用明確 process value、本機 `.env` 現有值，僅兩者都缺少時產生當次臨時值，並由所有 child 共用；API ready 後先通過無副作用認證握手，才能啟動 worker。

## Implementation
- primary: `scripts/launchers/supervise_local_runtime.ps1`
- entrypoint: `scripts/launchers/start_local_development.bat`

## Contracts
- session key 不寫入 `.env`、不輸出，且不透過 command argument 傳遞。
- API readiness 不等於 Private API authentication readiness；認證握手失敗時 fail closed，不啟動任何 worker。
- supervisor 只清理本次建立且可重新驗證身分的 process tree。

## Verification
- test_root: `tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/`

## Provenance
- Windows entrypoint, process ownership and Private API client/auth boundary — `source_observed` — current launcher, supervisor and authenticated private runtime implementation.

## Change triggers
Reconcile when Windows startup ownership, child set, session-key lifecycle, Private API authentication readiness, or focused test root changes.
