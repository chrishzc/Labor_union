import streamlit as st
import uuid
from requests import HTTPError

def render_payroll_rebuild_panel(case_no: str, client: object) -> None:
    st.subheader(f"月嫂薪資重算 (案件: {case_no})")
    
    if st.button("產生薪資重算預覽", type="primary", key=f"pr_preview_btn_{case_no}"):
        try:
            preview = client.preview(case_no)
            st.session_state[f"pr_preview_{case_no}"] = preview
            st.success("✅ 預覽成功產生！")
        except Exception as e:
            st.error(f"預覽發生錯誤: {e}")

    preview_key = f"pr_preview_{case_no}"
    if preview_key in st.session_state:
        preview = st.session_state[preview_key]
        
        st.markdown("### 薪資預覽結果")
        st.json({
            "assignments": preview.candidate.get("assignments", []),
            "actions": preview.candidate.get("actions", []),
            "earned_floor_fee_ntd": preview.candidate.get("earned_floor_fee_ntd"),
            "total_payable_ntd": preview.candidate.get("total_payable_ntd"),
        })
        
        with st.form(f"pr_apply_form_{case_no}"):
            reason = st.text_input("重算備註 (必填)", max_chars=500)
            if st.form_submit_button("確認重算並套用"):
                if not reason.strip():
                    st.error("請填寫重算備註。")
                else:
                    try:
                        result = client.apply(
                            case_no=case_no,
                            preview=preview,
                            reason=reason.strip(),
                            idempotency_key=str(uuid.uuid4()),
                            correlation_id=str(uuid.uuid4())
                        )
                        st.success(f"重算成功！(Job ID: {result.job_id})")
                        del st.session_state[preview_key]
                        st.rerun()
                    except Exception as e:
                        st.error(f"套用發生錯誤: {e}")

def render_staff_monthly_payroll_panel(staff_id: int, year: int, month: int, client: object) -> None:
    st.subheader(f"月嫂月結薪資 ({year} 年 {month} 月)")
    
    try:
        summary = client.query_staff_month(staff_id, year, month)
    except Exception as e:
        st.error(f"無法取得月結資料: {e}")
        return
        
    st.markdown(f"**案件數**: {summary.case_count} | **應付總計**: ${summary.payable_total_ntd:,} | **實付總計**: ${summary.net_payable_ntd:,}")
    
    if summary.obligations:
        st.markdown("#### 帳款明細")
        for ob in summary.obligations:
            st.markdown(f"- 案件 `{ob.case_no}`: ${ob.amount_due_ntd:,} (到期: {ob.due_date})")
    else:
        st.info("該月無帳款明細。")
