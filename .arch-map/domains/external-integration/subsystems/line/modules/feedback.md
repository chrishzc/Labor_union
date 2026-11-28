# Module: M2 feedback owner

## Responsibility

LINE Integration owns the bounded `resolved | unresolved` feedback root, immutable terminal receipt, fixed catalog/reply revision linkage and recomputable aggregate. An unresolved feedback decision persists its own receipt but does not itself create a ticket. Customer Service owns ticket creation.
2026-11-14 擴充：`navigation_catalog.py`、`deterministic_ai_router.py` 與 `AiEventStudio.tsx` 統一涵蓋所有於 LINE 1 對 1 與案件群組聊天室觸發動作之文字指令（含身分綁定、案件群組綁定／邀請、群組小幫手與結案／合意延期、圖文選單切換、轉接專人／恢復自動助理、問答回饋），各 handler 統一由 `route_aliases()` 讀取自訂指令；`customer_binding` 與 `order_group_bind` 允許依 1 對 1 精確／群組前綴跨情境共用「綁定訂單」。

現行指令目錄與一對一預覽排除退役的月嫂身分綁定、服務登記、客戶綁定及私聊案件資訊文字指令。`綁定訂單` 只對案件群組開放。替代入口依身分管理與圖文選單正式規格。

## Source

- `subsystems/line/feedback_contracts.py`
- `subsystems/line/feedback_application.py`
- `infrastructure/mysql/line_feedback_repository.py`

The adapter reuses immutable `line_notification_source_events` and `line_command_receipts`; the LINE outer Unit of Work remains the sole commit owner. It does not store raw prompt text, provider payload, credentials or conversation dumps.

## Implementation

- `subsystems/line/feedback_contracts.py`
- `subsystems/line/feedback_application.py`
- `subsystems/line/navigation_catalog.py`
- `subsystems/line/ai_router_contracts.py`
- `subsystems/line/deterministic_ai_router.py`
- `subsystems/line/service_help_application.py`
- `infrastructure/mysql/line_feedback_repository.py`
- `api/dependencies/line_runtime.py`
- `api/dependencies/line_worker_operation.py`
- `api/routes/line_ai_events.py`
- `api/schemas/line_ai_events.py`
- `api/routes/line_feedback.py`
- `api/schemas/line_feedback.py`
- `ui_react/src/pages/line_management/AiEventStudio.tsx`
- `ui_react/src/api/line_configuration/line_guidance_client.ts` — shared read-only guidance catalog and router preview for LINE interface settings and AI answer testing.

## Verification

- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/ai_event_studio_local_preview.test.tsx`
- `tests/domains/external-integration/subsystems/line/modules/feedback/test_feedback_application.py`
- `tests/domains/external-integration/subsystems/line/modules/feedback/test_navigation_catalog_aliases.py`
- `tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_knowledge_owner_flow.py`
- `tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_knowledge_source_validation.py`
- `tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_transaction_failures.py`
- `tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_feedback_page.py`
- `ui_react/src/tests/ai_event_studio_local_preview.test.tsx`

Required checks distinguish wrong terminal outcome, idempotency replay, unresolved feedback without automatic ticket creation, and fixed catalog/window aggregates.
