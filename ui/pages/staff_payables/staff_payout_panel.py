import streamlit as st
import uuid
from requests import HTTPError

def render_staff_payout_panel(staff_id: int, client: object) -> None:
    st.subheader(f"月嫂付款核銷 (月嫂 #{staff_id})")
    
    try:
        facts = client.query(staff_id)
    except Exception as e:
        st.error(f"無法取得核銷資料: {e}")
        return

    st.markdown(f"**目前帳戶版本**: `{facts.staff_payables_version}`")

    col1, col2 = st.columns(2)
    selected_events = []
    with col1:
        st.markdown("#### 付款事件紀錄")
        if not facts.events:
            st.info("無未核銷款項。")
        for ev in facts.events:
            if st.checkbox(f"[{ev.event_type}] ${ev.amount_ntd:,} ({ev.occurred_on})", key=f"sp_ev_{ev.id}"):
                if ev.finance_import_row_id:
                    selected_events.append(ev.finance_import_row_id)

    selected_obligations = []
    with col2:
        st.markdown("#### 應付帳款 (Obligations)")
        if not facts.obligations:
            st.info("無未核銷應付款。")
        for ob in facts.obligations:
            if st.checkbox(
                f"${ob.amount_due_ntd:,} (到期: {ob.due_date})", 
                key=f"sp_ob_{ob.obligation_identity}"
            ):
                selected_obligations.append(ob.obligation_identity)

    st.markdown("---")
    if st.button("產生核銷預覽", type="primary"):
        if not selected_events or not selected_obligations:
            st.warning("請至少選擇一筆款項與一筆應付款。")
            return
            
        try:
            corr_id = str(uuid.uuid4())
            preview = client.preview_payout(
                finance_import_row_ids=selected_events,
                obligation_identities=selected_obligations,
                correlation_id=corr_id
            )
            st.session_state[f"sp_preview_{staff_id}"] = preview
            st.session_state[f"sp_preview_req_{staff_id}"] = (selected_events, selected_obligations)
            st.success("✅ 預覽成功產生！")
        except Exception as e:
            st.error(f"預覽發生錯誤: {e}")

    preview_key = f"sp_preview_{staff_id}"
    if preview_key in st.session_state:
        preview = st.session_state[preview_key]
        req_events, req_obs = st.session_state[f"sp_preview_req_{staff_id}"]
        
        st.markdown("### 核銷預覽確認")
        st.json(preview.candidate)
        
        with st.form(f"sp_apply_form_{staff_id}"):
            reason = st.text_input("核銷備註 (必填)", max_chars=500)
            if st.form_submit_button("確認核銷並套用"):
                if not reason.strip():
                    st.error("請填寫核銷備註。")
                else:
                    try:
                        result = client.apply_payout(
                            finance_import_row_ids=req_events,
                            obligation_identities=req_obs,
                            preview=preview,
                            reason=reason.strip(),
                            idempotency_key=str(uuid.uuid4()),
                            correlation_id=str(uuid.uuid4())
                        )
                        st.success(f"核銷成功！(Job ID: {result.job_id})")
                        del st.session_state[preview_key]
                        st.rerun()
                    except Exception as e:
                        st.error(f"套用發生錯誤: {e}")
