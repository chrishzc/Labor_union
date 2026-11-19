# Module: delivery-retention

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
LINE 寄送內容與嘗試明細依六個臺灣日曆月到期整理，保留精簡 task 防重送與結清憑證；未完成、結果不明及租約中的工作不得清理。每筆 owner fresh lock、精確 command receipt、attempt 刪除與 linked intent/task 去內容化共用單一 outer UoW，不產生 provider effect。

## Implementation
- primary: `subsystems/line/delivery_retention.py`
- `infrastructure/mysql/line_delivery_task_repository.py` — bounded candidate、fresh task/attempt/intent facts、精確清理及列表排除到期標記；原 enqueue 仍按 payload fingerprint 防重送。
- `infrastructure/mysql/line_notification_repository.py`、`api/routes/line_notification_rules.py` — 已到期原來源或精確 replay 不再提供舊來源補送，保留新業務事件入口。
- `subsystems/line/ports.py` — typed retention repository boundary。
- `api/dependencies/line_worker_operation.py` — canonical additional worker 接線。
- `api/routes/line_tasks.py` — 到期 detail typed 410，不回傳已清除內容。

## Contracts
- `document/架構重整/01_規格基線/17A_LINE_Gateway_Inbox與通知投遞正式規格.md` §4.4、LINE-RET-01～04。
- attempt DELETE guard 的 fresh／preserve migration 歸 Global migration；保留原 registry-delete 邊界，新增精確 retention receipt 例外。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/delivery-retention/contract/`
- Public detail 到期驗收沿 `delivery-task-presentation` 已宣告的公開 route 測試。

## Change triggers
Reconcile when cutoff semantics、retention receipt、fresh facts、payload marker、transaction or worker entry changes。
