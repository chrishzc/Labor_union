import uuid
import streamlit as st

def render_matching_schedule_confirmation(case_no, plan_id, client):
    st.markdown("#### 日期表發送與雙方確認")
    try: state = client.query(case_no, plan_id)
    except Exception as error:
        st.warning(f"日期表尚不可發送：{error}")
        return False
    _render_schedule_preview(state.schedule_preview)
    if state.snapshot_status == "sent_outdated":
        st.warning("服務日期已異動；先前日期表與確認紀錄已失效，請檢查差異後決定是否重送。")
        _render_schedule_difference(state.outdated_schedule_preview, state.schedule_preview)
    _render_recipient_schedule_previews(state.schedule_preview.recipient_schedules)
    send_label = "重送目前服務日期表" if state.snapshot_status == "sent_outdated" else "發送目前服務日期表"
    if st.button(send_label, key=f"send_schedule_{case_no}_{plan_id}"):
        try:
            client.send(case_no, plan_id, idempotency_key=uuid.uuid4().hex)
            st.rerun()
        except Exception as error: st.error(f"發送失敗：{error}")
    for recipient in state.recipients:
        label = "客戶" if recipient.audience_type == "customer" else f"月嫂區段 {recipient.segment_id}"
        st.write(f"{label}｜{recipient.delivery_status}｜{recipient.confirmation_status}")
        if recipient.confirmation_occurred_at_utc:
            st.caption(
                f"最後確認事件：{recipient.confirmation_source}｜"
                f"{recipient.confirmation_occurred_at_utc:%Y-%m-%d %H:%M UTC}"
            )
        if recipient.confirmation_reason:
            st.warning(f"拒絕原因：{recipient.confirmation_reason}")
        value = st.selectbox("人工調整", ("manually_confirmed", "manually_revoked", "rejected"), key=f"schedule_value_{recipient.recipient_snapshot_id}")
        reason = st.text_input("原因（拒絕時必填）", key=f"schedule_reason_{recipient.recipient_snapshot_id}")
        if st.button(f"更新 {label}", key=f"schedule_update_{recipient.recipient_snapshot_id}"):
            try:
                client.confirm(recipient.recipient_snapshot_id, value, reason, idempotency_key=uuid.uuid4().hex)
                st.rerun()
            except Exception as error: st.error(f"更新失敗：{error}")
    if state.gate_passed: st.success("雙方已確認，可建立正式指派。")
    else: st.info("客戶與所有月嫂確認同一日期版本後，才可正式指派。")
    return state.gate_passed


def _render_schedule_preview(schedule):
    st.caption(
        f"日期表 Preview｜共 {schedule.total_service_days} 個服務日／"
        f"{schedule.total_weeks} 週（週日～週六）"
    )
    for week in schedule.weeks:
        dates = "、".join(week.service_dates)
        st.write(
            f"第 {week.week_number} 週 {week.period_start}～{week.period_end}｜"
            f"{week.service_day_count} 日｜{dates}"
        )


def _render_recipient_schedule_previews(recipient_schedules):
    for schedule in recipient_schedules:
        if schedule.audience_type != "caregiver":
            continue
        st.caption(
            f"月嫂區段 {schedule.segment_id}｜共 {schedule.total_service_days} 個服務日／"
            f"{schedule.total_weeks} 週"
        )
        for week in schedule.weeks:
            st.write(
                f"第 {week.week_number} 週｜{week.service_day_count} 日｜"
                f"{'、'.join(week.service_dates)}"
            )


def _render_schedule_difference(previous_schedule, current_schedule):
    if previous_schedule is None:
        st.caption("找不到先前日期表內容，請以目前日期表為準。")
        return
    previous_dates = _service_dates(previous_schedule)
    current_dates = _service_dates(current_schedule)
    added = "、".join(sorted(current_dates - previous_dates)) or "無"
    removed = "、".join(sorted(previous_dates - current_dates)) or "無"
    st.caption(f"日期差異｜新增：{added}｜移除：{removed}")


def _service_dates(schedule):
    return {
        service_date
        for week in schedule.weeks
        for service_date in week.service_dates
    }
