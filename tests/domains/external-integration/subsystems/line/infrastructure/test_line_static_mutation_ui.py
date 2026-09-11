"""
File: test_line_static_mutation_ui.py
Description: 驗證 LINE static mutation UI 的 preview、確認、apply 與安全 readback 契約。
"""

from pathlib import Path


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def _source(name: str) -> str:
    return (ROOT / "line" / "static" / name).read_text(encoding="utf-8")


def test_identity_ui_previews_every_binding_kind_before_apply() -> None:
    source = _source("identity.html")
    submit = source.split("async function submitForm", 1)[1].split(
        "async function loadLiffId", 1
    )[0]

    assert "`/api/v1/line/identity/${definition.endpoint}/preview`" in submit
    assert "`/api/v1/line/identity/${definition.endpoint}/apply`" in submit
    assert submit.index("/${definition.endpoint}/preview") < submit.index(
        "/${definition.endpoint}/apply"
    )
    assert "目前版本：" not in source
    assert "expected_version" in source
    assert "確認送出身分驗證" in source
    assert "authentication_pending" in source
    assert "帳密於套用時驗證" in source
    assert "preview.password" not in submit
    assert "JSON.stringify(preview" not in submit
    assert "預覽指紋：" not in submit
    assert "收據：" not in submit
    assert "套用 readback" not in submit


def test_staff_identity_ui_reports_direct_binding_without_claiming_menu_delivery() -> None:
    source = _source("identity.html")
    submit = source.split("async function submitForm", 1)[1].split(
        "async function applyIdentityPreview", 1
    )[0]

    assert "資料匹配後會立即完成綁定" in source
    assert "找不到匹配資訊，請檢查輸入內容是否正確或聯繫工會人員" in submit
    assert "我們已為您切換專屬圖文選單" not in submit
    assert "專屬圖文選單將於系統處理完成後套用" in submit


def test_mobile_review_ui_uses_preview_apply_and_safe_readback() -> None:
    source = _source("mobile_admin.html")
    decision = source.split("async function previewReviewDecision", 1)[1]

    assert "/decision/preview`" in decision
    assert "/decision/apply`" in decision
    assert "/decision`," not in decision
    assert "preview_fingerprint" in decision
    assert "before_status" in source
    assert "after_status" in source
    assert "resulting_version" in source
    assert "確認套用此預覽" in source
    assert "審核結果已更新" in decision
    assert "receipt_identity" in decision
    assert "outcome" in decision
    assert "尚未證明送達" in decision
    preview_render = source.split("function renderReviewPreview", 1)[1].split(
        "async function previewReviewDecision", 1
    )[0]
    assert "預覽指紋" not in preview_render
    assert "preview_fingerprint.slice" not in preview_render
    assert "版本：" not in preview_render


def test_mobile_review_terminal_states_are_explicitly_read_only() -> None:
    source = _source("mobile_admin.html")
    review_card = source.split("function reviewCard", 1)[1].split(
        "function requireReviewPreview", 1
    )[0]

    assert 'review.status !== "pending"' in review_card
    assert "此申請僅供查閱" in review_card
    assert review_card.index('review.status !== "pending"') < review_card.index(
        'document.createElement("textarea")'
    )


def test_registration_ui_uses_preview_confirmation_apply_and_typed_readback() -> None:
    source = _source("register.html")
    submit = source.split('document.getElementById("registerForm").addEventListener("submit"', 1)[1]
    success_render = source.split("successDescription.textContent = [", 1)[1].split(
        "].join('\\n')", 1
    )[0]

    assert "/api/v1/line/identity/registration/preview" in submit
    assert "/api/v1/line/identity/registration/apply" in submit
    assert submit.index("/registration/preview") < submit.index("/registration/apply")
    assert "expected_binding_version" in submit
    assert "preview_fingerprint" in submit
    assert "identity_status" in submit
    assert "登記編號：" not in success_render

    assert "登記編號：" not in success_render
    assert "客戶識別：" not in success_render
    assert "不代表已完成媒合" in source
    assert "不代表 LINE 訊息已送達" in source


def test_mobile_ui_safely_extracts_errors_and_renders_server_text_as_text() -> None:
    source = _source("mobile_admin.html")
    helper = source.split("function safeErrorMessage", 1)[1].split(
        "async function postJson", 1
    )[0]
    ticket_card = source.split("function ticketCard", 1)[1].split(
        "async function loadTicketDetail", 1
    )[0]
    review_card = source.split("function reviewCard", 1)[1].split(
        "async function previewReviewDecision", 1
    )[0]

    assert "result?.detail?.error?.message" in helper
    assert "result?.error?.message" in helper
    assert "JSON.stringify" not in helper
    assert ".innerHTML" not in source
    assert ".innerHTML" not in ticket_card
    assert ".innerHTML" not in review_card
    assert "textContent" in ticket_card
    assert "textContent" in review_card
    assert "處理紀錄載入失敗，請重試。" in source
    assert "重新載入處理紀錄" in source


def test_mobile_customer_reply_uses_preview_confirmation_apply_and_readback() -> None:
    source = _source("mobile_admin.html")
    reply = source.split("async function previewTicketReply", 1)[1].split(
        "async function loadReviews", 1
    )[0]

    assert "/reply/preview`" in reply
    assert "/reply/apply`" in reply
    assert "/reply`," not in reply
    assert reply.index("/reply/preview") < reply.index("/reply/apply")
    assert "preview_fingerprint" in reply
    assert "expected_version" in reply
    assert "delivery_enqueued" in reply
    assert "delivery_delivered" in reply
    assert "readback" in reply
    assert "確認套用此客服回覆預覽" in source
    assert "尚未送達" in reply


def test_all_active_line_pages_reject_query_string_user_identity() -> None:
    for name in (
        "identity.html",
        "register.html",
        "staff_order_search.html",
        "staff_schedule.html",
        "staff_baby_log.html",
        "staff_payout.html",
        "mobile_admin.html",
    ):
        source = _source(name)
        assert 'get("userId")' not in source
        assert "?userId=" not in source


def test_mobile_admin_hides_internal_identity_and_concurrency_metadata() -> None:
    source = _source("mobile_admin.html")
    initialize = source.split("async function init()", 1)[1].split(
        "function switchPane", 1
    )[0]
    ticket_detail = source.split("async function loadTicketDetail", 1)[1].split(
        "function invalidateTicketReplyPreview", 1
    )[0]
    review_apply = source.split("async function applyReviewDecision", 1)[1]
    reply_apply = source.split("async function applyTicketReply", 1)[1].split(
        "async function loadReviews", 1
    )[0]

    assert "profile.role" not in initialize
    assert "event.actor_id" not in ticket_detail
    assert "收據 ${data.receipt_identity}" not in review_apply
    assert "版本 ${data.version}" not in review_apply
    assert "版本 ${data.resulting_version}" not in reply_apply
    assert "delivery_enqueued=${data.delivery_enqueued}" not in reply_apply
    assert "LINE 訊息已排入可靠發送佇列" in reply_apply


def test_mobile_admin_studio_preview_is_zero_data_and_keeps_formal_auth() -> None:
    source = _source("mobile_admin.html")
    initialize = source.split("async function init()", 1)[1].split(
        "function renderStudioPreview", 1
    )[0]
    preview = source.split("function renderStudioPreview", 1)[1].split(
        "function switchPane", 1
    )[0]
    post_json = source.split("async function postJson", 1)[1].split(
        "async function init()", 1
    )[0]

    assert 'get("studio_preview") === "1"' in source
    assert "if (studioPreview)" in initialize
    assert "renderStudioPreview(target);" in initialize
    assert "revealMobileAdmin();" in initialize
    assert initialize.index("renderStudioPreview(target)") < initialize.index(
        'fetch("/api/v1/line/identity/runtime-config")'
    )
    assert "fetch(" not in preview
    assert "postJson(" not in preview
    assert 'control.disabled = true' in preview
    assert "未執行 LINE 登入，也未載入正式資料" in preview
    assert "正式 LIFF 入口仍需要身分驗證" in preview
    assert "if (studioPreview) throw new Error" in post_json


def test_mobile_admin_heading_is_target_specific_in_preview_and_formal_modes() -> None:
    source = _source("mobile_admin.html")
    heading = source.split("function applySurfaceHeading", 1)[1].split(
        "function requireCustomerPage", 1
    )[0]
    preview = source.split("function renderStudioPreview", 1)[1].split(
        "function switchPane", 1
    )[0]
    formal = source.split("function switchPane", 1)[1].split(
        "async function loadTickets", 1
    )[0]

    assert 'document.getElementById("title").textContent = copy[0]' in heading
    assert 'document.title = `${copy[0]}｜工會 LINE`' in heading
    assert "applySurfaceHeading(target)" in preview
    assert "applySurfaceHeading(target)" in formal
    assert ".section-heading > div { flex:1 1 0; min-width:0; }" in source
    assert "select,input,textarea { width:100%; min-width:0;" in source
    assert ".toolbar > input, .toolbar > select { flex:1 1 0; width:auto; }" in source
    for label in ("待辦工作台", "客服中心", "狀態追蹤", "營運摘要"):
        assert label in source


def test_mobile_admin_query_routes_use_closed_typed_response_models() -> None:
    source = (ROOT / "api" / "routes" / "line_mobile_admin.py").read_text(encoding="utf-8")

    assert "response_model=BaseResponse[dict]" not in source
    for model in (
        "_MobileAdminProfileView",
        "CustomerServiceSummaryView",
        "CustomerServicePageView",
        "CustomerServiceDetailView",
        "CanonicalLineReviewNumberedPageResponse",
        "CanonicalLineReviewDecisionPreviewResponse",
        "CanonicalLineReviewResponse",
    ):
        assert f"response_model=BaseResponse[{model}]" in source
    assert "response_model=BaseResponse[_SchedulingReviewPreviewView]" in source
    assert "response_model=BaseResponse[_SchedulingReviewOptionsView]" in source
    assert "client_finance_impact" not in source
    assert "payroll_impact" not in source
    assert "orders_impact" not in source


def test_mobile_scheduling_review_uses_line_binding_and_discards_late_forms() -> None:
    route = (ROOT / "api" / "routes" / "line_mobile_admin.py").read_text(encoding="utf-8")
    source = _source("mobile_admin.html")

    assert "require_persisted_admin" not in route
    assert "get_line_identity_management_application" not in route
    assert "get_linked_admin" in route
    scheduling_auth = route.split("def _scheduling_mobile_actor", 1)[1].split(
        "def _mobile_admin_context", 1
    )[0]
    assert "line_identity_bindings" not in scheduling_auth
    assert "LineCapability.REVIEW_DECIDE" in scheduling_auth
    assert "schedulingQuerySequence" in source
    assert "schedulingPreviewSequence" in source
    assert "schedulingFormRevision" in source
    assert "schedulingCaseIdentity" in source
    assert "union_admin_session_token" not in source
    assert "headers.Authorization" not in source
    assert "/admin/#login" not in source
    assert "redirectToAdminLogin" not in source
    assert "const profile = await postJson(\"/api/v1/line/mobile-admin/profile\", {});" in source
    initialize = source.split("async function init()", 1)[1].split(
        "function renderStudioPreview", 1
    )[0]
    assert "adminSessionToken" not in initialize
    assert 'id="mobileAdminContent" class="hidden"' in source
    assert "revealMobileAdmin();" in initialize
    assert 'postJson("/api/v1/line/mobile-admin/client-profile/requests"' in source
    assert 'postJson("/api/v1/line/mobile-admin/staff-leave-requests"' in source
    assert "querySequence !== schedulingQuerySequence" in source
    assert "formRevision !== schedulingFormRevision" in source


def test_mobile_admin_customer_and_review_pagination_use_server_metadata() -> None:
    source = _source("mobile_admin.html")
    customer = source.split("async function loadTickets", 1)[1].split(
        "const ticketStatusLabels", 1
    )[0]
    pagination = source.split("function renderPagination", 1)[1].split(
        "function safeErrorMessage", 1
    )[0]
    review_page = source.split("function requireReviewPage", 1)[1].split(
        "function renderPagination", 1
    )[0]
    reviews = source.split("async function loadIdentityReviews", 1)[1].split(
        "function reviewCard", 1
    )[0]

    assert "page: requestedPage" in customer
    assert "requireCustomerPage(data, requestedPage)" in customer
    assert "querySequence !== ticketQuerySequence" in customer
    assert "requestedPage !== ticketPageState.page" in customer
    assert 'ticketPageState.page = 1' in source
    assert "顯示 ${first}-${last} / ${pageData.total} 件" in pagination
    assert 'previous.disabled = pageData.page <= 1' in pagination
    assert 'next.disabled = pageData.page >= pageData.totalPages' in pagination
    assert "cursor" not in pagination.lower()
    assert "fingerprint" not in pagination.lower()
    assert "provider" not in pagination.lower()
    assert "Number.isInteger(data.page)" in review_page
    assert "Number.isInteger(data.page_size)" in review_page
    assert "Number.isInteger(data.total)" in review_page
    assert "data.page_size !== reviewPageState.pageSize" in review_page
    assert "page: requestedPage" in reviews
    assert "page_size: reviewPageState.pageSize" in reviews
    assert "requireReviewPage(data, requestedPage)" in reviews
    assert "querySequence !== reviewQuerySequence" in reviews
    assert "requestedPage !== reviewPageState.page" in reviews
    assert "renderPagination(root, pageData" in reviews
    assert 'reviewPageState.page = 1' in source
    assert 'reviewStatus").addEventListener("change", () =>' in source


def test_mobile_scheduling_review_forwards_owner_query_preview_apply_and_readback() -> None:
    source = _source("mobile_admin.html")
    assert 'id="openScheduling"' not in source
    assert 'id="backToWorkQueue"' in source
    assert 'id="schedulingPane"' in source
    assert 'id="loadSchedule"' in source
    assert '<select id="scheduleCaseNo"' in source
    assert '<input id="scheduleCaseNo"' not in source
    assert "/api/v1/line/mobile-admin/scheduling-review/options" in source
    assert "/api/v1/line/mobile-admin/scheduling-review/query" in source
    assert "/api/v1/line/mobile-admin/scheduling-review/preview" in source
    assert "/api/v1/line/mobile-admin/scheduling-review/apply" in source
    preview = source.split("async function previewSchedulingReview", 1)[1].split(
        "async function applySchedulingReview", 1
    )[0]
    apply = source.split("async function applySchedulingReview", 1)[1].split(
        "async function loadReviews", 1
    )[0]
    assert "official_service_dates" in preview
    scheduling_form = source.split("function renderSchedulingReview", 1)[1].split(
        "function invalidateSchedulingPreview", 1
    )[0]
    assert 'schedulingSelect("assigned_start_date"' in scheduling_form
    assert 'schedulingSelect("assigned_end_date"' in scheduling_form
    assert "schedulingDateDropdown" in scheduling_form
    assert 'dropdown.dataset.field = "official_service_dates"' in source
    assert 'input.type = "checkbox"' in source
    assert "preview_fingerprint" in apply
    assert "expected_order_version" in apply
    assert "expected_scheduling_version" in apply
    assert "expected_client_finance_version" in apply
    assert "expected_payroll_version" in apply
    assert "data.readback" in apply
    assert "排班已保存，並已重新讀回目前正式排班" in apply
    assert "innerHTML" not in source
