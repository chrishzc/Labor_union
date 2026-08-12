import uuid
import streamlit as st

def render_matching_schedule_confirmation(case_no, plan_id, client):
    st.markdown("#### 日期表發送與雙方確認")
    try: state = client.query(case_no, plan_id)
    except Exception as error:
        st.warning(f"日期表尚不可發送：{error}")
        return False
    if st.button("發送目前服務日期表", key=f"send_schedule_{case_no}_{plan_id}"):
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
