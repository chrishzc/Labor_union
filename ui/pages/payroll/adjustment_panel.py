import streamlit as st
import uuid

def render_payroll_adjustment_panel(case_no: str, client: object) -> None:
    st.subheader(f"月嫂薪資調整 (案件: {case_no})")
    
    try:
        case_data = client.query_case(case_no)
    except Exception as e:
        st.error(f"無法取得案件薪資義務: {e}")
        return

    st.markdown(f"**目前薪資版本**: `{case_data.payroll_version}`")
    
    if not case_data.obligations:
        st.info("該案件目前無可調整的薪資義務。")
        return

    with st.form(f"pa_preview_form_{case_no}"):
        st.markdown("#### 新增薪資調整")
        source_id = st.text_input("來源事件識別碼 (必填)")
        
        allocations = []
        for ob in case_data.obligations:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{ob.obligation_kind}** (指派 #{ob.assignment_id}, 月嫂 #{ob.staff_id})")
                st.caption(f"目前金額: ${ob.signed_amount_ntd:,}")
            with col2:
                amt = st.number_input(
                    "調整金額",
                    value=0,
                    key=f"pa_adj_{ob.assignment_id}"
                )
                if amt != 0:
                    allocations.append({
                        "assignment_id": ob.assignment_id,
                        "amount_ntd": amt
                    })
                    
        if st.form_submit_button("產生調整預覽", type="primary"):
            if not source_id.strip():
                st.error("請輸入來源事件識別碼。")
            elif not allocations:
                st.warning("請至少輸入一筆大於或小於 0 的調整金額。")
            else:
                try:
                    payload = {
                        "case_no": case_no,
                        "source_event_identity": source_id.strip(),
                        "allocations": allocations
                    }
                    preview = client.preview(payload)
                    st.session_state[f"pa_preview_{case_no}"] = preview
                    st.session_state[f"pa_preview_payload_{case_no}"] = payload
                    st.success("✅ 預覽成功產生！")
                except Exception as e:
                    st.error(f"預覽發生錯誤: {e}")

    preview_key = f"pa_preview_{case_no}"
    if preview_key in st.session_state:
        preview = st.session_state[preview_key]
        payload = st.session_state[f"pa_preview_payload_{case_no}"]
        
        st.markdown("### 調整預覽確認")
        st.json(preview.candidate)
        
        with st.form(f"pa_apply_form_{case_no}"):
            reason = st.text_input("調整備註 (必填)", max_chars=500)
            if st.form_submit_button("確認調整並套用"):
                if not reason.strip():
                    st.error("請填寫調整備註。")
                else:
                    try:
                        apply_payload = {
                            "case_no": case_no,
                            "source_event_identity": payload["source_event_identity"],
                            "allocations": payload["allocations"],
                            "expected_payroll_version": preview.payroll_version,
                            "preview_fingerprint": preview.preview_fingerprint,
                            "reason": reason.strip(),
                        }
                        command_headers = {
                            "Idempotency-Key": str(uuid.uuid4()),
                            "X-Correlation-ID": str(uuid.uuid4()),
                        }
                        result = client.apply(apply_payload, command_headers)
                        st.success(f"調整成功！")
                        del st.session_state[preview_key]
                        st.rerun()
                    except Exception as e:
                        st.error(f"套用發生錯誤: {e}")
