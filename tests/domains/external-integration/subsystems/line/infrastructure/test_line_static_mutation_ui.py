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
    assert "確認上述預覽並套用" in submit
    assert "authentication_pending" in source
    assert "帳密於套用時驗證" in source
    assert "preview.password" not in submit
    assert "JSON.stringify(preview" not in submit
    assert "預覽指紋：" not in submit
    assert "收據：" not in submit
    assert "套用 readback" not in submit


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

    assert "/api/v1/line/identity/registration/preview" in submit
    assert "/api/v1/line/identity/registration/apply" in submit
    assert submit.index("/registration/preview") < submit.index("/registration/apply")
    assert "expected_binding_version" in submit
    assert "preview_fingerprint" in submit
    assert "confirmRegistrationApply" in source
    assert "確認套用這份登記預覽" in source
    assert "registration_id" in submit
    assert "client_id" in submit
    assert "identity_status" in submit


def test_registration_preview_is_invalidated_by_any_form_edit_and_is_deidentified() -> None:
    source = _source("register.html")
    preview_render = source.split("function renderRegistrationPreview", 1)[1].split(
        "function invalidateRegistrationPreview", 1
    )[0]
    invalidation = source.split("function invalidateRegistrationPreview", 1)[1].split(
        "async function applyRegistration", 1
    )[0]

    assert 'addEventListener("input", invalidateRegistrationPreview)' in source
    assert 'addEventListener("change", invalidateRegistrationPreview)' in source
    assert "pendingRegistrationPreview = null" in invalidation
    assert "舊預覽已失效" in invalidation
    assert "payload.name" not in preview_render
    assert "payload.phone" not in preview_render
    assert "payload.id_number" not in preview_render
    assert "payload.address" not in preview_render
    assert "survey_details" not in preview_render
    assert "line_id_token" not in preview_render
    assert "JSON.stringify" not in preview_render
    assert "資料指紋：" not in preview_render
    assert "預期綁定版本：" not in preview_render
    success_render = source.split("successDescription.textContent = [", 1)[1].split(
        "].join('\\n')", 1
    )[0]
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
    assert "client_finance_impact" not in source
    assert "payroll_impact" not in source
    assert "orders_impact" not in source


def test_mobile_scheduling_review_requires_current_session_fact_and_discards_late_forms() -> None:
    route = (ROOT / "api" / "routes" / "line_mobile_admin.py").read_text(encoding="utf-8")
    source = _source("mobile_admin.html")

    assert "require_persisted_admin" in route
    assert "get_line_identity_management_application" in route
    assert "current_fact" in route
    scheduling_auth = route.split("def _scheduling_mobile_actor", 1)[1].split(
        "def _mobile_admin_actor", 1
    )[0]
    assert "line_identity_bindings" not in scheduling_auth
    assert "ActorContext(f\"admin:{admin.admin_user_id}\"" not in scheduling_auth
    assert "schedulingQuerySequence" in source
    assert "schedulingPreviewSequence" in source
    assert "schedulingFormRevision" in source
    assert "schedulingCaseIdentity" in source
    assert "sessionStorage.getItem(\"union_admin_session_token\")" in source
    assert "headers.Authorization" in source
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
    reviews = source.split("async function loadReviews", 1)[1].split(
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
    assert 'id="tabScheduling"' in source
    assert 'id="schedulingPane"' in source
    assert 'id="loadSchedule"' in source
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
    assert "preview_fingerprint" in apply
    assert "expected_order_version" in apply
    assert "expected_scheduling_version" in apply
    assert "expected_client_finance_version" in apply
    assert "expected_payroll_version" in apply
    assert "data.readback" in apply
    assert "排班已保存，並已重新讀回目前正式排班" in apply
    assert "innerHTML" not in source
