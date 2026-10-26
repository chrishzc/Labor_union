"""Thin desktop/LIFF read adapters over the existing pending-query owners.

Each request reads one bounded source from existing owners. No new inbox,
completion flag, writer, or cross-owner transaction is introduced here.
"""
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies.admin_auth import require_admin, admin_actor_context, has_required_capability
from api.dependencies.line_identity import get_line_identity_application, get_line_identity_review_application
from api.dependencies.client_profile import get_client_profile_application
from api.dependencies.line_runtime import get_line_order_group_query_application, get_line_delivery_task_admin_application
from api.dependencies.service_start import get_service_start_application
from api.dependencies.line_deposit import get_deposit_notifications
from api.dependencies.payment_overdue_reminders import get_payment_overdue_reminders
from api.dependencies.service_day_log_reminders import get_service_day_log_reminders
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.notification_tasks import NotificationSource as Source, NotificationItem as Item, NotificationPage, NotificationSourceView, MobileNotificationQuery, NotificationCursor
from subsystems.anomalies.current_issue_query import CurrentIssueCursorCodec, CurrentIssueListRequest
from subsystems.line.notification_failure_current_fact import LineNotificationFailureCurrentFactQuery, LineNotificationFailureReason
from domains.line.review import LineReviewStatus
from domains.line.identity_binding import LineBindingSubjectType
from subsystems.line.identity_management_contracts import LineIdentityCandidateQuery
from domains.line.delivery import LineDeliveryStatus
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from shared_kernel.clock import SystemBusinessClock
from subsystems.line.capabilities import LineCapability as Cap
from subsystems.line.review_contracts import LineReviewListQuery
from subsystems.line.candidate_contact_response_application import CandidateContactResponseApplication
from subsystems.line.candidate_contact_coordination_worker import query_manual_followups
from subsystems.line.delivery_admin_contracts import LineDeliveryAdminQuery
from subsystems.line.payment_overdue_reminders import reminder_text as payment_text
from subsystems.line.deposit_notifications import deposit_notification_payload, REMINDER, SETTLED
from api.routes.line_deposit_payment import deposit_reminder_blocker
from subsystems.customer_service.application import CustomerServiceApplication
from subsystems.customer_service.contracts import CustomerServiceReminderQuery

router = APIRouter(tags=['Notification Workbench'])
SIZE = 25
# Capabilities match the original owner entry points, including mobile auth.
SOURCES = {
    Source.REGISTRATION: ('服務登記', 'review', None),
    Source.IDENTITY: ('身分綁定審核', 'review', Cap.REVIEW_READ),
    Source.CUSTOMER_BINDING: ('客戶綁定人工提醒', 'review', Cap.IDENTITY_BINDING_READ),
    Source.STAFF_BINDING: ('月嫂綁定人工提醒', 'review', Cap.IDENTITY_BINDING_READ),
    Source.PROFILE: ('客戶資料異動', 'review', Cap.CUSTOMER_SERVICE_READ),
    Source.INFORMATION: ('確認資訊與調整條件', 'review', Cap.MATCHING_READ),
    Source.FOLLOWUP: ('月嫂回覆待跟進', 'review', Cap.MATCHING_READ),
    Source.RECOMMENDATION: ('推薦確認與簽約', 'review', Cap.MATCHING_READ),
    Source.SERVICE_START: ('開工、順延與代班', 'review', Cap.MATCHING_OVERRIDE),
    Source.DEPOSIT: ('訂金通知待處理', 'reminder', Cap.TASK_READ),
    Source.GROUP: ('訂金已付尚未建群', 'reminder', Cap.ORDER_GROUP_READ),
    Source.OVERDUE: ('各期款項逾期', 'reminder', Cap.CUSTOMER_SERVICE_HANDLE),
    Source.LOG: ('連續缺漏日誌', 'reminder', Cap.ORDER_GROUP_READ),
    Source.CUSTOMER_SERVICE: ('客服與服務協助', 'support', Cap.CUSTOMER_SERVICE_READ),
    Source.DELIVERY: ('LINE 寄送異常', 'support', Cap.TASK_READ),
    Source.NOTIFICATION_FAILURE: ('LINE 通知建立異常', 'support', Cap.MONITOR_READ),
    Source.RUNTIME: ('系統與通知對象', 'support', Cap.MONITOR_READ),
}


def _allowed(principal, source):
    capability = SOURCES[source][2]
    return capability is None or has_required_capability(principal, capability.value)


def _catalog(principal):
    return [NotificationSourceView(source=key, label=value[0], group=value[1])
            for key, value in SOURCES.items() if _allowed(principal, key)]


def _item(source, identity, title, summary, reason, **kwargs):
    return Item(id=f'{source.value}:{identity}', source=source, group=SOURCES[source][1],
                title=title, summary=summary, reason=reason, **kwargs)


def query_source(source, cursor, principal):
    if source == Source.LEAVE:
        raise typed_http_error(410, 'conflict', 'legacy_leave_todo_retired',
                               '舊請假申請僅供歷史查閱；現行例外請使用開工、順延與代班待辦。', 'notification-workbench')
    if not _allowed(principal, source):
        raise typed_http_error(403, 'forbidden', 'notification_source_forbidden',
                               '目前帳號沒有查看此類事項的權限。', 'notification-workbench')
    if source != Source.NOTIFICATION_FAILURE and not isinstance(cursor, int):
        raise typed_http_error(422, 'validation', 'notification_cursor_invalid', '分頁已失效，請重新整理。', 'notification-workbench')
    if source == Source.NOTIFICATION_FAILURE and isinstance(cursor, int) and cursor != 0:
        raise typed_http_error(422, 'validation', 'notification_cursor_invalid', '分頁已失效，請重新整理。', 'notification-workbench')
    try:
        return _read_source(source, cursor, principal)
    except HTTPException:
        raise
    except Exception:
        # Never expose raw SQL/provider payload or turn failed reads into zero.
        raise typed_http_error(503, 'unavailable', 'notification_source_unavailable',
                               '此類事項暫時無法讀取，請重新整理。', 'notification-workbench', retryable=True) from None


def _read_source(source, cursor, principal):
    if source == Source.NOTIFICATION_FAILURE:
        return _notification_failures(cursor)
    page = cursor + 1
    actor = admin_actor_context(principal)
    now = SystemBusinessClock().now()
    items = []
    total = None
    if source == Source.REGISTRATION:
        rows = get_line_identity_application().pending_registrations(after_id=cursor, limit=SIZE)
        items = [_item(source, r.registration_id, '服務登記待審核', '已提交需求表單，請核對申請內容。',
                       '核准後沿原流程建立客戶資料與綁定。', reference_id=r.registration_id,
                       person=str(r.candidate.client_payload['name'])) for r in rows]
        return NotificationPage(items=items, next_cursor=rows[-1].registration_id if len(rows) == SIZE else None)
    if source == Source.IDENTITY:
        result = get_line_identity_review_application().list(LineReviewListQuery(
            statuses=(LineReviewStatus.PENDING,), page=page, page_size=SIZE))
        total = result.total
        items = [_item(source, r.request_id.value, '身分綁定待審核', '請核對申請身分及目前綁定。',
                       '此申請仍在原身分審核佇列。', reference_id=r.request_id.value,
                       person={'customer':'客戶','staff':'月嫂','admin':'工會人員'}.get(r.subject_type.value if r.subject_type else '', '申請人')) for r in result.items]
    elif source in (Source.CUSTOMER_BINDING, Source.STAFF_BINDING):
        from api.routes.line_identity_management import _application
        role = LineBindingSubjectType.CUSTOMER if source == Source.CUSTOMER_BINDING else LineBindingSubjectType.STAFF
        label = '客戶' if role is LineBindingSubjectType.CUSTOMER else '月嫂'
        result = _application().binding_reminders(LineIdentityCandidateQuery(role, page=page, page_size=SIZE))
        total = result.total
        guidance = ('客戶請核對姓名與電話。' if role is LineBindingSubjectType.CUSTOMER
                    else '月嫂請核對姓名、身分證字號與生日。')
        exit_condition = ('完成綁定，或案件取消、完工、成為歷史案件後，此事項自動移除。'
                          if role is LineBindingSubjectType.CUSTOMER else
                          '完成綁定，或月嫂停用、暫停、退役後，此事項自動移除。')
        items = [_item(source, r.subject_reference, f'人工提醒{label}綁定 LINE',
                       '請透過電話等既有聯絡方式，提醒本人加入官方帳號並完成身分綁定。',
                       '尚未綁定 LINE，需透過其他方式聯絡。' + exit_condition,
                       reference_id=int(r.subject_reference), case_no=r.case_no, person=r.subject_name,
                       tag='待人工提醒', recipient=r.phone,
                       message=f'請加入工會 LINE 官方帳號並完成{label}身分綁定。{guidance}') for r in result.items]
    elif source == Source.PROFILE:
        rows, total = get_client_profile_application().list_requests(status='pending', page=page, page_size=SIZE)
        items = [_item(source, r.request_id, '客戶資料異動待審核', '客戶已提出資料異動。', r.reason or '請核對異動前後內容。',
                       reference_id=r.request_id, person=f'客戶 #{r.client_id}', expected_version=r.request_version) for r in rows]
    elif source == Source.INFORMATION:
        result = CandidateContactResponseApplication(get_connection).query_staff_questions(page=page, page_size=SIZE)
        total = result['total']
        items = [_item(source, r['question_id'], '調整條件待處理' if r['request_kind']=='condition_adjustment' else '確認資訊待處理',
                       r['customer_answer'] or '月嫂提出需求，請由人員輸入文案後處理。',
                       '；'.join(f"{v['label']}：{v['detail']}" for v in r['issues']) or '人員查看後自行輸入回覆，不自動轉問客戶。',
                       reference_id=r['question_id'], case_no=r['case_no'], person=r['staff_name'], information=r,
                       unavailable_reason=None if r['customer_available'] else '客戶尚未綁定 LINE，請先完成身分綁定再詢問客戶。') for r in result['items']]
    elif source == Source.FOLLOWUP:
        result = query_manual_followups(get_connection, now, page=page, limit=SIZE)
        total = result.total
        items = [_item(source, r.pool_id, '月嫂回覆待跟進', f'{r.reminder_count} 位月嫂待跟進。',
                       '24 小時只作內部提醒，不阻擋月嫂回覆。', case_no=r.case_no, reference_id=r.pool_id,
                       time=str(r.reminder_due_at)) for r in result.items]
    elif source == Source.RECOMMENDATION:
        with open_line_unit_of_work() as unit:
            total = unit.matching_notifications.customer_recommendation_followup_count(now)
            rows = unit.matching_notifications.customer_recommendation_followups(now, limit=SIZE, offset=cursor*SIZE)
        titles = {'contact_requested':'客戶要求專人協助', 'awaiting_signing':'客戶已接受配對，待辦簽約', 'reply_reminder':'推薦確認待跟進'}
        items = [_item(source, f'{r.plan_id}:{r.status}', titles[r.status], '請接續本案原有工作流程。',
                       '7 天只作內部提醒，仍可接受配對；簽約與訂金付款可先後發生。', case_no=r.case_no,
                       reference_id=r.ticket_id if r.status=='contact_requested' else None, tag='待簽約' if r.status=='awaiting_signing' else '待跟進',
                       time=str(r.reminder_due_at or '')) for r in rows]
        # One contact request is one ticket, also surfaced by the service owner.
        items = [item.model_copy(update={'id':f'customer_service:{item.reference_id}'}) if item.reference_id else item for item in items]
    elif source == Source.SERVICE_START:
        dependency = get_service_start_application()
        application = next(dependency)
        try:
            rows, total = application.todos(page, SIZE)
            items = [_item(source, r.request_id, '換人交接待處理' if r.workflow_kind=='handover' else '服務日期／代班待處理',
                           r.conflict_message or '請接續詢問意願、邀請入群及記錄日期。',
                           '只有需要代班或排程衝突才由工會處理。', case_no=r.case_no, reference_id=r.request_id,
                           person=r.staff_name, expected_version=r.version) for r in rows]
        finally:
            # The existing dependency is a generator and owns its connection.
            dependency.close()
    elif source == Source.DEPOSIT:
        application = get_deposit_notifications()
        with open_line_unit_of_work() as unit:
            result = unit.deposit_notifications.followups(page=page, page_size=SIZE)
        total = result.page_total
        for r in result.items:
            p = r.payment
            unavailable = deposit_reminder_blocker(application,p,r.line_bound)
            items.append(_item(source, p.case_no, '訂金核銷通知待處理' if p.settled else '訂金繳費提醒待處理',
                               f'訂金 NT$ {p.amount_ntd:,}'+('，已核銷。' if p.settled else '，尚未核銷。'),
                               '核銷通知由原有工作自動處理；不重複核銷。' if p.settled else '寄送前由原流程重新核對繳費資訊及收件人。',
                               case_no=p.case_no, expected_version=p.obligation_version, tag='已核銷待通知' if p.settled else '待提醒',
                               recipient='客戶私人聊天室', unavailable_reason=unavailable, delivery_status=r.delivery_status,
                               message=deposit_notification_payload(p.case_no,p.amount_ntd,p.due_date,SETTLED if p.settled else REMINDER,'')['altText'] if p.settled or p.due_date else None))
    elif source == Source.GROUP:
        result = get_line_order_group_query_application().paid_uncreated_todos(actor, page=page, page_size=SIZE)
        total = result.total
        items = [_item(source, r.case_no, '訂金已付，尚未建群', '請建立並綁定本案案件群組。',
                       '訂金正式核銷且尚無案件群組；不以簽約完成為門檻。', case_no=r.case_no,
                       message=f'在案件群組輸入：\n綁定訂單 {r.case_no} 邀請網址\n\n貼上完整邀請網址，各項可用空白或換行。\n綁定成功後輸入：發送邀請') for r in result.items]
    elif source == Source.OVERDUE:
        rows, total = get_payment_overdue_reminders().list(page, SIZE)
        labels = {'deposit':'訂金', 'first':'第一期款', 'second':'第二期款'}
        items = [_item(source, r.payment.obligation_identity, labels[r.payment.payment_stage]+'逾期未清',
                       f'本期未繳 NT$ {r.payment.remaining_amount_ntd:,}，逾期 {r.overdue_days} 天。',
                       '各期獨立判斷；寄送前重新核對本期金額、到期日及對象。', case_no=r.payment.case_no,
                       recipient=r.recipient_label, message=payment_text(r.payment), payment=asdict(r.payment),
                       unavailable_reason=r.unavailable_reason, delivery_status=r.last_reminder.status if r.last_reminder else None,
                       time=str(r.payment.due_date)) for r in rows]
    elif source == Source.LOG:
        dependency = get_service_day_log_reminders()
        try:
            rows, total = next(dependency).list(page, SIZE)
        finally:
            dependency.close()
        items = [_item(source, f'{r.gap.case_no}:{r.gap.staff_id}:{r.gap.missing_from}', '服務日誌連續缺漏',
                       f'{r.group_label}，連續缺漏 {r.gap.consecutive_days} 天。',
                       f'{r.gap.missing_from} ～ {r.gap.missing_through} 未填日誌，由人員決定是否提醒。', case_no=r.gap.case_no,
                       recipient=r.group_label, message=r.message, unavailable_reason=None if r.can_send else '尚未綁定可用案件群組。',
                       log={k:v for k,v in asdict(r.gap).items() if k != 'consecutive_days'}) for r in rows]
    elif source == Source.CUSTOMER_SERVICE:
        result = CustomerServiceApplication(open_line_unit_of_work).reminders(CustomerServiceReminderQuery(page=page, page_size=SIZE))
        total = result.total
        items = [_item(source, r.ticket_id, '客服／服務協助待處理', r.reason, '沿原客服案件查看留言、接手及回覆。',
                       reference_id=r.ticket_id, case_no=r.case_no, person=r.client_name or '聯絡人', time=str(r.updated_at or '')) for r in result.items]
    elif source == Source.DELIVERY:
        result = get_line_delivery_task_admin_application().list(LineDeliveryAdminQuery(
            statuses=(LineDeliveryStatus.FAILED, LineDeliveryStatus.RETRYABLE_FAILED), page=page, page_size=SIZE), actor)
        with open_line_unit_of_work() as unit:
            unresolved_ids = set(unit.notification_rules.unresolved_delivery_task_ids(tuple(r.task_id.value for r in result.items)))
        items = [_item(source, r.task_id.value, 'LINE 寄送異常', '請查看原寄送工作及可用處理方式。',
                       '寄送異常不撤銷原本的核銷或案件結果。', reference_id=r.task_id.value, delivery_status=r.status.value,
                       time=str(r.updated_at)) for r in result.items if r.task_id.value in unresolved_ids]
        # Fresh source filtering may leave an empty candidate page. Preserve the
        # original cursor, but do not present its unfiltered count as a total.
        return NotificationPage(items=items, total=0 if result.total == 0 else None,
                                next_cursor=page if page*SIZE < result.total else None)
    elif source == Source.RUNTIME:
        connection = get_connection()
        try:
            repository = MySqlRuntimeMonitorRepository(connection)
            statuses = repository.list_status()
            from api.routes.runtime_health import _app
            if not _app().has_available_admin_target():
                items.append(_item(source, 'targets', '系統通知尚無可用對象', '請核對管理員啟用狀態、LINE 綁定及通知對象設定。',
                                   '通知對象須啟用，且管理員仍啟用並具有目前有效的 LINE 綁定。'))
            for r in statuses:
                if r.status in ('warning', 'critical'):
                    items.append(_item(source, r.check_name, '系統狀態需要處理', r.message,
                                       '依目前監控結果顯示；恢復正常後重新整理即移除。', person=r.component, time=str(r.checked_at)))
            total = len(items)
            items = items[cursor*SIZE:(cursor+1)*SIZE]
        finally:
            connection.close()
    return NotificationPage(items=items, total=total, next_cursor=page if total is not None and page*SIZE < total else None)


@router.get('/api/v1/line/notification-tasks', response_model=BaseResponse[list[NotificationSourceView]])
def source_catalog(principal=Depends(require_admin)):
    return BaseResponse(data=_catalog(principal))


@router.get('/api/v1/line/notification-tasks/{source}', response_model=BaseResponse[NotificationPage])
def source_page(source: Source, cursor: NotificationCursor=0, principal=Depends(require_admin)):
    return BaseResponse(data=query_source(source, cursor, principal))


@router.post('/api/v1/line/mobile-admin/notification-tasks/{source}', response_model=BaseResponse[NotificationPage])
def mobile_source_page(source: Source, body: MobileNotificationQuery):
    from api.routes.line_mobile_admin import _mobile_admin_context
    principal, _ = _mobile_admin_context(body.line_id_token, Cap.REVIEW_READ if source == Source.LEAVE else SOURCES[source][2])
    return BaseResponse(data=query_source(source, body.cursor, principal))


@router.post('/api/v1/line/mobile-admin/notification-tasks', response_model=BaseResponse[list[NotificationSourceView]])
def mobile_source_catalog(body: MobileNotificationQuery):
    from api.routes.line_mobile_admin import _mobile_admin_context
    principal, _ = _mobile_admin_context(body.line_id_token)
    return BaseResponse(data=_catalog(principal))


def failure_readback(unit, projection):
    """Re-read the original LINE predicate; the workbench owns no completion flag."""
    if projection is None or projection.candidate.definition_code != 'LINE-006':
        return None
    subject = projection.candidate.subject_identity
    result = unit.notification_rules.current_failure_fact(LineNotificationFailureCurrentFactQuery(
        subject['case_no'], LineNotificationFailureReason(subject['notification_reason'])))
    if not result.authoritative_complete:
        raise typed_http_error(503, 'unavailable', 'notification_failure_readback_unavailable',
            '通知異常暫時無法完整核對，請重新整理。', 'notification-workbench', retryable=True)
    return result if result.predicate_active else None


def _notification_failures(cursor):
    request = CurrentIssueListRequest(definition_code='LINE-006', limit=SIZE, cursor=None if cursor == 0 else cursor)
    codec = CurrentIssueCursorCodec()
    try:
        after = codec.decode(request)
    except ValueError as error:
        raise typed_http_error(422, 'validation', 'notification_cursor_invalid', '分頁已失效，請重新整理。', 'notification-workbench') from error
    with open_line_unit_of_work() as unit:
        rows = unit.anomaly_rechecks.query_current_page(request, after, SIZE + 1)
        visible = rows[:SIZE]
        items = []
        for projection in visible:
            current = failure_readback(unit, projection)
            if current is None:
                continue
            recipient = current.notification_reason is LineNotificationFailureReason.RECIPIENT_UNAVAILABLE
            items.append(_item(Source.NOTIFICATION_FAILURE, projection.issue_key, 'LINE 通知建立異常',
                '通知收件對象尚不可用。' if recipient else '通知內容或排程設定需要修正。',
                '補好設定後仍需核對原通知；補送完成或原通知不再適用後才移除。',
                case_no=current.case_no, time=str(projection.last_verified_at),
                failure={'issue_key':projection.issue_key,'notification_reason':current.notification_reason.value,'related_task_ids':list(current.related_task_ids)}))
        next_cursor = codec.encode(request, visible[-1]) if len(rows) > SIZE and visible else None
        return NotificationPage(items=items, next_cursor=next_cursor)
