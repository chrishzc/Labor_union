# Module: M2 feedback owner

## Responsibility

LINE Integration owns the bounded `resolved | unresolved` feedback root, immutable terminal receipt, fixed catalog/reply revision linkage and recomputable aggregate. Unresolved feedback delegates exact ticket creation to the Customer Service owner and stores only the resulting ticket reference.

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
- `api/routes/line_ai_events.py`
- `api/schemas/line_ai_events.py`
- `api/routes/line_feedback.py`
- `api/schemas/line_feedback.py`
- `ui_react/src/pages/line_management/AiEventStudio.tsx`

## Verification

- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/ai_event_studio_local_preview.test.tsx`
- `tests/domains/external-integration/subsystems/line/modules/feedback/test_feedback_application.py`
- `ui_react/src/tests/ai_event_studio_local_preview.test.tsx`

Required negative cases are wrong terminal outcome, idempotency replay, unresolved ticket linkage and fixed catalog/window aggregate.
