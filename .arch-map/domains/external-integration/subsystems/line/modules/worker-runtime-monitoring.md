# Module: worker-runtime-monitoring

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
協調 canonical LINE worker 的單次工作週期與等待迴圈，並將成功或失敗 heartbeat 投影為可辨識的 runtime health observation。週期失敗必須留下錯誤類型後再向 caller 傳播；監控分開判斷 heartbeat 過期與最新週期失敗，不執行 provider effect 或改寫 delivery outcome。

## Implementation
- primary:
  - `subsystems/line/worker_runtime.py`
  - `subsystems/line/webhook_event_consumer.py` — 逐事件業務提交／失敗隔離；只在 commit 後將本次新建的資訊回覆 ID 交由既有 delivery worker 快速投遞，投遞失敗不得重試已提交業務。
  - `subsystems/line/runtime_monitoring_application.py`
  - `subsystems/line/runtime_alert_application.py` — heartbeat／health observation 持久化與 RuntimeLineAlertProjector；2026-10-30 全部管理員告警退役後只保留監測與事件，projector 不產生 delivery intent／task。
- primary: `subsystems/line/runtime_status_query.py` — 給已驗證管理員 LIFF 的唯讀去敏摘要、既有 freshness 與未知狀態；不探測外部服務或寫入。
- persistence adapter: `infrastructure/mysql/runtime_monitor_repository.py`
- Production media capacity observations read the configured shared NAS root; missing configuration is unknown, never a healthy local fallback. Development observations retain their existing MEDIA_STORAGE_ROOT.
- 狀態摘要與佇列計數只使用既有監測／delivery 資料表，計數排除已退役管理員告警；不依賴個別偏好表，不吞掉必要資料表的權限／缺表錯誤。

## Contracts
- `subsystems/line/runtime_contracts.py::LineWorkerHeartbeat` — success／failure heartbeat typed fact。
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — canonical worker 與 committed delivery boundary。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/worker-runtime-monitoring/`

## Change triggers
Reconcile when worker cycle／wait error handling、heartbeat freshness or failure meaning、runtime health threshold，或 focused test root 改變。
