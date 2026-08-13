from ui.api_clients.matching_schedule_confirmation_api_client import (
    ExpectedServiceSchedulePreviewView,
    ExpectedServiceScheduleWeekView,
    MatchingScheduleConfirmationView,
    ScheduleConfirmationRecipientView,
)
from ui.pages.scheduling import matching_schedule_confirmation_panel as panel


class _StreamlitRecorder:
    def __init__(self):
        self.text = []

    def markdown(self, value): self.text.append(value)
    def caption(self, value): self.text.append(value)
    def write(self, value): self.text.append(value)
    def warning(self, value): self.text.append(value)
    def info(self, value): self.text.append(value)
    def success(self, value): self.text.append(value)
    def button(self, *args, **kwargs): return False
    def selectbox(self, *args, **kwargs): return "manually_confirmed"
    def text_input(self, *args, **kwargs): return ""


class _ScheduleClient:
    def query(self, case_no, plan_id):
        week = ExpectedServiceScheduleWeekView(
            week_number=1,
            period_start="2026-08-02",
            period_end="2026-08-08",
            service_dates=["2026-08-03", "2026-08-05"],
            service_day_count=2,
        )
        preview = ExpectedServiceSchedulePreviewView(
            week_grouping_policy="calendar_week_sunday_to_saturday_v1",
            total_service_days=2,
            total_weeks=1,
            weeks=[week],
            recipient_schedules=[],
        )
        recipient = ScheduleConfirmationRecipientView(
            recipient_snapshot_id=9,
            audience_type="customer",
            segment_id=None,
            delivery_status="pending",
            confirmation_status="pending",
            confirmation_source=None,
            confirmation_reason=None,
            confirmation_occurred_at_utc=None,
        )
        return MatchingScheduleConfirmationView(
            case_no=case_no,
            plan_id=plan_id,
            confirmed_service_date_version=1,
            snapshot_id=None,
            snapshot_status="not_sent",
            schedule_preview=preview,
            recipients=[recipient],
            gate_passed=False,
        )


def test_schedule_panel_renders_typed_weekly_preview_before_send(monkeypatch):
    recorder = _StreamlitRecorder()
    monkeypatch.setattr(panel, "st", recorder)

    passed = panel.render_matching_schedule_confirmation("CASE-68", 18, _ScheduleClient())

    assert not passed
    assert "日期表 Preview｜共 2 個服務日／1 週（週日～週六）" in recorder.text
    assert "第 1 週 2026-08-02～2026-08-08｜2 日｜2026-08-03、2026-08-05" in recorder.text


def test_schedule_panel_explains_outdated_schedule_difference(monkeypatch):
    recorder = _StreamlitRecorder()
    monkeypatch.setattr(panel, "st", recorder)
    previous = ExpectedServiceSchedulePreviewView(
        week_grouping_policy="calendar_week_sunday_to_saturday_v1",
        total_service_days=1,
        total_weeks=1,
        weeks=[ExpectedServiceScheduleWeekView(
            week_number=1,
            period_start="2026-08-02",
            period_end="2026-08-08",
            service_dates=["2026-08-03"],
            service_day_count=1,
        )],
        recipient_schedules=[],
    )
    current = ExpectedServiceSchedulePreviewView(
        week_grouping_policy="calendar_week_sunday_to_saturday_v1",
        total_service_days=1,
        total_weeks=1,
        weeks=[ExpectedServiceScheduleWeekView(
            week_number=1,
            period_start="2026-08-02",
            period_end="2026-08-08",
            service_dates=["2026-08-04"],
            service_day_count=1,
        )],
        recipient_schedules=[],
    )

    panel._render_schedule_difference(previous, current)

    assert "日期差異｜新增：2026-08-04｜移除：2026-08-03" in recorder.text
