"""Session-authenticated adapters for existing LINE staff commands.

The owner applications retain validation, concurrency, idempotency and commits.
These endpoints never execute a provider or publish menus.
"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from api.dependencies.admin_auth import require_capability, require_line_matching_sender, require_line_matching_override, admin_actor_context, has_required_capability
from subsystems.line.capabilities import LineCapability
from api.dependencies.line_deposit import get_deposit_notifications
from api.schemas.base import BaseResponse
from api.schemas.line_identity import CanonicalLineReviewResponse
from api.schemas.notification_tasks import NotificationFailureDetailView
from api.schemas.line_candidate_contact import CandidateInformationStaffSendView
from api.routes.line_deposit_payment import DepositReminderReceipt
from api.error_contracts import typed_http_error
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import IdempotencyKey
from subsystems.line.deposit_notifications import DepositNotificationConflict
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from domains.line.identities import LineDeliveryTaskId
from subsystems.line.candidate_contact_response_application import CandidateContactResponseApplication, CandidateContactResponseError
from api.dependencies.order_terms import get_order_terms_application
from api.routes.order_terms import OrderTermsInput
from api.routes import order_terms as terms_routes
from shared_kernel.identities import CorrelationId

router = APIRouter(prefix='/api/v1/line/notification-task-actions', tags=['Notification Workbench'])
mobile_router = APIRouter(prefix='/api/v1/line/mobile-admin/notification-task-actions', tags=['Notification Workbench'])


def _failure_detail(issue_key, principal):
    from api.routes.notification_tasks import failure_readback
    with open_line_unit_of_work() as unit:
        current = failure_readback(unit, unit.anomaly_rechecks.query_current(issue_key))
        if current is None:
            raise typed_http_error(409, 'conflict', 'notification_failure_changed', '此通知異常已更新，請重新整理待辦。', 'notification-failure')
        timeline = unit.notification_rules.list_case_timeline(current.case_no)
        labels = {'recipient_unavailable':'收件人尚未完成 LINE 綁定，或本案尚無可用案件群組。請先核對收件人與群組設定，再重新核對通知。',
                  'notification_configuration_unavailable':'通知設定尚未完整。請至通知內容與規則設定補齊後，再重新核對通知。',
                  'template_or_schedule_invalid':'通知內容或排程設定需要修正。請至通知內容與規則設定核對後再試。',
                  'notification_source_not_currently_applicable':'案件狀況已改變，原通知目前已不適用。請返回並重新整理待辦。'}
        sources = []
        active_task_ids = set()
        for task_id in current.related_task_ids:
            task = unit.delivery_tasks.get(LineDeliveryTaskId(task_id))
            if task is None:
                raise typed_http_error(503, 'unavailable', 'notification_failure_task_unavailable', '原寄送工作暫時無法核對，請重試。', 'notification-failure')
            if task.status.value in ('pending','processing','failed','retryable_failed'):
                active_task_ids.add(task_id)
        source_tasks = dict(current.source_task_ids)
        for identity in current.unresolved_source_ids:
            if identity not in source_tasks:
                raise typed_http_error(503, 'unavailable', 'notification_failure_source_unavailable', '原通知工作暫時無法完整核對，請重試。', 'notification-failure')
            has_original_work = bool(active_task_ids.intersection(source_tasks[identity]))
            row = next((r for r in timeline if r['source_event_id'] == identity), None)
            if row is None:
                raise typed_http_error(503, 'unavailable', 'notification_failure_source_unavailable', '原通知資料暫時無法核對，請重試。', 'notification-failure')
            preview = unit.notification_rules.preview_manual_replay(identity)
            pending = identity in current.replay_in_progress_source_ids
            sources.append({'source_event_id':identity, 'event_code':row['event_code'],
                'can_replay':bool(preview['can_replay'] and not pending and not has_original_work and has_required_capability(principal, LineCapability.CONFIG_MANAGE.value)),
                'unavailable_reason':'原補送工作尚未完成，仍在排隊、寄送或等待重試，尚未確認送達。請查看下方原寄送工作，完成前不另建補送。' if pending else
                    '本筆通知已有原寄送工作，請接續下方原工作的重試或取消入口處理，不另建補送。' if has_original_work else
                    labels.get(preview['unavailable_reason'], '目前無法確認補送資格，請核對通知設定與原案件資料後重新核對。') if not preview['can_replay'] else
                    None if has_required_capability(principal, LineCapability.CONFIG_MANAGE.value) else '目前帳號沒有補送通知的權限，請由有權限的工會人員處理。'})
        return {'case_no':current.case_no,'notification_reason':current.notification_reason.value,'sources':sources,
                'related_task_ids':list(current.related_task_ids)}


@router.get('/notification-failures/{issue_key}/query', response_model=BaseResponse[NotificationFailureDetailView])
def notification_failure_detail(issue_key: Annotated[str, Path(pattern=r'^ci_[0-9a-f]{64}$')],
                                principal=Depends(require_capability(LineCapability.MONITOR_READ))):
    return BaseResponse(data=_failure_detail(issue_key, principal))




class MobileAuth(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id_token: str = Field(min_length=1, max_length=4096)


def _mobile(token, capability):
    from api.routes.line_mobile_admin import _mobile_admin_context
    return _mobile_admin_context(token, capability)[0]


@mobile_router.post('/notification-failures/{issue_key}/query', response_model=BaseResponse[NotificationFailureDetailView])
def mobile_notification_failure_detail(issue_key: Annotated[str, Path(pattern=r'^ci_[0-9a-f]{64}$')], body: MobileAuth):
    return BaseResponse(data=_failure_detail(issue_key, _mobile(body.line_id_token, LineCapability.MONITOR_READ)))


from api.schemas.line_notification_rules import ApplyLineNotificationManualReplayRequest


class MobileNotificationReplay(ApplyLineNotificationManualReplayRequest, MobileAuth):
    pass


@mobile_router.post('/notification-sources/{source_event_id}/replay')
def mobile_notification_replay(source_event_id: Annotated[int, Path(gt=0)], body: MobileNotificationReplay, request: Request):
    from api.routes.line_notification_rules import apply_notification_manual_replay
    principal = _mobile(body.line_id_token, LineCapability.CONFIG_MANAGE)
    return apply_notification_manual_replay(source_event_id,
        ApplyLineNotificationManualReplayRequest(**body.model_dump(exclude={'line_id_token'})), request, principal)


class DepositReminder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1, max_length=50)
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class InformationSend(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    recipient: Literal['caregiver', 'customer']
    message_text: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=100)


@router.post('/deposit-reminder', response_model=BaseResponse[DepositReminderReceipt])
def deposit_reminder(body: DepositReminder, principal=Depends(require_capability(LineCapability.TASK_SEND))):
    try:
        identity, status = get_deposit_notifications().send_reminder(body.case_no, body.expected_version,
            IdempotencyKey(body.idempotency_key), admin_actor_context(principal))
        return BaseResponse(data={'task_id':identity, 'delivery_status':status}, message='已建立寄送工作，尚未證明送達。')
    except DepositNotificationConflict as error:
        messages = {
            'deposit_contract_not_completed':'客戶與所有月嫂尚未完成簽約，請完成雙方簽約後再提醒繳款。',
            'deposit_customer_not_bound':'客戶尚未綁定 LINE，請先完成身分綁定。',
            'deposit_payment_details_incomplete':'繳費資訊尚未完整，請核對到期日、銀行代碼與虛擬帳號。',
            'deposit_liff_not_configured':'尚未設定繳費頁面，請先完成 LIFF 設定。',
        }
        raise typed_http_error(409, 'conflict', str(error), messages.get(str(error),
            '繳費資料或狀態已更新，請重新整理後再操作。'), 'notification-deposit') from error


@router.post('/information/{question_id}/send', response_model=BaseResponse[CandidateInformationStaffSendView])
def information_send(question_id: int, body: InformationSend, principal=Depends(require_line_matching_sender)):
    try:
        result = CandidateContactResponseApplication(get_connection).send_staff_information(question_id,
            body.recipient, body.message_text, admin_actor_context(principal).actor_id, IdempotencyKey(body.idempotency_key))
        return BaseResponse(data=result, message='已建立寄送工作，尚未證明送達。')
    except CandidateContactResponseError as error:
        messages = {
            'candidate_contact_recipient_unavailable':'月嫂尚未綁定 LINE，請先完成身分綁定。',
            'candidate_contact_customer_unavailable':'客戶尚未綁定 LINE，請先完成身分綁定。',
        }
        raise typed_http_error(409, 'conflict', str(error), messages.get(str(error),
            '問題或寄送狀態已更新，請重新整理後再操作。'), 'notification-information') from error


class AdjustmentContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1, max_length=50)
    customer_answer_event_id: int = Field(gt=0)


class AdjustmentTerms(AdjustmentContext):
    proposed_terms: OrderTermsInput


class AdjustmentApproval(AdjustmentTerms):
    expected_order_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=191)


class AdjustmentRecontact(AdjustmentContext):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)


class RecontactItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: int = Field(gt=0)
    preview_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class AdjustmentRecontactApply(AdjustmentContext):
    items: list[RecontactItem] = Field(min_length=1, max_length=100)


@router.get('/adjustments/{pool_id}')
def adjustment_query(pool_id:int,case_no:str=Query(min_length=1,max_length=50),customer_answer_event_id:int=Query(gt=0),
                     principal=Depends(require_line_matching_override),application=Depends(get_order_terms_application)):
    from api.routes.line_mobile_admin import _matching_operation, _matching_operation_payload, _MobileMatchingFollowupOperationView
    operation = _matching_operation(pool_id,case_no,customer_answer_event_id)
    return BaseResponse(data=_MobileMatchingFollowupOperationView.model_validate({**_matching_operation_payload(operation),
        'order_terms':terms_routes._query_payload(application.query(case_no))}))


@router.post('/adjustments/{pool_id}/preview')
def adjustment_preview(pool_id:int,body:AdjustmentTerms,principal=Depends(require_line_matching_override),application=Depends(get_order_terms_application)):
    from api.routes.line_mobile_admin import _matching_operation, _mobile_matching_terms_preview_payload
    _matching_operation(pool_id,body.case_no,body.customer_answer_event_id)
    return terms_routes._call_endpoint(lambda:_mobile_matching_terms_preview_payload(application.preview(body.case_no,body.proposed_terms.to_domain())),
        '條件預覽已建立，尚未寫入。',CorrelationId('notification-adjustment-preview'))


@router.post('/adjustments/{pool_id}/approve')
def adjustment_approve(pool_id:int,body:AdjustmentApproval,principal=Depends(require_line_matching_override),application=Depends(get_order_terms_application)):
    from api.routes.line_mobile_admin import _approve_matching_terms
    return _approve_matching_terms(pool_id,body,application,admin_actor_context(principal))


@router.post('/adjustments/{pool_id}/recontact/preview')
def adjustment_recontact_preview(pool_id:int,body:AdjustmentRecontact,principal=Depends(require_line_matching_override)):
    from api.routes.line_mobile_admin import _preview_matching_recontact
    return _preview_matching_recontact(pool_id,body)


@router.post('/adjustments/{pool_id}/recontact/apply')
def adjustment_recontact_apply(pool_id:int,body:AdjustmentRecontactApply,principal=Depends(require_line_matching_override)):
    from api.routes.line_mobile_admin import _apply_matching_recontact
    return _apply_matching_recontact(pool_id,body,admin_actor_context(principal))


@mobile_router.post('/registrations/{identity}/query')
def mobile_registration_query(identity:int,body:MobileAuth):
    from api.routes.registration_applications import application_detail
    principal = _mobile(body.line_id_token, None)
    return application_detail(identity,principal,get_line_identity_application())


from api.routes.registration_applications import ApprovalRequest, get_line_identity_application
from api.schemas.line_tasks import LineTaskActionRequest
from api.schemas.runtime_health import AlertAdminTargetRequest, AlertAdminTargetApplyRequest, AlertTargetEnabledRequest, AlertTargetEnabledApplyRequest


class MobileRegistrationApproval(ApprovalRequest, MobileAuth):
    pass


@mobile_router.post('/registrations/{identity}/approve')
def mobile_registration_approve(identity:int,body:MobileRegistrationApproval):
    from api.routes.registration_applications import approve_application
    principal = _mobile(body.line_id_token, LineCapability.REVIEW_DECIDE)
    return approve_application(identity,ApprovalRequest(expected_version=body.expected_version),principal,get_line_identity_application())


@mobile_router.post('/delivery/{identity}/query')
def mobile_delivery_query(identity:int,body:MobileAuth):
    from api.routes.line_tasks import task_detail
    return task_detail(identity,_mobile(body.line_id_token,LineCapability.TASK_READ))


class MobileTaskControl(LineTaskActionRequest, MobileAuth):
    pass


@mobile_router.post('/delivery/{identity}/{action}')
def mobile_delivery_control(identity:int,action:Literal['cancel','retry'],body:MobileTaskControl,request:Request):
    from api.routes.line_tasks import cancel_task,retry_task
    principal=_mobile(body.line_id_token,LineCapability.TASK_CONTROL)
    return {'cancel':cancel_task,'retry':retry_task}[action](identity,LineTaskActionRequest(**body.model_dump(exclude={'line_id_token'})),request,principal)


from api.schemas.runtime_health import SystemStatusResponse
from subsystems.line.runtime_status_query import RuntimeStatusQuery


def get_runtime_status_query():
    return RuntimeStatusQuery(open_line_unit_of_work)


@mobile_router.post('/runtime/query', response_model=BaseResponse[SystemStatusResponse])
def mobile_runtime_query(body:MobileAuth):
    _mobile(body.line_id_token,LineCapability.MONITOR_READ)
    try:
        return BaseResponse(data=SystemStatusResponse.model_validate(get_runtime_status_query().query()))
    except Exception as error:
        raise typed_http_error(503, 'unavailable', 'runtime_status_unavailable',
                               '系統狀態暫時無法讀取，請稍後再試。', 'runtime-status', retryable=True) from error


def has_alert_manager(principal):
    from api.dependencies.admin_auth import has_required_capability
    return has_required_capability(principal,LineCapability.ALERT_MANAGE.value)


class MobileTargetPreview(AlertAdminTargetRequest,MobileAuth):
    pass


class MobileTargetApply(AlertAdminTargetApplyRequest,MobileAuth):
    pass


@mobile_router.post('/runtime/add/preview')
def mobile_target_preview(body:MobileTargetPreview):
    from api.routes.runtime_health import preview_add_admin_target
    principal=_mobile(body.line_id_token,LineCapability.ALERT_MANAGE)
    return preview_add_admin_target(AlertAdminTargetRequest(**body.model_dump(exclude={'line_id_token'})),principal)


@mobile_router.post('/runtime/add')
def mobile_target_apply(body:MobileTargetApply,request:Request):
    from api.routes.runtime_health import add_admin_target
    principal=_mobile(body.line_id_token,LineCapability.ALERT_MANAGE)
    return add_admin_target(AlertAdminTargetApplyRequest(**body.model_dump(exclude={'line_id_token'})),request,principal)


class MobileTargetTogglePreview(AlertTargetEnabledRequest,MobileAuth):
    pass


class MobileTargetToggleApply(AlertTargetEnabledApplyRequest,MobileAuth):
    pass


@mobile_router.post('/runtime/{identity}/toggle/preview')
def mobile_target_toggle_preview(identity:int,body:MobileTargetTogglePreview):
    from api.routes.runtime_health import preview_set_target_enabled
    principal=_mobile(body.line_id_token,LineCapability.ALERT_MANAGE)
    return preview_set_target_enabled(identity,AlertTargetEnabledRequest(**body.model_dump(exclude={'line_id_token'})),principal)


@mobile_router.post('/runtime/{identity}/toggle')
def mobile_target_toggle_apply(identity:int,body:MobileTargetToggleApply,request:Request):
    from api.routes.runtime_health import set_target_enabled
    principal=_mobile(body.line_id_token,LineCapability.ALERT_MANAGE)
    return set_target_enabled(identity,AlertTargetEnabledApplyRequest(**body.model_dump(exclude={'line_id_token'})),request,principal)


@mobile_router.post('/identity/{identity}/query',response_model=BaseResponse[CanonicalLineReviewResponse])
def mobile_identity_query(identity:Annotated[int,Path(gt=0)],body:MobileAuth):
    _mobile(body.line_id_token,LineCapability.REVIEW_READ)
    from api.dependencies.line_identity import get_line_identity_review_application
    from api.routes.line_mobile_admin import _review_view
    from domains.line.identities import LineReviewRequestId
    from subsystems.line.identity_review_application import LineReviewNotFoundError
    try:
        item=get_line_identity_review_application().get(LineReviewRequestId(identity))
    except LineReviewNotFoundError:
        raise typed_http_error(404,'not_found','line_review_not_found','此身分審核事項已更新，請重新整理。','notification-identity') from None
    return BaseResponse(data=_review_view(item))
