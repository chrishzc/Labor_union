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
    from infrastructure.line.table_image_renderer import render_table_image
    return LineMessagePreviewApplication(configuration or Configuration(variables=("case_no",)), factory, render_table_image)


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


def test_general_question_preview_is_current_self_service_menu():
    application = app()
    other = application.render('service-other', None, None, None, actor(), sample=True)
    menu = application.render('service-menu', None, None, None, actor(), sample=True)
    assert other.format == 'flex' and other.bubbles == menu.bubbles
    assert 'service-other' not in {entry.id for entry in application.catalog(actor())}


@pytest.mark.parametrize('key', ['service-flow', 'service-payment'])
def test_retired_explanations_are_not_listed_or_previewed(key):
    application = app()
    catalog = application.catalog(actor())
    assert key not in {item.id for item in catalog}
    assert {'service-profile-update', 'service-order-update'} <= {item.id for item in catalog}
    with pytest.raises(MessagePreviewNotFound):
        application.render(key, None, None, None, actor(), sample=True)


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


def test_retired_customer_leave_confirmation_is_not_renderable():
    application = app(Configuration("LU96-M1-LEAVE-EXTENSION-CARD-V1", (), "請確認安排"))
    with pytest.raises(MessagePreviewNotFound):
        application.render("notice", None, None, None, actor(), sample=False)


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
        {"id": "old-admin-health", "template_id": "LU96-M4-SAFE-ALERT-CARD-V1"},
        {"id": "old-complaint", "template_id": "LU96-M4-COMPLAINT-HIGH-CARD-V1"},
    ]})
    ids = {entry.id for entry in catalog}
    assert {"card-customer-confirmation", "card-union-question", "card-union-answer",
            "card-candidate-information-1", "card-candidate-information-2", "card-candidate-information-3",
            "service-menu", "order-update-menu", "service-contact", "service-resolved", "identity-bound-customer", "identity-bound-staff", "identity-bound-admin",
            "template-client_rebind_rejected", "template-staff_verification_rejected"} <= ids
    assert not {"retired", "template-new_user_d1", "template-new_user_d2", "template-new_user_d3", "template-v"} & ids
    assert {entry.id for entry in catalog if entry.format == 'flex' and entry.name.startswith('正式媒合－')} == {'card-customer-confirmation'}
    assert not {'card-caregiver-information', 'card-caregiver-information-2', 'card-customer-profiles'} & ids
    assert not {'runtime-system-health', 'old-admin-health', 'old-complaint'} & ids


def test_unused_identity_templates_are_hidden_without_removing_rule_backed_notifications():
    from subsystems.line.configuration_store import read_raw_config
    from copy import deepcopy
    templates = read_raw_config('message_templates')
    before = deepcopy(templates)
    unused = {'staff_switch_fail','staff_menu_not_set','esc_success','esc_fail','bind_link_msg',
              'register_success','bind_success_existing','bind_confirm_rebind','bind_fail_no_data',
              'client_rebind_approved','staff_verification_requested'}
    catalog = LineMessagePreviewApplication._catalog(templates, {'rules': [
        {'id': 'configured-active-notification', 'template_id': 'register_success'}]})
    assert not {'template-' + key for key in unused} & {item.id for item in catalog}
    assert 'configured-active-notification' in {item.id for item in catalog}
    assert templates == before


def test_start_day_group_card_public_preview_has_copy_and_inert_buttons_only():
    from pathlib import Path
    class CurrentConfiguration:
        def get(self,kind,_actor):
            definition=json.loads(Path(f'config/{kind.value}.json').read_text(encoding='utf-8'))
            return LineConfigurationSnapshot(kind,LineConfigurationRevision(1),canonical_line_payload_json(definition))
    def forbidden_reader():
        pytest.fail('public preview must not access real identities or create an inquiry')
    application=LineMessagePreviewApplication(CurrentConfiguration(),forbidden_reader)
    result=application.render('LINE-ORDER-SERVICE-START-DAY-V1',None,None,None,actor(),sample=True)
    public=json.dumps(asdict(result),ensure_ascii=False)
    assert result.status=='ready'
    assert '今天是本案的服務開始日' in public and '服務正常' in public and '需要協助' in public
    assert '3 天後' not in public and 'start-day:' not in public
    assert application.render('LINE-ORDER-SERVICE-START-DAY-V1',None,None,None,actor()).status=='unavailable'


@pytest.mark.parametrize('key,phrase',[
    ('LINE-SECOND-PAYMENT-DUE-V1','第二期款尚待繳納 24,000 元'),
    ('LINE-SECOND-PAYMENT-SETTLED-V1','第二期款 24,000 元已確認入帳'),
    ('LINE-SERVICE-COMPLETION-V1','請填寫服務滿意度問卷'),
])
def test_second_payment_public_preview_is_short_group_copy_without_actions(key,phrase):
    from pathlib import Path
    class CurrentConfiguration:
        def get(self,kind,_actor):
            definition=json.loads(Path(f'config/{kind.value}.json').read_text(encoding='utf-8'))
            return LineConfigurationSnapshot(kind,LineConfigurationRevision(1),canonical_line_payload_json(definition))
    def forbidden_reader():pytest.fail('sample must not access identities, create jobs or call a provider')
    application=LineMessagePreviewApplication(CurrentConfiguration(),forbidden_reader)
    result=application.render(key,None,None,None,actor(),sample=True)
    assert result.status=='ready' and result.format=='text' and phrase in result.text
    assert not result.bubbles
    assert application.render(key,None,None,None,actor()).status=='unavailable'


@pytest.mark.parametrize("key", ["service-menu", "order-update-menu", "service-contact", "service-resolved", "identity-pending", "identity-bound-customer", "identity-bound-staff", "identity-bound-admin", "service-profile-update", "service-order-update", "service-other"])
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
            return {"blockers": (), "order_information_1": ({"text": "正式資訊一", 'line_sections': ({'title': '服務', 'rows': (('時段', '正式資訊一'),)},)},),
                "order_information_2": ({"text": "正式資訊二", 'line_sections': ({'title': '需求', 'rows': (('餐點', '正式資訊二'),)},)},), "weekly_service_rows": (),
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


def test_retired_customer_leave_confirmation_has_no_public_example():
    application = app(Configuration("LU96-M1-LEAVE-EXTENSION-CARD-V1", (), "請確認安排"))
    with pytest.raises(MessagePreviewNotFound):
        application.render("notice", None, None, None, actor(), sample=True)


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
    assert 'data:image/png;base64,' in display and "公版" in result.note
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


@pytest.mark.parametrize('key,decision', [
    ('service-start-normal-received', 'normal'),
    ('service-start-help-received', 'help'),
])
def test_start_day_acknowledgement_preview_reuses_committed_group_copy(key, decision, monkeypatch):
    from subsystems.line import service_start_day
    expected = service_start_day.start_day_response_text(decision)
    application = app(factory=lambda: pytest.fail('fixed reply must not open a real reader'))
    result = application.render(key, None, None, None, actor(), sample=True)
    assert result.status == 'ready' and result.text == expected and result.facts == ()
    monkeypatch.setattr(service_start_day, 'start_day_response_text', lambda actual: f'共用回覆：{actual}')
    assert application.render(key, None, None, None, actor(), sample=True).text == f'共用回覆：{decision}'


def test_substitute_and_date_record_preview_disclose_sparse_dates_and_caregiver():
    application = app()
    dates = '2026-11-02、2026-11-04、2026-11-06'
    inquiry = application.render('service-start-inquiry', None, None, None, actor(), sample=True)
    public = json.dumps(asdict(inquiry), ensure_ascii=False)
    assert '服務日期：' + dates in public and '服務期間：' not in public
    assert '2026-11-03' not in public
    assert {fact.id: fact.label for fact in inquiry.facts}['服務日期（service_dates）'] == dates
    record = application.render('service-start-result', None, None, None, actor(), sample=True)
    fields = {fact.id: fact.label for fact in record.facts}
    assert fields['服務日期（assignments[0].service_dates）'] == dates
    assert fields['月嫂姓名（assignments[0].staff_name）'] in record.text
    assert dates in record.text


def test_current_group_preview_names_use_case_group_terminology():
    names = [item.name for item in app().catalog(actor()) if item.id.startswith('group-')]
    assert names and all('服務群組' not in name for name in names)
    assert set(names) == {'案件群組邀請卡－客戶', '案件群組邀請卡－月嫂'}


def test_signing_and_each_overdue_preview_use_real_owner_copy_and_distinct_period_amounts():
    application=app()
    client=application.render('contract-signing-client',None,None,None,actor(),sample=True)
    staff=application.render('contract-signing-staff',None,None,None,actor(),sample=True)
    assert client.text == staff.text and '外部簽約平台' in client.text
    assert any(fact.label=='客戶私人聊天室' for fact in client.facts)
    assert any(fact.label=='月嫂私人聊天室' for fact in staff.facts)
    for stage,label,amount,recipient in [('deposit','訂金','6,000','客戶私人聊天室'),('first','第一期款','12,000','案件群組'),('second','第二期款','8,000','案件群組')]:
        result=application.render('payment-overdue-'+stage,None,None,None,actor(),sample=True)
        assert label in result.text and amount in result.text
        assert any(fact.label==recipient for fact in result.facts)


def test_all_current_builtin_messages_have_editable_copy_and_genesis_is_not_mutated():
    from subsystems.line.message_copy_catalog import default_copy_templates, effective_copy_definition
    defaults = default_copy_templates()
    original = {"templates": []}
    effective = effective_copy_definition(original)
    for entry in app().catalog(actor()):
        if entry.id == 'card-candidate-information-3':
            assert entry.id not in defaults
            continue
        if entry.builtin and entry.template_id is None:
            assert entry.id in defaults, entry.id
    effective["templates"][0]["content"] = "只修改候選設定"
    assert original == {"templates": []}
    assert next(iter(defaults.values()))["content"] != "只修改候選設定"


@pytest.mark.parametrize("reviewed", [False, True])
def test_each_identity_success_uses_its_own_saved_copy_and_keeps_existing_tasks(reviewed):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from domains.line.identities import LineUserId, LineReviewRequestId
    from domains.line.identity_binding import LineBindingSubjectType
    from domains.line.review import LineReviewStatus
    from shared_kernel.identities import CorrelationId
    from subsystems.line.identity_application import _enqueue_result_message
    from subsystems.line.identity_review_application import _enqueue_decision_message
    from subsystems.line.identity_contracts import LineIdentityApplyResult, LineIdentityApplyStatus
    from subsystems.line.message_copy import IDENTITY_SUCCESS_TEMPLATES
    from subsystems.line.message_copy_catalog import effective_copy_definition
    definition = effective_copy_definition({"templates": []})
    texts = {"customer": "客戶：請查看案件進度", "staff": "月嫂：請補齊可服務時段", "admin": "工會：請查看待辦"}
    for template in definition["templates"]:
        role = next((role for role, identifier in IDENTITY_SUCCESS_TEMPLATES.items() if identifier == template["id"]), None)
        if role:
            template["content"] = texts[role]
    tasks = []
    unit = SimpleNamespace(configurations=SimpleNamespace(get=lambda kind: LineConfigurationSnapshot(kind, LineConfigurationRevision(8), canonical_line_payload_json(definition))),
                           delivery_tasks=SimpleNamespace(enqueue=tasks.append, exists_for_key=lambda key: any(task.idempotency_key == key for task in tasks)))
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for role in LineBindingSubjectType:
        if reviewed:
            snapshot = SimpleNamespace(status=LineReviewStatus.APPROVED, subject_type=role, line_user_id=LineUserId("U" + role.value))
            command = SimpleNamespace(request_id=LineReviewRequestId(1), idempotency_key=SimpleNamespace(value="review-" + role.value), correlation_id=CorrelationId("review-copy"))
            _enqueue_decision_message(unit, snapshot, command, now)
        else:
            result = LineIdentityApplyResult(LineIdentityApplyStatus.BOUND, LineUserId("U" + role.value), role, "1")
            _enqueue_result_message(unit, result, CorrelationId("identity-copy"), now)
    assert [json.loads(task.payload_json)["text"] for task in tasks] == list(texts.values())
    frozen = tasks[0].payload_json
    next(t for t in definition["templates"] if t["id"] == IDENTITY_SUCCESS_TEMPLATES["customer"])["content"] = "新的客戶文案"
    assert tasks[0].payload_json == frozen
    if not reviewed:
        result = LineIdentityApplyResult(LineIdentityApplyStatus.BOUND, LineUserId("Ucustomer"), LineBindingSubjectType.CUSTOMER, "1")
        _enqueue_result_message(unit, result, CorrelationId("identity-copy-replay"), now)
        assert len(tasks) == 3


def test_card_copy_handles_multiple_profiles_without_overwriting_data_or_actions():
    from copy import deepcopy
    from subsystems.scheduling.matching_line_cards import customer_profiles_card
    from subsystems.line.message_copy_catalog import default_copy_templates, effective_copy_definition, render_copy_payload
    definition = effective_copy_definition({"templates": []})
    key = "card-customer-profiles"
    default = default_copy_templates()[key]
    template = next(t for t in definition["templates"] if t["id"] == default["id"])
    values = json.loads(template["content"])
    for field in default["copy_fields"]:
        if field["content"] == "請確認配對方案":
            values[field["id"]] = "請核對推薦結果"
        if field["content"] == "接受此配對":
            values[field["id"]] = "確認選擇"
    template["content"] = json.dumps(values, ensure_ascii=False)
    profiles = [{"id": i, "name": name, "city": "新竹市", "care_babies": i, "service_regions": ["新竹市"], "special_skills": []} for i, name in ((1, "王月嫂"), (2, "林月嫂"))]
    payload = json.loads(customer_profiles_card("CASE-7", profiles, "original-action-token", "逐案說明不可被共用文案取代"))
    before = deepcopy(payload)
    result = render_copy_payload(definition, key, payload, {"case_no": "CASE-7"})
    assert payload == before
    assert result["contents"]["contents"][:2] == before["contents"]["contents"][:2]
    decision = result["contents"]["contents"][-1]
    assert decision["body"]["contents"][0]["text"] == "請核對推薦結果"
    assert decision["body"]["contents"][2]["text"] == "逐案說明不可被共用文案取代"
    action = decision["footer"]["contents"][0]["action"]
    assert action["label"] == "確認選擇"
    assert action["data"] == before["contents"]["contents"][-1]["footer"]["contents"][0]["action"]["data"]


def test_configuration_owner_rejects_malformed_card_copy_from_any_writer():
    from subsystems.line.message_configuration import validate_message_templates, LineMessageConfigurationError
    from subsystems.line.message_copy_catalog import effective_copy_definition, default_copy_templates
    definition = effective_copy_definition({"templates": []})
    identifier = default_copy_templates()["service-menu"]["id"]
    template = next(t for t in definition["templates"] if t["id"] == identifier)
    template["content"] = "這不是卡片文案欄位集合"
    with pytest.raises(LineMessageConfigurationError):
        validate_message_templates(definition)


def test_progress_without_owner_context_does_not_invent_case_facts_from_copy_defaults():
    from types import SimpleNamespace
    from subsystems.line.service_help_application import LineServiceHelpApplication, _progress_payload
    from subsystems.line.message_copy_catalog import effective_copy_definition
    definition = effective_copy_definition({"templates": []})
    unit = SimpleNamespace(customer_service=SimpleNamespace(latest_client_case=lambda user: None),
        configurations=SimpleNamespace(get=lambda kind: LineConfigurationSnapshot(kind, LineConfigurationRevision(1), canonical_line_payload_json(definition))))
    result = LineServiceHelpApplication(lambda: None)._progress_payload(None, unit, SimpleNamespace(value="U-copy-test"))
    assert result == _progress_payload(None)
    assert "最新案件" not in result["text"]


def test_every_builtin_card_supports_free_paragraphs_without_changing_provider_actions():
    from subsystems.line.message_copy_catalog import _card_defaults, default_copy_templates, render_copy_payload
    def actions(node):
        if isinstance(node, dict):
            if 'action' in node:
                yield node['action']
            for value in node.values():
                yield from actions(value)
        elif isinstance(node, list):
            for value in node:
                yield from actions(value)
    for key, template in default_copy_templates().items():
        if not template.get('copy_fields'):
            continue
        bodies = [field for field in template['copy_fields'] if field['kind'] == 'body']
        assert bodies, key
        assert any(field['kind'] == 'title' for field in template['copy_fields']), key
        values = json.loads(template['content'])
        for field in bodies:
            values[field['id']] = '第一段自訂說明。\n\n另外增加的提醒段落。'
        payload = _card_defaults()[key]
        variables = {v['name']: 'DEMO-001' for v in template['variables']}
        result = render_copy_payload({'templates': []}, key, payload, variables, json.dumps(values))
        assert '另外增加的提醒段落。' in json.dumps(result, ensure_ascii=False), key
        assert list(actions(result)) == list(actions(payload)), key


def test_new_customer_description_is_only_added_to_the_final_decision_with_multiple_profiles():
    from subsystems.line.message_copy_catalog import default_copy_templates, render_copy_payload
    from subsystems.scheduling.matching_line_cards import customer_confirmation_card
    profiles = tuple({'id': index, 'name': f'月嫂{index}'} for index in range(1, 5))
    payload = json.loads(customer_confirmation_card('CASE-7', profiles, (), (), (), {}, 'real-token', '本案說明'))
    template = default_copy_templates()['card-customer-confirmation']
    values = json.loads(template['content'])
    body = next(field for field in template['copy_fields'] if field['kind'] == 'body')
    values[body['id']] = '請確認 {case_no}\n\n可自行加上其他說明。'
    title = next(field for field in template['copy_fields'] if field['kind'] == 'title')
    values[title['id']] = '我修改的確認標題'
    result = render_copy_payload({'templates': []}, 'card-customer-confirmation', payload, {'case_no': 'CASE-7'}, json.dumps(values))
    before, after = payload['contents']['contents'], result['contents']['contents']
    assert after[:-1] == before[:-1]
    assert after[-1]['footer'] == before[-1]['footer']
    assert after[-1]['body']['contents'][-1]['text'] == '請確認 CASE-7\n\n可自行加上其他說明。'
    assert after[-1]['body']['contents'][0]['text'] == '我修改的確認標題'


def test_old_card_copy_preserves_its_saved_title_while_the_new_description_is_empty():
    from subsystems.line.message_copy_catalog import default_copy_templates, effective_copy_definition
    from copy import deepcopy
    template = default_copy_templates()['card-customer-confirmation']
    values = {field['id']: field['content'] for field in template['copy_fields'] if 'append_to' not in field}
    title = next(field['id'] for field in template['copy_fields'] if field['kind'] == 'title')
    values[title] = '先前維護過的標題'
    original = {'templates': [{**template, 'content': json.dumps(values)}]}
    before = deepcopy(original)
    result = effective_copy_definition(original)
    current = json.loads(result['templates'][0]['content'])
    assert current[title] == '先前維護過的標題'
    body = next(field['id'] for field in template['copy_fields'] if field['kind'] == 'body')
    assert current[body] == ''
    assert original == before


def test_fixed_operator_feedback_and_admin_alerts_have_no_catalog_or_default_copy():
    from subsystems.line.message_copy_catalog import default_copy_templates
    from subsystems.line.configuration_store import read_raw_config
    keys = {'group-bound','group-invitations-queued','group-error-invitation-url','group-format-invite',
            'group-error-admin','group-error-order','group-error-unbound','group-error-identity',
            'group-error-cancelled','group-error-unpaid','group-error-occupied','group-format-empty',
            'group-format-case','group-format-url','group-format-spacing','group-format-split',
            'group-format-invalid-case','group-format-invalid-url','runtime-system-health'}
    from pathlib import Path
    rules = json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    catalog = LineMessagePreviewApplication._catalog(read_raw_config('message_templates'),rules)
    ids = {item.id for item in catalog}
    assert not keys & ids and not keys & set(default_copy_templates())
    assert {'group-invitation-customer','group-invitation-staff','service-order-update','service-profile-update'} <= ids
    assert not {'LU96-M4-SAFE-ALERT-RULE-V1','LU96-M4-COMPLAINT-HIGH-RULE-V1'} & ids
    for key in keys:
        with pytest.raises(MessagePreviewNotFound):
            app().render(key,None,None,None,actor(),sample=True)
