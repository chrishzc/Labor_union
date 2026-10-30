"""Table picture snapshots, independent actions and the scoped read boundary."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from infrastructure.line.table_image_renderer import render_table_image
from subsystems.line.table_image_contracts import TableDocument, TableSection, information_document
from subsystems.line.table_image_links import image_url, image_claim
from subsystems.line.table_image_messages import with_table_images, DOCUMENTS_KEY
from subsystems.line.table_image_query import LineTableImageQuery, TableImageNotFound
from subsystems.scheduling.matching_line_cards import candidate_contact_information_card, customer_confirmation_card

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv('LINE_PUBLIC_BASE_URL', 'https://pictures.example.invalid')
    monkeypatch.setenv('MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET', 'table-image-test-key-not-a-production-secret')


def document():
    return TableDocument('訂單資訊－1', 'DEMO-001', (
        TableSection('服務約定', ('項目', '內容'), (('服務日期', '2026-12-09 ～ 2027-01-07'), ('備註', '完整長內容' * 50))),))


def token(key='delivery:demo', index=0):
    return urlsplit(image_url(key, index, NOW)).path.rsplit('/', 1)[-1]


def test_links_hide_source_identity_and_are_authenticated_expiring_and_purpose_bound():
    reference = token('delivery:private-case-reference')
    assert 'private-case-reference' not in reference
    assert image_claim(reference, NOW)['key'] == 'delivery:private-case-reference'
    with pytest.raises(ValueError):
        image_claim(reference, NOW + timedelta(days=7))
    changed = reference[:20] + ('a' if reference[20] != 'a' else 'b') + reference[21:]
    for invalid in (changed, reference.replace('lti_', 'mcf_', 1), 'invalid', 'lti_' + 'a' * 1600):
        with pytest.raises(ValueError):
            image_claim(invalid, NOW)


def test_invalid_link_never_opens_a_database():
    def forbidden():
        pytest.fail('invalid bearer link must be rejected before opening a database')
    with pytest.raises(TableImageNotFound):
        LineTableImageQuery(forbidden, render_table_image, lambda: NOW).read('invalid')


@pytest.mark.parametrize('environment', ['production', 'development'])
def test_picture_links_require_the_existing_configured_secret_without_a_known_dev_key(monkeypatch, environment):
    from subsystems.line.table_image_contracts import TableImageUnavailable
    monkeypatch.setenv('APP_ENV', environment)
    monkeypatch.delenv('MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET')
    with pytest.raises(TableImageUnavailable):
        token()
    for public_example in ('replace_with_download_token_secret', 'local-only-matching-confirmation-download-v1'):
        monkeypatch.setenv('MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET', public_example)
        with pytest.raises(TableImageUnavailable):
            token()


@pytest.mark.parametrize('flow', ['candidate', 'customer'])
def test_send_route_returns_a_closed_unavailable_result_when_image_setup_is_missing(monkeypatch, flow):
    from fastapi import HTTPException
    from subsystems.line.table_image_contracts import TableImageUnavailable
    from subsystems.access.authentication_session import AdminPrincipal
    from api.routes import candidate_contact_pool, matches
    def unavailable(*_, **__): raise TableImageUnavailable('private configuration detail')
    principal = AdminPrincipal(1, 'test', '測試', 'system_admin')
    request = SimpleNamespace(actor='test', info_type=1, event_key='demo', preview_fingerprint='preview', expected_version=0, note='推薦確認')
    if flow == 'candidate':
        monkeypatch.setattr(candidate_contact_pool, '_require_actor', lambda *_: None)
        monkeypatch.setattr(candidate_contact_pool, 'workflow', SimpleNamespace(send_information=unavailable))
        operation = lambda: candidate_contact_pool.send_candidate_information('DEMO-001', 1, request, principal)
    else:
        monkeypatch.setattr(matches, '_require_matching_actor', lambda *_: None)
        monkeypatch.setattr(matches, 'matching_notifications', SimpleNamespace(request_customer_confirmation=unavailable))
        operation = lambda: matches.send_matching_plan_customer_confirmation_route(request, 'DEMO-001', 1, principal)
    with pytest.raises(HTTPException) as captured:
        operation()
    assert captured.value.status_code == 503
    assert 'private configuration detail' not in str(captured.value.detail)


def test_transport_logs_redact_picture_capabilities_without_breaking_access_formatting():
    import logging
    import httpx
    from infrastructure.line.table_image_logging import TableImageLinkFilter
    from uvicorn.logging import AccessFormatter
    reference = token()
    path = '/api/v1/line/table-images/' + reference
    access = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d',
        ('127.0.0.1', 'GET', path, '1.1', 200), None)
    TableImageLinkFilter().filter(access)
    assert reference not in AccessFormatter('%(message)s').format(access)
    assert access.args[-1] == 200
    relay = logging.LogRecord('httpx', logging.INFO, '', 0, 'HTTP Request: %s %s "%s %d %s"',
        ('POST', httpx.URL('https://private.invalid/internal/v1/line-media/table-images/' + reference), 'HTTP/1.1', 200, 'OK'), None)
    TableImageLinkFilter().filter(relay)
    assert reference not in relay.getMessage()


def test_picture_reads_only_the_committed_delivery_snapshot_without_mutation():
    original = document()
    calls = []
    @contextmanager
    def unit():
        def read(key, index):
            calls.append((key, index))
            return original
        # No commit, current-case query, configuration or provider capability.
        yield SimpleNamespace(delivery_tasks=SimpleNamespace(table_image_document=read))
    content = LineTableImageQuery(unit, render_table_image, lambda: NOW).read(token())
    assert calls == [('delivery:demo', 0)]
    image = Image.open(BytesIO(content))
    assert image.format == 'PNG' and image.width == 1100
    assert 300 < image.height < 10000


def test_candidate_picture_keeps_willingness_actions_in_a_separate_card():
    sections = (('服務約定', (('每日時數', '8'),)),)
    old = json.loads(candidate_contact_information_card('DEMO-001', 1, sections, 'interaction', 'https://example.invalid/reply'))
    result = with_table_images(old, (document(),), 'delivery:demo', NOW, candidate=True)
    cards = result['contents']['contents']
    assert len(cards) == 2 and cards[0]['hero']['type'] == 'image'
    assert cards[1]['footer'] == old['contents']['footer']
    assert len(cards[1]['body']['contents']) == 2
    assert result[DOCUMENTS_KEY][0]['document'] == asdict(document())
    assert '每日時數' not in json.dumps(cards[1], ensure_ascii=False)


def test_clearing_candidate_description_does_not_copy_owner_rows_into_the_action_card():
    from subsystems.line.message_copy_catalog import default_copy_templates, render_copy_payload
    key = 'card-candidate-information-1'
    template = default_copy_templates()[key]
    values = json.loads(template['content'])
    field = next(field for field in template['copy_fields'] if field['kind'] == 'body')
    values[field['id']] = ''
    payload = json.loads(candidate_contact_information_card('DEMO-001', 1,
        (('月嫂薪資', (('預估總薪資', 'NT$ 50,000'),)),), 'interaction', 'https://example.invalid/reply'))
    updated = render_copy_payload({'templates': []}, key, payload, {'case_no': 'DEMO-001'}, json.dumps(values))
    result = with_table_images(updated, (document(),), 'delivery:demo', NOW, candidate=True)
    action = result['contents']['contents'][-1]
    assert action['footer'] == payload['contents']['footer']
    assert len(action['body']['contents']) == 1
    assert 'NT$ 50,000' not in str(action)


def test_weekly_picture_has_no_spurious_action_card():
    old = json.loads(candidate_contact_information_card('DEMO-001', 3, (('每週服務', (('週一', '8'),)),), 'interaction', None))
    result = with_table_images(old, (document(),), 'delivery:demo', NOW, candidate=True)
    assert len(result['contents']['contents']) == 1


def test_formal_package_keeps_profiles_three_pictures_and_independent_customer_decision():
    old = json.loads(customer_confirmation_card('DEMO-001', ({'id': 1, 'name': '範例月嫂'},), (), (), (), {}, 'interaction', '確認說明'))
    result = with_table_images(old, (document(), document(), document()), 'delivery:demo', NOW)
    cards = result['contents']['contents']
    assert len(cards) == 5
    assert [card['hero']['type'] for card in cards[1:4]] == ['image'] * 3
    assert cards[0] == old['contents']['contents'][0]
    assert cards[-1] == old['contents']['contents'][-1]
    assert len(result[DOCUMENTS_KEY]) == 3


def test_formal_composition_enqueues_one_snapshot_whose_capabilities_resolve_its_documents():
    from subsystems.line.message_copy_catalog import default_copy_templates
    from domains.line.identities import LineUserId
    from domains.scheduling.matching_communication import MatchingPlanReference, MatchingNotificationKind
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
    pending = []
    repository = SimpleNamespace(append_notification_intent=lambda **_: 17,
        open_interaction=lambda **_: None, project_intent=lambda *_: None)
    def enqueue(request):
        pending.append(request)
        return SimpleNamespace(task_id=23)
    unit = SimpleNamespace(matching_notifications=repository,
        delivery_tasks=SimpleNamespace(enqueue=enqueue))
    template = default_copy_templates()['card-customer-confirmation']
    values = json.loads(template['content'])
    description = next(field for field in template['copy_fields'] if field['kind'] == 'body')
    values[description['id']] = '本案 {case_no} 的額外說明。\n\n請先核對服務日期。'
    unit.configurations = SimpleNamespace(get=lambda _: SimpleNamespace(revision=SimpleNamespace(value=1),
        definition_json=json.dumps({'templates': [{**template, 'content': json.dumps(values)}]})))
    command = SimpleNamespace(plan=MatchingPlanReference('DEMO-001', 1, 0),
        idempotency_key=IdempotencyKey('demo-confirmation'), fingerprint=SimpleNamespace(value='preview'),
        actor=ActorContext('test'), correlation_id=CorrelationId('demo-confirmation'))
    snapshot = dict(package_type='customer_confirmation', order_information_1=({'line_sections': (
        {'title': '客戶付款約定', 'rows': (('客戶應付總額', 'NT$ 99,999'),)},)},),
        order_information_2=(), weekly_service_rows=())
    payload = customer_confirmation_card('DEMO-001', ({'id': 1, 'name': '範例月嫂'},), (), (), (), {}, 'interaction', '確認說明')
    application = MatchingNotificationApplication(None, lambda: NOW, availability_validator=lambda _: None)
    application._append_notification(unit, command, LineUserId('U-demo'), None,
        MatchingNotificationKind.CUSTOMER_PROFILES, snapshot, payload, 'interaction', 'customer_decision')
    assert len(pending) == 1
    delivery = pending[0]
    result = json.loads(delivery.payload_json)
    cards = result['contents']['contents']
    assert len(result[DOCUMENTS_KEY]) == 3
    for index, card in enumerate(cards[1:4]):
        claim = image_claim(urlsplit(card['hero']['url']).path.rsplit('/', 1)[-1], NOW)
        assert (claim['key'], claim['index']) == (delivery.idempotency_key.value, index)
    original = json.loads(payload)['contents']['contents'][-1]
    assert cards[-1]['footer'] == original['footer']
    assert cards[-1]['body']['contents'][:-1] == original['body']['contents']
    assert cards[-1]['body']['contents'][-1]['text'] == '本案 DEMO-001 的額外說明。\n\n請先核對服務日期。'
    assert 'NT$ 99,999' in str(result[DOCUMENTS_KEY])


def test_snapshot_repository_uses_parameterized_key_and_closed_document_index():
    from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
    calls = []
    payload = {DOCUMENTS_KEY: [{'document': asdict(document())}]}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, values): calls.append((sql, values))
        def fetchone(self): return {'payload_snapshot': json.dumps(payload)}
    repository = MySqlLineDeliveryTaskRepository(SimpleNamespace(cursor=Cursor))
    assert repository.table_image_document('delivery:demo', 0) == document()
    assert calls[0] == ('SELECT payload_snapshot FROM line_delivery_tasks WHERE idempotency_key=%s', ('delivery:demo',))
    with pytest.raises(LookupError):
        repository.table_image_document('delivery:demo', 1)


def test_compact_service_and_payment_layout_keeps_owner_values_without_recalculating_totals():
    result = information_document('訂單資訊－1', 'DEMO-001', ({'line_sections': (
        {'title': '服務約定', 'rows': (('案件編號', 'DEMO-001'), ('預計服務開始日', '2026-12-09'), ('每日服務時數', '8'))},
        {'title': '客戶付款約定', 'rows': (('訂金金額', 'NT$ 6,000'), ('預計訂金繳款日', '2026-11-25'), ('客戶應付總額', 'NT$ 99,999'))},
    )},), info_type=1)
    visible = str(asdict(result))
    for value in ('DEMO-001', '2026-12-09', '8', 'NT$ 6,000', '2026-11-25', 'NT$ 99,999'):
        assert value in visible


def test_provider_receives_pictures_and_actions_but_never_private_document_metadata():
    from infrastructure.line.messaging_api_adapter import _request_body
    old = json.loads(customer_confirmation_card('DEMO-001', ({'id': 1, 'name': '範例月嫂'},), (), (), (), {}, 'interaction', '確認說明'))
    result = with_table_images(old, (document(), document(), document()), 'delivery:demo', NOW)
    request = SimpleNamespace(payload_json=json.dumps(result), recipient=SimpleNamespace(identity=SimpleNamespace(value='U-demo')))
    wire = json.loads(_request_body(request))
    assert DOCUMENTS_KEY not in wire['messages'][0]
    assert '完整長內容' not in json.dumps(wire, ensure_ascii=False)
    assert 'hero' in json.dumps(wire)
    assert DOCUMENTS_KEY in json.loads(request.payload_json)
    from subsystems.line.table_image_messages import admin_picture_payload
    display = admin_picture_payload(request.payload_json)
    assert DOCUMENTS_KEY not in display
    assert '/table-images/lti_' not in display
    assert DOCUMENTS_KEY in request.payload_json  # Original committed request is unchanged.


@pytest.mark.parametrize('info_type', [1, 2])
def test_initial_picture_projection_stays_redacted_while_formal_sheet_retains_its_fields(info_type):
    from subsystems.orders.order_information import build_case_information, build_formal_information_sections
    facts = {'case_no': 'DEMO-001', 'client_name': '客戶私密姓名', 'address': '客戶私密地址', 'phone': '客戶私密電話'}
    candidate = build_case_information('DEMO-001', info_type, facts, {})
    initial = information_document('資訊', 'DEMO-001', ({'line_sections': tuple(asdict(section) for section in candidate.line_sections)},))
    formal = build_formal_information_sections(info_type, facts, {})
    assert '客戶私密' not in str(asdict(initial))
    assert '客戶私密姓名' in str(formal) and '客戶私密地址' in str(formal)


def test_staff_and_customer_information_one_have_distinct_financial_documents():
    from subsystems.line.message_preview_samples import PublicPreviewReader
    reader = PublicPreviewReader()
    staff = reader.card(None, None, 'card-candidate-information-1').table_documents_json
    customer = json.loads(reader.card(None, None, 'card-customer-confirmation').table_documents_json)[0]
    assert '月嫂薪資' in staff and '薪資單價' in staff and '預估總薪資' in staff and '預計付款日' in staff
    for field in ('客戶付款約定', '訂金金額', '第一期金額', '第二期金額', '客戶應付總額'):
        assert field not in staff
    assert '客戶付款約定' in str(customer)
    assert '月嫂薪資' not in str(customer) and '預估總薪資' not in str(customer)


@pytest.mark.parametrize('key', ['card-customer-confirmation', 'card-candidate-information-1', 'card-candidate-information-2'])
def test_existing_action_wording_is_preserved_when_image_body_copy_is_retired(key):
    from subsystems.line.message_copy import copy_fields
    from subsystems.line.message_copy_catalog import _card_defaults, default_copy_templates, effective_copy_definition
    old_fields = copy_fields(_card_defaults()[key])
    values = {field['id']: field['content'] for field in old_fields}
    current = default_copy_templates()[key]
    action = next(field['id'] for field in current['copy_fields'] if field['id'].endswith('/action/label'))
    values[action] = '我的原有按鈕文案'
    saved = {'templates': [{**current, 'content': json.dumps(values, ensure_ascii=False)}]}
    effective = effective_copy_definition(saved)['templates'][0]
    assert json.loads(effective['content'])[action] == '我的原有按鈕文案'
    assert len(effective['copy_fields']) < len(old_fields)
    assert set(json.loads(effective['content'])) == {field['id'] for field in effective['copy_fields']}
    assert json.loads(saved['templates'][0]['content']) == values


def test_png_routes_fail_closed_and_private_machine_gate_is_distinct_from_the_image_bearer():
    from api.routes import line_table_images as routes
    from api.dependencies.internal_service_auth import require_internal_service, InternalServicePrincipal
    web = FastAPI()
    web.include_router(routes.router)
    web.include_router(routes.private_router)
    query = SimpleNamespace(read=lambda reference: render_table_image(document()))
    web.dependency_overrides[routes.get_table_image_query] = lambda: query
    web.dependency_overrides[require_internal_service] = lambda: InternalServicePrincipal('line-media-proxy', 'local_shared_key')
    with TestClient(web) as client:
        assert client.post('/internal/v1/line-media/table-images/' + token()).status_code == 403
        web.dependency_overrides[require_internal_service] = lambda: InternalServicePrincipal('wrong-service', 'nas_service_token')
        assert client.post('/internal/v1/line-media/table-images/' + token()).status_code == 403
        web.dependency_overrides[require_internal_service] = lambda: InternalServicePrincipal('line-media-proxy', 'nas_service_token')
        response = client.post('/internal/v1/line-media/table-images/' + token())
        assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
        assert response.content.startswith(b'\x89PNG')
        query.read = lambda _: (_ for _ in ()).throw(TableImageNotFound())
        assert client.get('/api/v1/line/table-images/' + token()).status_code == 404
