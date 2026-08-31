module: matching-schedule-confirmation
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/matching-schedule-confirmation.md
layout_status: custom_current
test_root: ui_react/src/tests/matching_schedule_confirmation_actions.test.tsx

# Higher-boundary verification
- `tests/domains/external-integration/subsystems/line/integration/test_matching_schedule_confirmation.py` — Scheduling snapshot/repository 與 LINE delivery integration。
- `tests/domains/external-integration/subsystems/line/subsystems/test_line_matching_postback_stage7.py` — webhook/postback transport adaptation。
- `tests/test_matching_schedule_confirmation_api_client.py` 與 `tests/test_matching_schedule_confirmation_panel.py` 保留於現有 compatibility paths，本 slice 不搬移或重包。
