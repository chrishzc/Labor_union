# Module: worker-runtime-monitoring

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
協調 canonical LINE worker 的單次工作週期與等待迴圈，並將成功或失敗 heartbeat 投影為可辨識的 runtime health observation。週期失敗必須留下錯誤類型後再向 caller 傳播；監控分開判斷 heartbeat 過期與最新週期失敗，不執行 provider effect 或改寫 delivery outcome。

## Implementation
- primary:
  - `subsystems/line/worker_runtime.py`
  - `subsystems/line/runtime_monitoring_application.py`

## Contracts
- `subsystems/line/runtime_contracts.py::LineWorkerHeartbeat` — success／failure heartbeat typed fact。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — canonical worker 與 committed delivery boundary。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/worker-runtime-monitoring/`

## Change triggers
Reconcile when worker cycle／wait error handling、heartbeat freshness or failure meaning、runtime health threshold，或 focused test root 改變。
