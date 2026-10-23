"""Current group commands: mobile whitespace, saved URL and fresh delivery gates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace as NS

import pytest

from domains.line.delivery import LineDeliveryLease, LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId, LineGroupId, LineSourceType, LineUserId
from domains.line.order_group import LineOrderGroupBindingSnapshot, LineOrderGroupBindingStatus
from shared_kernel.identities import ExpectedVersion
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.order_group_application import LineOrderGroupApplication
from subsystems.line.order_group_contracts import LineOrderGroupInvitationSettings, OrderLineAudience

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
URL = 'https://line.me/R/ti/g/example'
CASE = '115000157'


class Groups:
    def __init__(self):
        self.settings = None
        self.binds = []
        self.relays = []
        self.member_history = ['joined']

    def get(self, case_no):
        return self.settings.binding if self.settings and self.settings.binding.case_no == case_no else None

    def get_by_group(self, group_id):
        binding = self.get(CASE)
        return binding if binding and binding.group_id.value == group_id else None

    def bind(self, command):
        self.binds.append(command)
        binding = LineOrderGroupBindingSnapshot(command.case_no, command.group_id,
                    LineOrderGroupBindingStatus.BOUND, ExpectedVersion(command.expected_version.value + 1))
        self.settings = LineOrderGroupInvitationSettings(binding, None)

    def get_invitation(self, case_no, *, lock=False):
        return self.settings

    def save_invitation_url(self, binding, url):
        self.settings = LineOrderGroupInvitationSettings(binding, url)

    def sync_participants(self, audience):
        pass

    def record_invitation_relay(self, relay, key):
        self.relays.append(relay)


class Deliveries:
    def __init__(self):
        self.requests = {}
        self.cancelled = []
        self.current = None

    def enqueue(self, request):
        existing = self.requests.setdefault(request.idempotency_key.value, request)
        assert request == existing

    def get(self, task_id):
        return self.current

    def cancel(self, command):
        self.cancelled.append(command)


class Uow:
    def __init__(self):
        self.order_groups = Groups()
        self.delivery_tasks = Deliveries()
        self.audience = OrderLineAudience(CASE, LineUserId('U-customer'), (LineUserId('U-staff'),))
        self.order_audiences = NS(get=lambda case: self.audience)
        self.admins = NS(get_linked_admin=lambda user: NS(admin_user_id=7, role='line_agent'))
        self.audits = []
        self.audit = NS(append=self.audits.append)
        self.commits = 0

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def commit(self): self.commits += 1


def inbox(text, event_id='event-1'):
    return NS(event=NS(source=NS(source_type=LineSourceType.GROUP, source_id='C-group', user_id=LineUserId('U-admin')),
              event_id=NS(value=event_id), occurred_at=NOW,
              payload_json=json.dumps({'message': {'type': 'text', 'text': text}})))


def command(uow, text, event_id='event-1'):
    assert LineOrderGroupApplication(lambda: NOW).handle_message(inbox(text, event_id), uow)


def replies(uow):
    return [json.loads(r.payload_json)['text'] for r in uow.delivery_tasks.requests.values()
            if r.source_aggregate_type == 'line_webhook_event']


def invitations(uow):
    return [r for r in uow.delivery_tasks.requests.values() if r.source_aggregate_type == 'line_order_group_invitation']


@pytest.mark.parametrize('separator', [' ', '   ', '\u3000', '\n', '\r\n', '\t\n\u3000'])
def test_setup_accepts_mobile_whitespace_and_saves_without_private_invitations(separator):
    uow = Uow()
    command(uow, separator.join(('綁定訂單', CASE, URL)))
    assert uow.order_groups.settings.invitation_url == URL
    assert replies(uow) == [f'已設定案件 {CASE} 的服務群組。']
    assert not invitations(uow) and not uow.order_groups.relays and not uow.commits
    assert URL not in repr(uow.order_groups.settings) and URL not in repr(uow.audits)


@pytest.mark.parametrize(('text','hint'), [
    ('綁定訂單', '請填寫案件編號與邀請網址'),
    (f'綁定訂單 {CASE}', '請貼上本群組邀請網址'),
    (f'綁定訂單 {URL}', '請填寫案件編號'),
    (f'綁定訂單{CASE} {URL}', '加空白或換行'),
    (f'綁定訂單 {CASE}{URL}', '加空白或換行'),
    (f'綁定訂單 {CASE} https://line.me/R/ti/g/\nexample', '網址中間不要換行'),
    (f'綁定訂單 {CASE} {URL} 額外說明', '只填寫'),
    (f'綁定訂單 {CASE} https://example.com/invite', '邀請網址格式不正確'),
    (f'綁定訂單 {CASE} https://line.me:443/R/ti/g/example', '邀請網址格式不正確'),
    (f'綁定訂單 {CASE} https://fake@line.me/R/ti/g/example', '邀請網址格式不正確'),
    (f'綁定訂單 {CASE} {URL}?extra=1', '邀請網址格式不正確'),
    (f'發送邀請連結 {URL}', '只需輸入「發送邀請」'),
    (f'發送邀請 {URL}', '只需輸入「發送邀請」'),
])
def test_malformed_and_retired_commands_explain_current_format_without_mutating(text, hint):
    uow = Uow()
    command(uow, text)
    assert hint in replies(uow)[0] and '格式：綁定訂單 案件編號 邀請網址' in replies(uow)[0]
    assert not uow.order_groups.binds and not uow.order_groups.relays and not invitations(uow)


def test_url_update_keeps_binding_version_and_membership_then_bare_invite_uses_saved_url():
    uow = Uow()
    command(uow, f'綁定訂單 {CASE} {URL}')
    version = uow.order_groups.settings.binding.version
    command(uow, f'綁定訂單\n{CASE}\n{URL}2', 'event-2')
    assert len(uow.order_groups.binds) == 1
    assert uow.order_groups.settings.binding.version == version
    assert uow.order_groups.member_history == ['joined']
    command(uow, '\n 發送邀請\n', 'event-3')
    command(uow, '發送邀請', 'event-3')  # durable enqueue identity and time stay replay-stable
    assert len(invitations(uow)) == 2
    assert {r.recipient.identity.value for r in invitations(uow)} == {'U-customer', 'U-staff'}
    assert all(json.loads(r.payload_json)['contents']['footer']['contents'][0]['action']['uri'] == URL+'2'
               for r in invitations(uow))


def test_unconfigured_or_legacy_binding_cannot_send():
    uow = Uow()
    command(uow, '發送邀請')
    assert '尚未設定' in replies(uow)[0]
    uow.order_groups.bind(NS(case_no=CASE, group_id=LineGroupId('C-group'), expected_version=ExpectedVersion(0)))
    command(uow, '發送邀請', 'event-2')
    assert '請先設定本群組邀請網址' in replies(uow)[1]
    assert not invitations(uow)


@pytest.mark.parametrize('text',[f'綁定訂單 {CASE} {URL}', '發送邀請'])
@pytest.mark.parametrize('gate',['unauthorized','unpaid','unbound'])
def test_setup_and_invite_keep_staff_payment_and_current_identity_gates(text, gate):
    uow = Uow()
    if gate == 'unauthorized':
        uow.admins.get_linked_admin = lambda _: None
    else:
        def reject(_): raise RuntimeError('settled_deposit_required_for_line_group' if gate == 'unpaid' else 'order_line_audience_not_ready')
        uow.order_audiences.get = reject
    if text == '發送邀請':
        uow.order_groups.bind(NS(case_no=CASE, group_id=LineGroupId('C-group'), expected_version=ExpectedVersion(0)))
    command(uow, text)
    assert any(word in replies(uow)[0] for word in ('工會人員','尚未確認入帳','尚未完成 LINE 綁定'))
    assert not invitations(uow) and not uow.order_groups.relays


def test_unexpected_save_failure_reaches_outer_rollback_and_never_acknowledges_success():
    uow = Uow()
    def failure(*_): raise RuntimeError('database_write_failure')
    uow.order_groups.save_invitation_url = failure
    with pytest.raises(RuntimeError, match='database_write_failure'):
        command(uow, f'綁定訂單 {CASE} {URL}')
    assert not replies(uow) and not invitations(uow)


@pytest.mark.parametrize('change', ['none','url','group','recipient','unpaid','cancelled','legacy'])
def test_worker_rechecks_saved_configuration_and_eligibility_before_provider(change):
    uow = Uow()
    command(uow, f'綁定訂單 {CASE} {URL}')
    command(uow, '發送邀請', 'event-2')
    request = invitations(uow)[0]
    settings = uow.order_groups.settings
    if change == 'url': uow.order_groups.settings = replace(settings, invitation_url=URL+'2')
    if change == 'group': uow.order_groups.settings = replace(settings, binding=replace(settings.binding, group_id=LineGroupId('C-new'), version=ExpectedVersion(2)))
    if change == 'recipient': uow.audience = replace(uow.audience, customer_line_user_id=LineUserId('U-new'))
    if change in ('unpaid','cancelled'):
        def reject(_): raise RuntimeError('settled_deposit_required_for_line_group' if change == 'unpaid' else 'cancelled_order_cannot_bind_line_group')
        uow.order_audiences.get = reject
    if change == 'legacy': request = replace(request, source_aggregate_identity=CASE+':legacy')
    lease = LineDeliveryLease(LineDeliveryTaskId(1), 'test', NOW, NOW+timedelta(seconds=60))
    task = NS(task_id=LineDeliveryTaskId(1), request=request, lease=lease)
    uow.delivery_tasks.current = NS(status=LineDeliveryStatus.PROCESSING, lease=lease)
    worker = LineDeliveryWorker(lambda: uow, None, 'test', lambda: NOW)
    assert worker._still_sendable(task) == (change == 'none')
    assert len(uow.delivery_tasks.cancelled) == (change != 'none')


def test_retired_alert_registration_command_has_no_effect_on_service_groups():
    uow = Uow()
    def forbidden(*args):
        pytest.fail("retired group command cannot register a target")
    application = LineOrderGroupApplication(lambda: NOW, alert_group_registrar=forbidden)
    assert application.handle_message(inbox("設定異常通知群組"), uow)
    assert not uow.delivery_tasks.requests and not uow.order_groups.binds
    assert not uow.audits and not uow.commits
