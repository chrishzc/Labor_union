"""
File: app.py
Description: 管理端 Streamlit 導覽、全域登入與短效 TOTP QR 配對入口。
"""

import importlib
import os
import sys
from urllib.parse import parse_qs
from io import BytesIO
from collections.abc import Mapping

import qrcode
import streamlit as st
# 將專案根目錄加入 Python 搜尋路徑，以利讀取 services
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from ui.nav_helper import NAV_KEY, apply_pending_navigation
from ui.api_clients.access_control_api_client import AccessControlApiClient, AccessControlApiError
from ui.pages.shared import (
    ADMIN_ACCESS_TOKEN_KEY,
    admin_auth_is_bypassed,
    local_developer_session_is_enabled,
)

st.set_page_config(page_title="Lobar Union 管理系統", layout="wide")

DEFAULT_PAGE_TITLE = "📦 訂單管理"
NAV_SECTION_KEY = "nav_section"
PAGE_REGISTRY: Mapping[str, tuple[tuple[str, str], ...]] = {
    "營運作業": (
        ("📦 訂單管理", "ui.pages.02_orders"),
        ("📥 資料匯入中心", "ui.pages.09_data_import"),
        ("多月嫂排班", "ui.pages.03_calendar"),
        ("📋 表單與履歷問卷管理", "ui.pages.05_form_management"),
        ("💬 LINE 管理中心", "ui.pages.07_line_management"),
    ),
    "帳務": (
        ("💰 帳務作業中心", "ui.pages.04_finance"),
    ),
    "異常與稽核": (
        ("異常警示中心", "ui.pages.06_finance_alerts"),
        ("🔍 資料庫原始資料瀏覽", "ui.pages.01_data_browser"),
        ("工會人員權限", "ui.pages.09_access_management"),
        ("🩺 系統狀態", "ui.pages.08_system_status"),
    ),
}

ROLLBACK_TARGETS: Mapping[str, tuple[str, str | tuple[str, ...] | None, str]] = {
    "form-management": ("ui.pages.05_form_management", "order-tracker", "📋 表單與履歷問卷管理"),
    "orders": ("ui.pages.02_orders", None, "📦 訂單管理"),
    "scheduling": ("ui.pages.03_calendar", ("calendar", "staff-directory"), "多月嫂排班"),
    "data-import": ("ui.pages.09_data_import", None, "📥 資料匯入中心"),
    "line-management": ("ui.pages.07_line_management", None, "💬 LINE 管理中心"),
    "system-status": ("ui.pages.08_system_status", "reports", "🩺 系統狀態"),
    "finance": ("ui.pages.04_finance", None, "💰 帳務作業中心"),
    "anomalies": ("ui.pages.06_finance_alerts", None, "異常警示中心"),
    "data-browser": ("ui.pages.01_data_browser", None, "🔍 資料庫原始資料瀏覽"),
    "access-management": ("ui.pages.09_access_management", None, "工會人員權限"),
}


def resolve_rollback_query(raw_query: str | Mapping[str, object]) -> tuple[str, str | None] | None:
    """Resolve only the frozen entry/view pair; malformed input fails closed."""
    if isinstance(raw_query, str):
        values = parse_qs(raw_query.lstrip("?"), keep_blank_values=True)
    else:
        values = {key: value if isinstance(value, list) else [value] for key, value in raw_query.items()}
    if set(values) - {"entry", "view"} or any(len(items) != 1 for items in values.values()):
        return None
    entry = values.get("entry", [None])[0]
    view = values.get("view", [None])[0]
    if not isinstance(entry, str) or not entry.isascii() or entry != entry.lower() or entry not in ROLLBACK_TARGETS:
        return None
    module_name, expected_view, page_title = ROLLBACK_TARGETS[entry]
    allowed_views = (expected_view,) if isinstance(expected_view, str) else expected_view
    if view != expected_view and (not allowed_views or view not in allowed_views):
        return None
    return page_title, view


def _consume_rollback_query() -> bool:
    params = getattr(st, "query_params", None)
    if params is None:
        return True
    if not params:
        return True
    resolved = resolve_rollback_query(params)
    params.clear()
    if resolved is None:
        return False
    page_title, view = resolved
    st.session_state[NAV_KEY] = page_title
    if view is not None:
        st.session_state["rollback_calendar_view"] = view
    return True


def _load_page_show(module_name):
    module = importlib.import_module(module_name)
    show = getattr(module, "show", None)
    if not callable(show):
        raise TypeError(f"{module_name} 缺少可呼叫的 show()")
    return show


# Kept cohesive because selection and lazy page execution form one shell boundary.
def main():
    if not _consume_rollback_query():
        st.session_state[NAV_KEY] = DEFAULT_PAGE_TITLE
        st.warning("無效的回復入口，已安全返回預設頁面。")
        return
    if not _require_global_authentication():
        return
    st.sidebar.title("🧭 Lobar Union 系統導覽")
    apply_pending_navigation()
    pages = _page_modules(PAGE_REGISTRY)
    page_titles = tuple(pages)
    if NAV_KEY not in st.session_state or st.session_state[NAV_KEY] not in page_titles:
        st.session_state[NAV_KEY] = DEFAULT_PAGE_TITLE
    _apply_navigation_section(st.session_state[NAV_KEY])
    section = st.sidebar.selectbox(
        "功能分類",
        tuple(PAGE_REGISTRY),
        key=NAV_SECTION_KEY,
        on_change=_select_first_page_in_section,
    )
    section_pages = PAGE_REGISTRY[section]
    choice = st.sidebar.radio(
        "前往頁面",
        tuple(title for title, _ in section_pages),
        key=NAV_KEY,
    )

    # 執行該分頁的 show()
    try:
        show = _load_page_show(pages[choice])
    except Exception as error:
        st.error(f"載入頁面失敗：{error}")
        return
    show()


def _require_global_authentication() -> bool:
    """Render only the public login/enrollment surface before the shell is initialized."""
    if admin_auth_is_bypassed():
        st.caption("local_bypass：未啟用管理員登入；不得用於 production。")
        return True
    client = AccessControlApiClient()
    token = st.session_state.get(ADMIN_ACCESS_TOKEN_KEY)
    if isinstance(token, str) and token:
        try:
            profile = client.me(token)
        except AccessControlApiError:
            st.session_state.pop(ADMIN_ACCESS_TOKEN_KEY, None)
        else:
            st.session_state["line_admin_profile"] = profile.model_dump()
            if st.sidebar.button("登出", key="global_admin_logout"):
                try:
                    client.logout(token)
                except AccessControlApiError:
                    pass
                st.session_state.pop(ADMIN_ACCESS_TOKEN_KEY, None)
                st.rerun()
            return True
    if local_developer_session_is_enabled() and not st.session_state.get("local_developer_session_attempted"):
        st.session_state["local_developer_session_attempted"] = True
        try:
            session = client.development_session()
        except AccessControlApiError as error:
            st.warning(f"local_developer_session 無法建立：{error}")
        else:
            st.session_state[ADMIN_ACCESS_TOKEN_KEY] = session.access_token
            st.session_state["line_admin_profile"] = session.admin.model_dump()
            st.rerun()
    _render_login_or_enrollment(client)
    return False


def _render_login_or_enrollment(client: AccessControlApiClient) -> None:
    st.title("管理後台登入")
    enrollment = st.session_state.get("access_control_enrollment")
    if isinstance(enrollment, dict):
        provisioning_uri = str(enrollment["provisioning_uri"])
        st.info("請用驗證器掃描 QR code，並輸入第一組驗證碼。")
        st.image(
            _enrollment_qr_png(provisioning_uri),
            caption="此 QR code 僅在本次短效 MFA 綁定畫面顯示。",
            width=280,
        )
        with st.expander("無法掃描時，顯示手動設定資訊"):
            st.code(provisioning_uri, language=None)
        enrollment_submitting = bool(
            st.session_state.get("access_control_enrollment_submitting")
        )
        with st.form("global_mfa_enrollment"):
            code = st.text_input("第一組 TOTP 驗證碼", max_chars=6)
            submitted = st.form_submit_button(
                "完成 MFA 綁定", type="primary", disabled=enrollment_submitting
            )
        if submitted and not enrollment_submitting:
            st.session_state["access_control_enrollment_submitting"] = True
            try:
                codes = client.verify_enrollment(
                    challenge_id=str(enrollment["id"]),
                    challenge_token=str(enrollment["token"]),
                    totp_code=code,
                )
            except AccessControlApiError as error:
                st.session_state.pop("access_control_enrollment_submitting", None)
                st.error(str(error))
                return
            st.session_state.pop("access_control_enrollment_submitting", None)
            st.session_state.pop("access_control_enrollment", None)
            st.success("MFA 已完成。請保存下列 recovery codes，再使用帳密與 TOTP 登入。")
            st.code("\n".join(codes), language=None)
        return
    password_challenge = st.session_state.get("access_control_password_challenge")
    if isinstance(password_challenge, dict):
        st.info("帳密已通過。請輸入驗證器代碼或 recovery code。")
        factor_submitting = bool(
            st.session_state.get("access_control_factor_submitting")
        )
        with st.form("global_admin_factor_verification"):
            factor_code = st.text_input("TOTP 驗證碼或 recovery code")
            submitted = st.form_submit_button(
                "完成登入", type="primary", disabled=factor_submitting
            )
        if submitted and not factor_submitting:
            st.session_state["access_control_factor_submitting"] = True
            try:
                session = client.verify_password_challenge(
                    challenge_id=str(password_challenge["id"]),
                    challenge_token=str(password_challenge["token"]),
                    factor_code=factor_code,
                )
            except AccessControlApiError as error:
                st.session_state.pop("access_control_factor_submitting", None)
                st.session_state.pop("access_control_password_challenge", None)
                st.error(str(error))
                st.info("此登入 challenge 已作廢；請從帳密第一步重新登入。")
                return
            st.session_state.pop("access_control_factor_submitting", None)
            st.session_state.pop("access_control_password_challenge", None)
            st.session_state[ADMIN_ACCESS_TOKEN_KEY] = session.access_token
            st.session_state["line_admin_profile"] = session.admin.model_dump()
            st.rerun()
        return
    with st.form("global_admin_login"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary")
    if submitted:
        try:
            challenge = client.issue_password_challenge(username=username, password=password)
        except AccessControlApiError as error:
            st.error(str(error))
            return
        if challenge.challenge_type == "mfa_enrollment":
            st.session_state["access_control_enrollment"] = {
                "id": challenge.challenge_id,
                "token": challenge.challenge_token,
                "provisioning_uri": challenge.provisioning_uri,
                "expires_at": challenge.expires_at.isoformat(),
            }
            st.rerun()
        st.session_state["access_control_password_challenge"] = {"id": challenge.challenge_id, "token": challenge.challenge_token}
        st.rerun()


def _enrollment_qr_png(provisioning_uri: str) -> bytes:
    """將短效 provisioning URI 在記憶體中編碼為 QR PNG，不寫檔或呼叫外部服務。"""
    uri = provisioning_uri.strip()
    if not uri.startswith("otpauth://totp/"):
        raise ValueError("MFA provisioning URI 格式不正確")
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    code.add_data(uri)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _page_modules(
    registry: Mapping[str, tuple[tuple[str, str], ...]],
) -> dict[str, str]:
    return {
        title: module_name
        for pages in registry.values()
        for title, module_name in pages
    }


def _apply_navigation_section(page_title: str) -> None:
    for section, pages in PAGE_REGISTRY.items():
        if page_title in {title for title, _ in pages}:
            st.session_state[NAV_SECTION_KEY] = section
            return
    st.session_state[NAV_KEY] = DEFAULT_PAGE_TITLE
    st.session_state[NAV_SECTION_KEY] = _section_for(DEFAULT_PAGE_TITLE)


def _select_first_page_in_section() -> None:
    section = st.session_state[NAV_SECTION_KEY]
    st.session_state[NAV_KEY] = PAGE_REGISTRY[section][0][0]


def _section_for(page_title: str) -> str:
    return next(
        section
        for section, pages in PAGE_REGISTRY.items()
        if page_title in {title for title, _ in pages}
    )

if __name__ == "__main__":
    main()
