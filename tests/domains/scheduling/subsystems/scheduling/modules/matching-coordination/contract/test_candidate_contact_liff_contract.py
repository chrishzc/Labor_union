from pathlib import Path


ROOT = Path(__file__).resolve().parents[8]


def test_candidate_liff_exposes_exact_categories_and_exclusive_no_interest():
    page = (ROOT / "line" / "static" / "candidate_contact.html").read_text(encoding="utf-8")

    for label in (
        "服務地區",
        "服務日期／檔期",
        "每日服務時段",
        "每日服務時數",
        "下廚需求",
        "交通、停車或樓層",
        "個人因素",
        "8. 沒有意願",
    ):
        assert page.count(label) >= 1
    assert "確認資訊" in page
    assert "調整條件" in page
    assert "noInterest.checked = false" in page
    assert "input.checked = false" in page


def test_candidate_and_customer_liff_never_accept_url_line_identity():
    candidate = (ROOT / "line" / "static" / "candidate_contact.html").read_text(encoding="utf-8")
    customer = (ROOT / "line" / "static" / "candidate_contact_customer.html").read_text(encoding="utf-8")

    for page in (candidate, customer):
        assert "liff.getIDToken()" in page
        assert "line_id_token" in page
        assert "userId" not in page
        assert "lineUserId" not in page


def test_liff_gateway_preserves_only_opaque_candidate_reference():
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")

    assert 'target === "candidate_contact"' in identity
    assert 'target === "candidate_contact_customer"' in identity
    assert "^[0-9a-f]{64}$" in identity
    assert "targetPage === 'candidate_contact'" in gateway
    assert "targetPage === 'candidate_contact_customer'" in gateway


def test_candidate_liffs_never_render_structured_api_errors_as_objects():
    pages = (
        (ROOT / "line" / "static" / "candidate_contact.html").read_text(encoding="utf-8"),
        (ROOT / "line" / "static" / "candidate_contact_customer.html").read_text(encoding="utf-8"),
    )

    for page in pages:
        assert "throw new Error(apiErrorMessage(result))" in page
        assert "result?.detail?.error?.message" in page
        assert "result?.detail?.error?.field_errors" in page
        assert 'typeof candidate === "string"' in page
        assert "Array.isArray(fieldErrors)" in page
        assert 'typeof item?.msg === "string"' in page


def test_candidate_liff_customer_binding_failure_has_actionable_message():
    route = (ROOT / "api" / "routes" / "line_candidate_contact.py").read_text(encoding="utf-8")

    assert 'code == "candidate_contact_customer_unavailable"' in route
    assert "此案件客戶尚未綁定 LINE" in route


def test_customer_adjustment_is_handed_to_union_instead_of_redirecting_customer():
    page = (ROOT / "line" / "static" / "candidate_contact_customer.html").read_text(encoding="utf-8")
    route = (ROOT / "api" / "routes" / "line_candidate_contact.py").read_text(encoding="utf-8")

    assert "可以，請工會協助修改" in page
    assert "已通知工會人員。工會完成正式資料修改後，會重新詢問月嫂。" in page
    assert "前往修改訂單" not in page
    assert "已記錄是否可調整，並交由工會人員接續處理。" in route
