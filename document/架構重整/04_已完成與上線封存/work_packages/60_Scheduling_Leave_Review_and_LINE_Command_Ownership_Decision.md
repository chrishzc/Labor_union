---
doc_type: architecture-decision
declared_status: human-confirmed; scheduling-api-implementation-blocked-by-live-drift
date: 2026-08-12
owner: Scheduling / LINE Integration
---

# Scheduling 請假審核與 LINE 指令歸屬裁決

## Business scenarios

1. 管理員審核月嫂請假時，操作 Scheduling 根事實，不進入 LINE identity review。
2. LINE 使用者輸入既有綁定指令時，取得可預測且唯一的 identity flow。

## 人工裁決

- 月嫂請假審核採 Scheduling bounded API／typed client；不得放在 LINE route 或
  `LineAdminApiClient`。
- `綁定訂單`、`訂單查詢` 保留 customer binding；`綁定後台帳號` 保留 admin binding。
- `online.sh` 與 `online.bat` 同為本機開發 launcher；僅限 operator 使用，不得作 production deployment。

## 本次 write set

- `subsystems/line/webhook_identity_handlers.py`
- `ui/api_clients/line_api_client.py`
- 對應正式規格、focused tests 與本 decision

## Live drift 與後續入口

遠端新增的 `subsystems/scheduling/staff_leave_review_service.py` 依賴目前不存在的
`services.db_service` 與 `services.line_task_service`，無法安全掛入 FastAPI。後續實作必須另以
Scheduling repository、單一 outer UoW、typed errors、capability、audit/outbox 與 entrypoint
replacement 完成；不得復活 legacy `services.*`。在此之前，錯置且沒有實際 canonical route 的
LINE client methods 先移除，fail closed。

## Acceptance

- 三個既有 aliases 進入指定 binding flow。
- `LineAdminApiClient` 不含 `/api/v1/line/review-requests` 或 staff-leave review methods。
- LINE cutover 與 identity focused regression 通過。
- 不以 `online.sh` 缺檔阻擋 Windows merge。
