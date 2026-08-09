"""Thin accounts-payable query and archived-download display."""

from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st

from ui.api_clients.accounts_payable_export_client import (
    AccountsPayableExportApiClient,
)

_DISPLAY_COLUMNS = (
    "月份-銀行代碼-流水號", "銀行名稱", "客戶or服務人員姓名", "銀行帳號",
    "銀行代號(碼)", "金額", "身分證字號(匯款到永豐才要填)", "案件編號", "匯款日期",
)


def _render_tab4_accounts_payable():
    """Display typed backend results without deriving accounting facts."""
    st.subheader("應付帳款查詢／輸出")
    st.caption(
        "每次產生檔案都會先永久歸檔；下載不會改變付款或核銷狀態。"
    )
    target_month = _target_month_selector()
    client = AccountsPayableExportApiClient()
    try:
        preview = client.query(target_month)
    except (requests.RequestException, KeyError, ValueError) as error:
        st.error(f"讀取 {target_month} 應付帳款失敗：{error}")
        return
    _render_preview(preview)
    _render_export_action(client, target_month)
    _render_archive_query(client, int(target_month[:4]))


# One cohesive Streamlit widget is clearer than indirect wrappers per field.
def _target_month_selector() -> str:
    today = datetime.today()
    year_column, month_column = st.columns(2)
    with year_column:
        selected_year = st.selectbox(
            "年份",
            list(range(today.year - 2, today.year + 3)),
            index=2,
            key="accounts_payable_year",
        )
    with month_column:
        selected_month = st.selectbox(
            "月份",
            list(range(1, 13)),
            index=today.month - 1,
            format_func=lambda month: f"{month:02d} 月",
            key="accounts_payable_month",
        )
    return f"{selected_year:04d}-{selected_month:02d}"


def _render_preview(preview: dict[str, object]) -> None:
    rows = preview.get("rows") or []
    frame = pd.DataFrame(_fixed_transfer_rows(rows), columns=_DISPLAY_COLUMNS)
    st.metric("待匯款合計", f"{int(preview['total_amount_ntd']):,} 元")
    st.write(f"共 {int(preview['row_count'])} 筆待匯款項")
    st.dataframe(frame, width="stretch", hide_index=True)


def _fixed_transfer_rows(rows):
    serials = {"31": 0, "633": 0}
    result = []
    for row in rows:
        payment_date = date.fromisoformat(str(row["payment_date"]))
        bank_code = "31" if row["payment_type"] == "staff_payable" else "633"
        serials[bank_code] += 1
        result.append({
            _DISPLAY_COLUMNS[0]: f"{payment_date.month}-{bank_code}-{serials[bank_code]}",
            _DISPLAY_COLUMNS[1]: "永豐銀行" if bank_code == "31" else "台新銀行",
            _DISPLAY_COLUMNS[2]: row["recipient_name"],
            _DISPLAY_COLUMNS[3]: row["bank_account"],
            _DISPLAY_COLUMNS[4]: row["bank_code"],
            _DISPLAY_COLUMNS[5]: row["amount_ntd"],
            _DISPLAY_COLUMNS[6]: row["recipient_identity_card"] if bank_code == "31" else "",
            _DISPLAY_COLUMNS[7]: ",".join(row["case_numbers"]),
            _DISPLAY_COLUMNS[8]: payment_date,
        })
    return result


def _render_export_action(
    client: AccountsPayableExportApiClient,
    target_month: str,
) -> None:
    state_key = f"accounts_payable_download_{target_month}"
    if st.button("產生並歸檔應付帳款 Excel", key=f"prepare_{state_key}"):
        _prepare_download(client, target_month, state_key)
    artifact = st.session_state.get(state_key)
    if artifact is None:
        return
    st.download_button(
        "下載已歸檔的應付帳款 Excel",
        data=artifact.workbook_bytes,
        file_name=artifact.filename,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        key=f"download_{state_key}",
    )


def _prepare_download(client, target_month: str, state_key: str) -> None:
    try:
        with st.spinner("正在產生並歸檔檔案…"):
            st.session_state[state_key] = client.export(target_month)
    except (requests.RequestException, ValueError) as error:
        st.error(f"產生應付帳款 Excel 失敗：{error}")


def _render_archive_query(client, year: int) -> None:
    with st.expander(f"{year} 年系統歸檔"):
        try:
            archive = client.query_archive(year)
        except (requests.RequestException, KeyError, ValueError) as error:
            st.error(f"讀取歸檔清單失敗：{error}")
            return
        records = archive.get("records") or []
        if not records:
            st.info("目前沒有歸檔檔案。")
            return
        st.dataframe(
            pd.DataFrame(records),
            width="stretch",
            hide_index=True,
        )
