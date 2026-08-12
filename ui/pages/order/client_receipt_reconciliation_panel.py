import streamlit as st
import pandas as pd
from requests import HTTPError
from api.schemas.client_receipt_reconciliation import (
    ClientReceiptPreviewBody,
    ClientReceiptApplyBody,
)

def render_client_receipt_reconciliation_panel(case_no: str, client: object) -> None:
    st.subheader("客戶收款核銷")
    
    try:
        facts = client.query(case_no)
    except Exception as e:
        st.error(f"無法取得核銷資料: {e}")
        return

    if not facts.bank_facts and not facts.obligations:
        st.info("此案件目前沒有未核銷的銀行款項或應收帳款。")
        return

    st.markdown(f"**目前帳戶版本**: `{facts.account_version}`")

    # Layout for Bank Facts and Obligations
    col1, col2 = st.columns(2)
    
    selected_bank_facts = []
    with col1:
        st.markdown("#### 未核銷銀行款項")
        if not facts.bank_facts:
            st.info("無未核銷款項。")
        for bf in facts.bank_facts:
            if st.checkbox(
                f"${bf.amount_ntd:,} (日期: {bf.transaction_date})", 
                key=f"cr_bf_{bf.finance_import_row_id}"
            ):
                selected_bank_facts.append(bf.finance_import_row_id)

    selected_obligations = []
    with col2:
        st.markdown("#### 應收帳款 (Obligations)")
        if not facts.obligations:
            st.info("無未核銷應收帳款。")
        for ob in facts.obligations:
            if st.checkbox(
                f"[{ob.payment_stage}] ${ob.amount_due_ntd:,} (到期: {ob.due_date})", 
                key=f"cr_ob_{ob.obligation_identity}"
            ):
                selected_obligations.append(ob.obligation_identity)

    # Form to preview and apply
    st.markdown("---")
    payment_stage = st.selectbox(
        "收款階段 (Payment Stage)",
        options=["deposit", "first", "second", "adjustment"],
        format_func=lambda x: {
            "deposit": "訂金 (deposit)",
            "first": "一尾 (first)",
            "second": "二尾 (second)",
            "adjustment": "調整 (adjustment)"
        }[x]
    )

    if st.button("產生核銷預覽", type="primary"):
        if not selected_bank_facts or not selected_obligations:
            st.warning("請至少選擇一筆銀行款項與一筆應收帳款。")
            return
            
        preview_body = ClientReceiptPreviewBody(
            payment_stage=payment_stage,
            finance_import_row_ids=selected_bank_facts,
            obligation_identities=selected_obligations,
        )
        
        try:
            preview = client.preview(case_no, preview_body)
            st.session_state[f"cr_preview_{case_no}"] = preview
            st.session_state[f"cr_preview_body_{case_no}"] = preview_body
            st.session_state[f"cr_preview_operation_{case_no}"] = "normal"
            st.success("✅ 預覽成功產生！請在下方確認並送出。")
        except HTTPError as e:
            try:
                error_msg = e.response.json().get("detail", {}).get("error", {}).get("message", str(e))
                st.error(f"預覽失敗: {error_msg}")
            except Exception:
                st.error(f"預覽失敗: {e}")
        except Exception as e:
            st.error(f"預覽發生錯誤: {e}")

    # If preview exists in session state, show it and allow applying
    preview_key = f"cr_preview_{case_no}"
    if preview_key in st.session_state:
        preview = st.session_state[preview_key]
        preview_body = st.session_state[f"cr_preview_body_{case_no}"]
        operation_key = f"cr_preview_operation_{case_no}"
        operation = st.session_state.get(operation_key, "normal")
        
        st.markdown("### 核銷預覽確認")
        st.json(preview.candidate)
        if (
            preview.candidate.get("status") == "review_required"
            and "client_receipt_overpaid" in preview.candidate.get("blockers", [])
        ):
            st.warning("此筆實收超過應收；請建立客戶退款應付，不能以一般核銷直接套用。")
            if st.button("產生超收退款應付預覽", key=f"cr_overage_preview_{case_no}"):
                try:
                    overage_preview = client.preview_overage(case_no, preview_body)
                except HTTPError as error:
                    st.error(f"超收處置預覽失敗: {error}")
                else:
                    st.session_state[preview_key] = overage_preview
                    st.session_state[operation_key] = "overage"
                    st.rerun()
            return
        
        with st.form(f"cr_apply_form_{case_no}"):
            reason = st.text_input("核銷備註 (必填)", max_chars=500)
            submitted = st.form_submit_button("確認核銷並套用")
            
            if submitted:
                if not reason.strip():
                    st.error("請填寫核銷備註。")
                else:
                    import uuid
                    apply_body = ClientReceiptApplyBody(
                        payment_stage=preview_body.payment_stage,
                        finance_import_row_ids=preview_body.finance_import_row_ids,
                        obligation_identities=preview_body.obligation_identities,
                        expected_account_version=preview.account_version,
                        preview_fingerprint=preview.preview_fingerprint,
                        reason=reason.strip()
                    )
                    
                    try:
                        apply = client.apply_overage if operation == "overage" else client.apply
                        result = apply(case_no, apply_body, str(uuid.uuid4()))
                        message = "已建立客戶退款應付" if operation == "overage" else "核銷成功"
                        st.success(f"{message}！(結算 ID: {result.settlement_identity})")
                        del st.session_state[preview_key]
                        del st.session_state[f"cr_preview_body_{case_no}"]
                        st.session_state.pop(operation_key, None)
                        st.rerun()
                    except HTTPError as e:
                        try:
                            error_msg = e.response.json().get("detail", {}).get("error", {}).get("message", str(e))
                            st.error(f"套用失敗: {error_msg}")
                        except Exception:
                            st.error(f"套用失敗: {e}")
                    except Exception as e:
                        st.error(f"套用發生錯誤: {e}")
