"""Real-fact projections, closed action output and zero-effect preview boundaries."""

from contextlib import contextmanager
from dataclasses import asdict
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import admin_actor_context, require_line_configuration_reader
from api.routes import line_message_preview as route
from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from domains.line.canonical_payload import canonical_line_payload_json
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.message_preview import (
    _CURRENT_FLOW_PREVIEWS, LineMessagePreviewApplication, MessagePreviewNotFound, PreviewCase, PreviewLeave,
    PreviewOption, PreviewOptionPage, PreviewStaff,
)


def actor():
    return admin_actor_context(AdminPrincipal(1, "preview-test", "測試", "system_admin"))


class Configuration:
    def __init__(self, template_id="test-template", variables=(), content="案件 {case_no}"):
        self.template_id, self.variables, self.content = template_id, variables, content

    def get(self, kind, _actor):
        definition = {"templates": [{"id": self.template_id, "name": "通知", "enabled": True,
            "message_type": "text", "content": self.content, "variables": [
                {"name": name, "required": True} for name in self.variables]}]} if kind is LineConfigurationKind.MESSAGE_TEMPLATES else {
                    "rules": [{"id": "notice", "template_id": self.template_id}]}
        return LineConfigurationSnapshot(kind, LineConfigurationRevision(3), canonical_line_payload_json(definition))


class Reader:
    def case(self, case_no):
        return PreviewCase(case_no, "林小姐", "2026-11-01", "2026-11-30", "新竹市", "日間", "09:00–17:00") if case_no == "CASE-1" else None

    def staff(self, staff_id):
        return PreviewStaff(7, "陳月嫂", "新竹市", 1, True, ("新竹市",), ("照護",)) if staff_id == 7 else None

    def leave(self, *_):
        return PreviewLeave(21, 3, "2026-11-05", "2026-11-06")

    def service_date(self, *_):
        return "2026-11-12"

    def payment_values(self, *_):
        return {"first_payment_amount": "NT$ 12,600", "first_payment_status": "待繳納"}

    def options(self, kind, search, after):
        return PreviewOptionPage((PreviewOption("CASE-1", "CASE-1｜林小姐"),), None)


@contextmanager
def reader_factory():
    yield Reader()  # Intentionally has no writer, provider, audit or token capability.


def app(configuration=None, factory=reader_factory):
    return LineMessagePreviewApplication(configuration or Configuration(variables=("case_no",)), factory)


def client(monkeypatch, application=None):
    web = FastAPI()
    web.include_router(route.router)
    web.dependency_overrides[require_line_configuration_reader] = lambda: AdminPrincipal(1, "test", "測試", "system_admin")
    monkeypatch.setattr(route, "get_message_preview_application", lambda: application or app())
    return TestClient(web)


def test_missing_subject_does_not_open_database_or_invent_sample_facts():
    def forbidden():
        pytest.fail("missing selection must not open a database connection")
    result = app(factory=forbidden).render("notice", None, None, None, actor())
    assert result.status == "needs_subject" and result.facts == ()


def test_render_uses_selected_facts_and_ephemeral_copy_without_saving():
    configuration = Configuration(variables=("case_no",))
    result = app(configuration).render("notice", "選擇案件 {case_no}", "CASE-1", None, actor())
    assert result.text == "選擇案件 CASE-1"
    assert configuration.content == "案件 {case_no}"
    assert ("客戶", "林小姐") in [(f.id, f.label) for f in result.facts]


def test_case_not_found_is_not_replaced_with_other_case():
    with pytest.raises(MessagePreviewNotFound):
        app().render("notice", None, "missing", None, actor())


def test_capability_is_enforced_inside_application():
    with pytest.raises(PermissionError):
        app().options("case", "", None, ActorContext("unprivileged"))


def test_canonical_flex_preview_strips_all_executable_actions():
    result = app().render("card-customer-profiles", None, "CASE-1", 7, actor())
    assert result.status == "ready" and len(result.bubbles) == 2
    public = json.dumps(asdict(result), ensure_ascii=False)
    assert "陳月嫂" in public and "CASE-1" in public
    for forbidden in ('"uri"', '"data"', '"line_user_id"', '"token"', "preview-only"):
        assert forbidden not in public
    assert "不會執行" in public


def test_real_leave_dates_are_required_and_used():
    application = app(Configuration("LU96-M1-LEAVE-EXTENSION-CARD-V1", (), "請確認安排"))
    result = application.render("notice", "新的說明", "CASE-1", None, actor())
    public = json.dumps(asdict(result), ensure_ascii=False)
    assert "2026-11-05" in public and "2026-11-06" in public and "新的說明" in public
    class NoLeave(Reader):
        def leave(self, *_):
            return None
    @contextmanager
    def no_leave():
        yield NoLeave()
    missing = app(application._configuration, no_leave).render("notice", None, "CASE-1", None, actor())
    assert missing.status == "unavailable" and missing.bubbles == ()


def test_payment_render_consumes_owner_formatted_values():
    result = app(Configuration(variables=("first_payment_amount", "first_payment_status"),
        content="{first_payment_amount}；{first_payment_status}")).render("notice", None, "CASE-1", None, actor())
    assert result.text == "NT$ 12,600；待繳納"


def test_http_preview_is_closed_and_no_store(monkeypatch):
    web = client(monkeypatch)
    response = web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "case_no": "CASE-1"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"]["text"] == "案件 CASE-1"
    assert web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "send": True}).status_code == 422
    assert web.get("/api/v1/line/message-previews/subjects?kind=staff&after=not-a-number").status_code == 422
    assert web.get("/api/v1/line/message-previews/subjects?kind=unsafe").status_code == 422


def test_failed_query_is_closed_without_raw_database_detail(monkeypatch):
    class Failed:
        def options(self, *_):
            raise RuntimeError("private database error")
    response = client(monkeypatch, Failed()).get("/api/v1/line/message-previews/subjects?kind=case")
    assert response.status_code == 503
    assert "private database error" not in response.text


def test_reader_boundary_is_read_only_and_always_rolled_back(monkeypatch):
    from infrastructure.mysql.line_message_preview_repository import open_message_preview_reader
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=None): calls.append((sql, params))
        def fetchall(self): return []
    class Connection:
        def cursor(self): return Cursor()
        def rollback(self): calls.append(("rollback", None))
        def close(self): calls.append(("close", None))
        def commit(self): pytest.fail("preview must never commit")
    monkeypatch.setattr("infrastructure.mysql.mysql_adapter.get_connection", lambda: Connection())
    with open_message_preview_reader() as reader:
        assert reader.options("case", "'; DELETE FROM orders;--", None).items == ()
    assert calls[0][0] == "START TRANSACTION READ ONLY"
    assert "DELETE" not in calls[1][0] and "DELETE" in calls[1][1][1]
    assert [c[0] for c in calls[-2:]] == ["rollback", "close"]


def test_rejected_authentication_never_constructs_preview_application(monkeypatch):
    web = FastAPI()
    web.include_router(route.router)
    def deny(): raise HTTPException(403, "denied")
    web.dependency_overrides[require_line_configuration_reader] = deny
    monkeypatch.setattr(route, "get_message_preview_application", lambda: pytest.fail("authorization must precede reader construction"))
    assert TestClient(web).post("/api/v1/line/message-previews/preview", json={"id": "notice"}).status_code == 403


def test_registered_preview_bypasses_mutation_audit_for_success_and_validation_failure(monkeypatch):
    from fastapi import Request
    from api.main import app as main_app
    import api.main as main

    def authenticated(request: Request):
        principal = AdminPrincipal(1, "test", "測試", "system_admin")
        request.state.admin_principal = principal
        return principal
    monkeypatch.setattr(route, "get_message_preview_application", lambda: app())
    monkeypatch.setattr(main, "record_admin_audit", lambda **_: pytest.fail("preview must not append mutation audit"))
    previous = main_app.dependency_overrides.get(require_line_configuration_reader)
    main_app.dependency_overrides[require_line_configuration_reader] = authenticated
    try:
        web = TestClient(main_app)
        assert web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "case_no": "CASE-1"}).status_code == 200
        assert web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "send": True}).status_code == 422
    finally:
        if previous is None:
            main_app.dependency_overrides.pop(require_line_configuration_reader, None)
        else:
            main_app.dependency_overrides[require_line_configuration_reader] = previous


def test_catalog_includes_formal_sources_without_retired_or_unowned_test_templates():
    from subsystems.line.configuration_store import read_raw_config
    templates = read_raw_config("message_templates")
    catalog = LineMessagePreviewApplication._catalog(templates, {"rules": [
        {"id": "retired", "template_id": "new_user_d1"},
    ]})
    ids = {entry.id for entry in catalog}
    assert {"card-customer-confirmation", "card-union-question", "card-union-answer",
            "card-candidate-information-1", "card-candidate-information-2", "card-candidate-information-3",
            "service-menu", "order-update-menu", "service-contact", "service-resolved", "identity-bound",
            "template-register_success", "template-staff_verification_requested"} <= ids
    assert not {"retired", "template-new_user_d1", "template-new_user_d2", "template-new_user_d3", "template-v"} & ids


@pytest.mark.parametrize("key", ["service-menu", "order-update-menu", "service-contact", "service-resolved", "identity-pending", "identity-bound", "service-flow", "service-payment", "service-profile-update", "service-order-update", "service-other"])
def test_fixed_runtime_messages_need_no_database_and_expose_no_actions(key):
    def forbidden():
        pytest.fail("fixed runtime message must not read subjects or create an interaction")
    result = app(factory=forbidden).render(key, None, None, None, actor())
    assert result.status == "ready"
    public = json.dumps(asdict(result), ensure_ascii=False)
    for forbidden_value in ('"uri"', '"data"', '"token"', "liff.line.me"):
        assert forbidden_value not in public
    if key == "identity-bound":
        assert result.text == "綁定成功，專屬選單將稍後更新。"


@pytest.mark.parametrize("key", ["card-union-question", "card-union-answer"])
def test_manual_copy_is_only_a_preview_draft_using_the_real_case(key):
    empty = app().render(key, "", "CASE-1", 7, actor())
    assert empty.status == "unavailable" and not empty.bubbles
    result = app().render(key, "請協助確認服務條件。", "CASE-1", 7, actor())
    public = json.dumps(asdict(result), ensure_ascii=False)
    assert result.status == "ready" and "請協助確認服務條件。" in public
    assert "preview.invalid" not in public and "preview-only" not in public
    assert "不會執行" in public


@pytest.mark.parametrize("key", ["card-customer-confirmation", "card-candidate-information-1", "card-candidate-information-2", "card-candidate-information-3"])
def test_formal_package_cannot_fall_back_to_an_unrelated_staff_or_invented_data(key):
    class NoPackage(Reader):
        def card(self, case_no, staff_id, kind):
            assert (case_no, staff_id, kind) == ("CASE-1", 7, key)
            return None
    @contextmanager
    def factory():
        yield NoPackage()
    result = app(factory=factory).render(key, None, "CASE-1", 7, actor())
    assert result.status == "unavailable" and not result.bubbles


def test_confirmation_uses_read_only_owner_projection_without_generating_resume_tokens(monkeypatch):
    from infrastructure.mysql.line_message_preview_repository import MySqlLineMessagePreviewReader
    class Repository:
        def __init__(self, _): pass
        def customer_confirmation_package(self, *_): pytest.fail("locked Apply projection is forbidden")
        def customer_confirmation_preview(self, *_):
            return {"blockers": (), "order_information_1": ({"text": "正式資訊一"},),
                "order_information_2": ({"text": "正式資訊二"},), "weekly_service_rows": (),
                "caregiver_resumes": ({"staff_id": 7},)}
        def customer_profile_facts(self, *_): return (asdict(Reader().staff(7)),)
    monkeypatch.setattr("infrastructure.mysql.matching_notification_repository.MySqlMatchingNotificationRepository", Repository)
    reader = MySqlLineMessagePreviewReader(object())
    monkeypatch.setattr(reader, "_one", lambda sql, params: {"id": 12})
    source = reader.card("CASE-1", 7, "card-customer-confirmation")
    payload = json.loads(source.payload_json)
    assert len(payload["contents"]["contents"]) == 5
    from subsystems.line.message_preview import _project_node
    display = json.dumps([asdict(_project_node(b)) for b in payload["contents"]["contents"]], ensure_ascii=False)
    assert "正式資訊一" in display and "下載履歷 PDF" in display
    assert "preview.invalid" not in display and "preview-only" not in display


def test_bootstrap_copy_matches_current_registration_binding_and_welcome_semantics():
    from subsystems.line.configuration_store import read_raw_config
    from subsystems.line.webhook_identity_handlers import DEFAULT_ONBOARDING_WELCOME_MESSAGE
    templates = {t["id"]: t for t in read_raw_config("message_templates")["templates"]}
    assert templates["customer_onboarding_welcome"]["content"] == DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "一般留言不會有專員回覆" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "【AI 智慧問答】" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "【聯絡專人服務】" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert "瀏覽常見問答" in DEFAULT_ONBOARDING_WELCOME_MESSAGE
    assert templates["register_success"]["content"] == "申請已送出，待工會核准。"
    assert templates["bind_success_new_order"]["content"] == "綁定成功，專屬選單將稍後更新。"
    assert "status_code" not in templates["staff_switch_fail"]["content"]


@pytest.mark.parametrize("key", ["notice", "card-caregiver-information", "card-caregiver-information-2",
    "card-customer-profiles", "card-customer-confirmation", "card-candidate-information-1",
    "card-candidate-information-2", "card-candidate-information-3", "card-union-question", "card-union-answer"])
def test_public_examples_render_without_subject_database_or_eligibility(key):
    def forbidden():
        pytest.fail("public examples must never query real case or staff eligibility")
    result = app(factory=forbidden).render(key, None, "not-a-real-case", 999999, actor(), sample=True)
    assert result.status == "ready" and "公版" in result.note
    bindings = {fact.id: fact.label for fact in result.facts}
    assert bindings["案件編號（case_no）"] == "DEMO-CASE-001"
    public = json.dumps(asdict(result), ensure_ascii=False)
    for forbidden_value in ("not-a-real-case", "999999", "preview-only", "preview.invalid", '"uri"', '"token"', '"data"'):
        assert forbidden_value not in public


def test_public_template_bindings_match_only_used_fields_and_substitution_values():
    application = app(Configuration(variables=("case_no", "first_payment_amount", "service_date"),
        content="{case_no}／{first_payment_amount}／{service_date}"))
    result = application.render("notice", None, None, None, actor(), sample=True)
    assert result.text == "DEMO-CASE-001／NT$ 12,000／2026-11-03"
    assert {fact.label for fact in result.facts} == {"DEMO-CASE-001", "NT$ 12,000", "2026-11-03"}
    assert len(result.facts) == 3


def test_public_leave_uses_explicit_example_dates_and_copy():
    result = app(Configuration("LU96-M1-LEAVE-EXTENSION-CARD-V1", (), "請確認本次安排。")) \
        .render("notice", "公版測試說明", None, None, actor(), sample=True)
    assert result.status == "ready"
    bindings = {fact.id: fact.label for fact in result.facts}
    assert bindings["請假開始日（leave_start_date）"] == "2026-11-10"
    assert bindings["通知說明（description）"] == "公版測試說明"
    assert "2026-11-10" in json.dumps(asdict(result), ensure_ascii=False)


def test_http_public_sample_ignores_subjects_and_never_opens_record_reader(monkeypatch):
    def forbidden():
        pytest.fail("public sample must not open record reader")
    web = client(monkeypatch, app(factory=forbidden))
    response = web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "data_source": "sample"})
    assert response.status_code == 200 and response.json()["data"]["text"] == "案件 DEMO-CASE-001"
    assert web.post("/api/v1/line/message-previews/preview", json={"id": "notice", "data_source": "unknown"}).status_code == 422


def test_public_cards_keep_canonical_information_fields_and_disclose_their_values():
    result = app().render("card-candidate-information-2", None, None, None, actor(), sample=True)
    display = json.dumps([asdict(bubble) for bubble in result.bubbles], ensure_ascii=False)
    assert "飲食與照護需求" in display and "公版" in result.note
    assert "清淡飲食（範例）" in display
    assert any(fact.label == "清淡飲食（範例）" for fact in result.facts)
    two = app().render("card-caregiver-information-2", None, None, None, actor(), sample=True)
    assert any(fact.id == "服務縣市（city）" and fact.label == "新竹市" for fact in two.facts)


def test_retired_zero_pool_cannot_render_even_if_legacy_rule_remains():
    configuration = Configuration(template_id="LU96-M3-ZERO-POOL-CARD-V1")
    application = app(configuration)
    assert all(item.template_id != "LU96-M3-ZERO-POOL-CARD-V1" for item in application.catalog(actor()))
    with pytest.raises(MessagePreviewNotFound):
        application.render("notice", None, None, None, actor(), sample=True)


@pytest.mark.parametrize("key", [row[0] for row in _CURRENT_FLOW_PREVIEWS])
def test_current_flow_messages_render_publicly_without_subjects_or_side_effect_capabilities(key):
    def forbidden():
        pytest.fail("public flow preview cannot open a real-subject reader")
    application = app(factory=forbidden)
    result = application.render(key, None, None, None, actor(), sample=True)
    assert result.status == "ready"
    assert result.text or result.bubbles
    for bubble in result.bubbles:
        serialized = json.dumps(asdict(bubble), ensure_ascii=False)
        assert "https://" not in serialized and "postback" not in serialized
    assert application.render(key, None, None, None, actor()).status == "unavailable"


def test_deposit_and_service_progress_disclose_actual_public_substitutions():
    application = app()
    reminder = application.render("deposit-reminder", None, None, None, actor(), sample=True)
    assert "6,000" in json.dumps(asdict(reminder), ensure_ascii=False)
    fields = {fact.id:fact.label for fact in reminder.facts}
    assert fields["訂金金額（新臺幣）（amount_ntd）"] == "6000"
    assert fields["繳費期限（due_date）"] == "2026-11-01"
    settled = application.render("deposit-settled", None, None, None, actor(), sample=True)
    assert "已確認入帳" in json.dumps(asdict(settled), ensure_ascii=False)
    assert all("due_date" not in fact.id for fact in settled.facts)
    progress = application.render("service-progress", None, None, None, actor(), sample=True)
    assert "DEMO-CASE-001" in progress.text and "訂單成立" in progress.text
    assert len(progress.facts) == 4
