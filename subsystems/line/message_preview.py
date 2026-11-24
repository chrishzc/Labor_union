"""
File: message_preview.py
Description: 協調 LINE 訊息與互動卡片的唯讀公版目錄與安全預覽渲染。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Callable, ContextManager, Literal, Protocol, TypedDict

from domains.line.configuration import LineConfigurationKind
from shared_kernel.identities import ActorContext
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.message_configuration import render_message_template
from subsystems.line.message_copy_catalog import (
    INACTIVE_CANDIDATE_COPY_TEMPLATE_IDS, RETIRED_PAYMENT_RECEIPT_TEMPLATE_IDS,
    RETIRED_SERVICE_COMPLETION_PUSH_TEMPLATE_ID, RETIRED_CUSTOMER_SERVICE_TEMPLATE_IDS,
    RETIRED_SIGNING_REMINDER_TEMPLATE_IDS, RETIRED_START_DAY_REPORT_TEMPLATE_IDS,
    default_copy_templates, effective_copy_definition, render_copy_payload,
)
from subsystems.line.service_completion_notifications import RETIRED_SERVICE_COMPLETION_PUSH_EVENT_CODE


@dataclass(frozen=True)
class PreviewOption:
    id: str
    label: str


@dataclass(frozen=True)
class PreviewOptionPage:
    items: tuple[PreviewOption, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class PreviewCase:
    case_no: str
    client_name: str
    start_date: str
    end_date: str
    city: str
    service_type: str
    service_time: str
    multi_birth_count: str = ""
    residence_type: str = ""


@dataclass(frozen=True)
class PreviewStaff:
    id: int
    name: str
    city: str
    care_babies: int | None
    has_massage_cert: bool
    service_regions: tuple[str, ...]
    special_skills: tuple[str, ...]


@dataclass(frozen=True)
class PreviewLeave:
    request_id: int
    version: int
    start_date: str
    end_date: str


@dataclass(frozen=True)
class PreviewCardSource:
    payload_json: str
    table_documents_json: str = ''


class MessagePreviewReader(Protocol):
    def options(self, kind: str, search: str, after: str | None) -> PreviewOptionPage: ...
    def case(self, case_no: str) -> PreviewCase | None: ...
    def staff(self, staff_id: int) -> PreviewStaff | None: ...
    def leave(self, case_no: str, staff_id: int | None) -> PreviewLeave | None: ...
    def service_date(self, case_no: str, staff_id: int) -> str | None: ...
    def payment_values(self, case_no: str) -> dict[str, str]: ...
    def card(self, case_no: str, staff_id: int, kind: str) -> PreviewCardSource | None: ...


@dataclass(frozen=True)
class PreviewDescriptor:
    id: str
    template_id: str | None
    name: str
    format: Literal["text", "flex"]
    requires_case: bool
    requires_staff: bool
    builtin: bool = False
    allows_draft: bool = False


class PreviewAppearance(TypedDict, total=False):
    background_color: str
    color: str
    border_color: str
    border_width: int
    corner_radius: int
    padding_top: int
    padding_right: int
    padding_bottom: int
    padding_left: int
    gap: int
    margin: int
    width: int
    height: int
    flex: int
    align: Literal["start", "center", "end"]
    justify_content: Literal["start", "center", "end", "space-between", "space-around", "space-evenly"]
    align_items: Literal["start", "center", "end", "stretch"]
    button_style: Literal["primary", "secondary", "link"]
    bubble_size: Literal["nano", "micro", "deca", "hecto", "kilo", "mega", "giga"]
    wrap: bool


@dataclass(frozen=True)
class PreviewNode:
    kind: Literal["text", "box", "button", "separator", "image"]
    text: str = ""
    bold: bool = False
    size: str = "sm"
    layout: str = "vertical"
    primary: bool = False
    action_description: str = ""
    children: tuple[PreviewNode, ...] = ()
    image_data: str = ''
    appearance: PreviewAppearance | None = None


@dataclass(frozen=True)
class PreviewResult:
    status: Literal["ready", "needs_subject", "unavailable"]
    note: str
    format: Literal["text", "flex"]
    text: str = ""
    bubbles: tuple[PreviewNode, ...] = ()
    facts: tuple[PreviewOption, ...] = ()


class MessagePreviewNotFound(ValueError):
    pass


_LEAVE = "LU96-M1-LEAVE-EXTENSION-CARD-V1"
_STAFF_VARIABLES = {"staff_name", "caregiver_name"}
_CASE_VARIABLES = {"name", "client_name", "case_no", "planned_start_date", "service_date",
                   "first_payment_amount", "first_payment_due_date", "second_payment_amount",
                   "second_payment_due_date", "first_payment_status", "second_payment_status",
                   "first_payment_notice", "caregiver_names", "response_token"}

_RETIRED = {"LU96-M4-SAFE-ALERT-CARD-V1", "LU96-M4-COMPLAINT-HIGH-CARD-V1", "LU96-M1-LEAVE-EXTENSION-CARD-V1", "LU96-M3-LEAVE-AGREE-CARD-V1", "LU96-M3-LEAVE-DISAGREE-CARD-V1","new_user_d1", "new_user_d2", "new_user_d3", "LU96-M3-ZERO-POOL-CARD-V1",
            "LU96-ORDER-PRE-START-REMINDER-CARD-V1", "LU96-ORDER-SECOND-PAYMENT-REMINDER-CARD-V1",
            "LINE-SERVICE-DAY-LOG-REMINDER-TEXT-V1", "service-day-log-reminder",
            "customer_onboarding_welcome", "welcome"}
_UNLISTED_RULE_TEMPLATES = {"LINE-SECOND-PAYMENT-DUE-TEXT-V1"}
_IDENTITY_TEMPLATES = (
    "staff_switch_success", "bind_success_new_order", "client_rebind_rejected",
    "staff_verification_rejected",
)
_CURRENT_FLOW_PREVIEWS = (
    ("registration-approved-citizen", "市民需求申請核准通知", "text"),
    ("registration-approved-non-citizen", "非市民需求申請核准通知", "text"),
    ("staff-leave-completed", "月嫂請假完成正式排班通知", "text"),
    ("staff-web-expiry-reminder", "月嫂個人網頁項目到期提醒", "text"),
    ("payment-overdue-deposit", "訂金逾期提醒卡", "flex"),
    ("payment-overdue-first", "第一期款逾期提醒卡", "flex"),
    ("payment-overdue-second", "第二期款逾期提醒卡", "flex"),
    ("payment-first-reminder", "開工當天問候－含第一期款提醒", "text"),
    ("payment-first-greeting", "開工當天問候－無第一期款餘額", "text"),
    ("cancellation-notice-settlement", "取消結算明細通知", "text"),
    ("cancellation-notice-refund", "取消結算退款完成通知", "text"),
    ("cancellation-notice-collection", "取消結算補收入帳通知", "text"),
    ("payment-second-reminder", "第二期款繳費提醒卡", "flex"),
    ("deposit-reminder", "訂金繳費提醒卡", "flex"),
    ("payment-reminder-ack", "繳費提醒回覆－已匯款確認", "text"),
    ("group-invitation-customer", "案件群組邀請卡－客戶", "flex"),
    ("helper-menu-card", "案件群組－月嫂小幫手選單卡", "flex"),
    ("helper-menu-completed", "案件群組－服務已完成小幫手選單卡", "flex"),
    ("helper-satisfaction-survey", "滿意度調查問卷－案件群組回覆", "text"),
    ("helper-confirm-start-card", "確認開工日－客戶確認卡", "flex"),
    ("helper-confirm-start-completed", "確認開工日－自動排班完成回覆", "text"),
    ("helper-schedule-unconfirmed", "服務排程－尚未確認開工日提示", "text"),
    ("helper-postponement-card", "雙方合意延期－客戶確認卡", "flex"),
    ("helper-postponement-completed", "雙方合意延期－排程更新完成回覆", "text"),
    ("helper-guidelines-card", "客戶常見疑問－導覽卡", "flex"),
    ("helper-faq-ingredients", "客戶常見疑問－食材採買與準備標準回答", "text"),
    ("helper-faq-hours", "客戶常見疑問－每日服務時數與範圍標準回答", "text"),
    ("helper-faq-subsidy", "客戶常見疑問－政府補助申請與撥款標準回答", "text"),
    ("service-start-inquiry", "服務開始－代班接案意願詢問", "flex"),
    ("service-start-result", "服務開始－群組日期結果紀錄", "text"),
    ("group-invitation-staff", "案件群組邀請卡－月嫂", "flex"),
    ("candidate-willing-received", "初步候選聯絡－月嫂意願受理", "text"),
    ("matching-willing-received", "正式媒合－月嫂意願受理", "text"),
    ("matching-customer-accepted", "正式媒合－客戶接受配對回覆", "text"),
    ("matching-customer-response", "正式媒合－客戶選擇受理回覆", "text"),
    ("service-progress", "服務進度查詢結果", "text"),
    ("service-progress-unbound", "服務進度－未綁定提示", "text"),
    ("service-registration", "服務登記入口訊息", "text"),
    ("service-registration-unavailable", "服務登記入口尚未設定", "text"),
    ("identity-customer-link", "客戶身分綁定入口", "text"),
    ("identity-staff-link", "月嫂身分資料填寫入口", "text"),
    ("identity-admin-link", "工會帳號綁定入口", "text"),
)
_CURRENT_FLOW_IDS = {row[0] for row in _CURRENT_FLOW_PREVIEWS}
_UNLISTED_FORMAL_CARDS = {'card-caregiver-information', 'card-caregiver-information-2', 'card-customer-profiles'}
_BUILTINS = (
    ("card-caregiver-information", "正式媒合－月嫂案件資訊卡（一）", "flex", True, True, False),
    ("card-caregiver-information-2", "正式媒合－月嫂案件資訊卡（二）", "flex", True, True, False),
    ("card-customer-profiles", "正式媒合－月嫂資料與客戶確認卡", "flex", True, True, False),
    ("card-customer-confirmation", "正式媒合－客戶完整推薦確認包", "flex", True, True, False),
    ("card-candidate-information-package", "初步候選聯絡－案件資訊整包", "flex", True, True, False),
    ("card-candidate-information-1", "初步候選聯絡－訂單資訊一", "flex", True, True, False),
    ("card-candidate-information-2", "初步候選聯絡－訂單資訊二", "flex", True, True, False),
    ("card-candidate-information-3", "初步候選聯絡－每週服務說明", "flex", True, True, False),
    ("service-menu", "服務與問答導覽卡", "flex", False, False, False),
    ("identity-pending", "身分申請受理通知", "text", False, False, False),
    ("identity-bound-customer", "客戶綁定成功", "text", False, False, False),
    ("identity-bound-staff", "月嫂綁定成功", "text", False, False, False),
    ("identity-bound-admin", "工會人員綁定成功", "text", False, False, False),
)


class LineMessagePreviewApplication:
    def __init__(self, configuration, reader_factory: Callable[[], ContextManager[MessagePreviewReader]], image_renderer=None):
        self._configuration = configuration
        self._reader_factory = reader_factory
        self._image_renderer = image_renderer

    def _definitions(self, actor):
        require_line_capability(actor, LineCapability.CONFIG_READ)
        snapshot = self._configuration.get(LineConfigurationKind.MESSAGE_TEMPLATES, actor)
        if snapshot.revision.value == 0 and snapshot.definition_json == "{}":
            from subsystems.line.configuration_store import read_raw_config
            templates = read_raw_config("message_templates")
        else:
            templates = json.loads(snapshot.definition_json)
        rules = json.loads(self._configuration.get(LineConfigurationKind.NOTIFICATION_RULES, actor).definition_json)
        return effective_copy_definition(templates), rules

    def catalog(self, actor: ActorContext) -> tuple[PreviewDescriptor, ...]:
        templates, rules = self._definitions(actor)
        return self._catalog(templates, rules)

    @staticmethod
    def _catalog(templates, rules, *, include_unlisted=False):
        by_id = {t["id"]: t for t in templates.get("templates", [])}
        references = [
            (r["id"], r["template_id"]) for r in rules.get("rules", [])
            if r["template_id"] not in _RETIRED and r["template_id"] not in INACTIVE_CANDIDATE_COPY_TEMPLATE_IDS
            and r["template_id"] not in RETIRED_CUSTOMER_SERVICE_TEMPLATE_IDS
            and r["template_id"] not in RETIRED_SIGNING_REMINDER_TEMPLATE_IDS
            and r["template_id"] not in RETIRED_PAYMENT_RECEIPT_TEMPLATE_IDS
            and r["template_id"] not in RETIRED_START_DAY_REPORT_TEMPLATE_IDS
            and r["template_id"] != RETIRED_SERVICE_COMPLETION_PUSH_TEMPLATE_ID
            and r.get("event_code") != RETIRED_SERVICE_COMPLETION_PUSH_EVENT_CODE
            and (include_unlisted or r["template_id"] not in _UNLISTED_RULE_TEMPLATES)
        ]
        referenced = {template_id for _, template_id in references}
        references += [("template-" + key, key) for key in _IDENTITY_TEMPLATES if key not in referenced and key not in {"bind_success_new_order", "staff_switch_success"}]
        descriptors = []
        for key, template_id in references:
            template = by_id.get(template_id)
            if not template:
                continue
            variables = {v["name"] for v in template.get("variables", [])}
            is_card = template_id == _LEAVE or template["message_type"] == "flex"
            descriptors.append(PreviewDescriptor(
                key, template_id, str(template.get("name") or key), "flex" if is_card else "text",
                is_card or bool(variables & _CASE_VARIABLES),
                bool(variables & _STAFF_VARIABLES) or "service_date" in variables,
                key.startswith("template-"),
            ))
        descriptors.extend(PreviewDescriptor(key, None, name, fmt, case, staff, True, draft)
                           for key, name, fmt, case, staff, draft in _BUILTINS
                           if include_unlisted or key not in _UNLISTED_FORMAL_CARDS)
        descriptors.extend(PreviewDescriptor(key, None, name, fmt, False, False, True)
                           for key, name, fmt in _CURRENT_FLOW_PREVIEWS)
        return tuple(descriptors)

    def options(self, kind: str, search: str, after: str | None, actor: ActorContext) -> PreviewOptionPage:
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._reader_factory() as reader:
            return reader.options(kind, search, after)

    def render(self, key: str, content: str | None, case_no: str | None,
               staff_id: int | None, actor: ActorContext, *, sample: bool = False) -> PreviewResult:
        key = {"template-bind_success_new_order": "identity-bound-customer", "template-staff_switch_success": "identity-bound-staff",
               "service-other": "service-menu"}.get(key, key)
        cancellation_copy = key.startswith("cancellation-notice-")
        cancellation_draft = content if cancellation_copy else None
        templates, rules = self._definitions(actor)
        # The library lists the bundled delivery. Existing direct preview callers
        # keep their readonly contract; no send operation or saved copy is retired.
        descriptor = next((d for d in self._catalog(templates, rules, include_unlisted=True) if d.id == key), None)
        if descriptor is None:
            raise MessagePreviewNotFound("message")
        if descriptor.template_id == 'LINE-SECOND-PAYMENT-DUE-TEXT-V1' and not sample:
            return PreviewResult('unavailable', '此群組通知請使用公版預覽；正式內容由本案流程結果帶入。', descriptor.format)
        reader_factory = self._reader_factory
        if sample:
            from subsystems.line.message_preview_samples import CASE, STAFF, VALUES, DEFAULT_DRAFT, public_preview_reader
            case_no = CASE.case_no if descriptor.requires_case else None
            staff_id = STAFF.id if descriptor.requires_staff else None
            reader_factory = public_preview_reader
            if descriptor.allows_draft and content is None:
                content = DEFAULT_DRAFT
        if (descriptor.requires_case and not case_no) or (descriptor.requires_staff and not staff_id):
            return PreviewResult("needs_subject", "請先選擇此訊息所需的案件或月嫂。", descriptor.format)
        facts: list[PreviewOption] = []
        values = {"url": "［服務申請入口；預覽不建立專屬連結］", "bind_url": "［身分連結入口；預覽不建立專屬連結］"}
        if sample:
            values.update(VALUES)
        case = staff = leave = card_source = None
        if case_no or staff_id:
            with reader_factory() as reader:
                case = reader.case(case_no) if case_no else None
                staff = reader.staff(staff_id) if staff_id else None
                if (case_no and case is None) or (staff_id and staff is None):
                    raise MessagePreviewNotFound("subject")
                if case:
                    values.update(name=case.client_name, client_name=case.client_name, case_no=case.case_no,
                                  planned_start_date=case.start_date)
                    facts.extend((PreviewOption("案件編號", case.case_no), PreviewOption("客戶", case.client_name),
                                  PreviewOption("服務開始日", case.start_date), PreviewOption("服務結束日", case.end_date)))
                if staff:
                    values.update(staff_name=staff.name, caregiver_name=staff.name)
                    facts.append(PreviewOption("月嫂", staff.name))
                if descriptor.template_id == _LEAVE and case:
                    leave = reader.leave(case.case_no, staff_id)
                    if leave:
                        facts.extend((PreviewOption("請假開始日", leave.start_date), PreviewOption("請假結束日", leave.end_date)))
                template = next((t for t in templates.get("templates", []) if t["id"] == descriptor.template_id), None)
                variables = {v["name"] for v in template.get("variables", [])} if template else set()
                if case and any("payment" in v for v in variables):
                    payment = reader.payment_values(case.case_no)
                    values.update(payment)
                    labels = {"first_payment_amount": "第一期款金額", "first_payment_status": "第一期款狀態",
                              "second_payment_amount": "第二期款金額", "second_payment_status": "第二期款狀態",
                              "planned_start_date": "付款提醒服務日", "second_payment_due_date": "第二期款期限"}
                    facts.extend(PreviewOption(labels[k], v) for k, v in payment.items() if k in variables and k in labels)
                if "service_date" in variables and case and staff:
                    day = reader.service_date(case.case_no, staff.id)
                    if day:
                        values["service_date"] = day
                        facts.append(PreviewOption("服務日期", day))
                if case and staff and (key == "card-customer-confirmation" or key.startswith("card-candidate-information-")):
                    card_source = reader.card(case.case_no, staff.id, key)
        template = next((t for t in templates.get("templates", []) if t["id"] == descriptor.template_id), None)
        rendered_payload = None
        flow_facts = None
        if template:
            declared = {v["name"] for v in template.get("variables", [])}
            required = {v["name"] for v in template.get("variables", []) if v.get("required")}
            if any(not values.get(v) for v in required):
                return PreviewResult("unavailable", "所選資料缺少此訊息所需的業務資訊或流程結果，無法完整預覽。",
                                     descriptor.format, facts=tuple(facts))
            candidate = dict(template)
            if content is not None:
                if template["message_type"] == "flex":
                    from subsystems.line.message_copy import copy_fields, apply_copy_payload
                    fields = copy_fields(template['content'])
                    import re
                    displayed = set(re.findall(r'\{([A-Za-z][A-Za-z0-9_]*)\}', ' '.join(field['content'] for field in fields)))
                    candidate["content"] = apply_copy_payload(template["content"], content, fields, {v: "{" + v + "}" for v in declared & displayed})
                else:
                    candidate["content"] = content
            rendered_payload = json.loads(render_message_template({"templates": [candidate]}, template["id"],
                                          {k: v for k, v in values.items() if k in declared}).payload_json)
        if key in _CURRENT_FLOW_IDS:
            if not sample:
                return PreviewResult("unavailable", "此流程訊息請使用公版預覽，不會查詢或執行真實流程。", descriptor.format)
            from subsystems.line.message_preview_samples import current_message_sample
            payload, flow_facts = current_message_sample(key)
        elif descriptor.template_id in {"LU96-M4-SAFE-ALERT-CARD-V1", "LU96-M4-COMPLAINT-HIGH-CARD-V1"} and sample:
            from subsystems.line.human_escalation_delivery import human_alert_text
            from subsystems.line.message_preview_samples import alert_sample_values
            category, summary, entry, flow_facts = alert_sample_values()
            payload = {"type": "text", "text": human_alert_text(rendered_payload["text"], category, summary, entry)}
        elif key == "card-customer-confirmation" or key.startswith("card-candidate-information-"):
            if card_source is None:
                return PreviewResult("unavailable", "所選案件與月嫂沒有此卡片所需的正式方案、候選紀錄或完整訂單／服務日期資料，請選擇其他對象。", "flex", facts=tuple(facts))
            payload = json.loads(card_source.payload_json)
        elif key == "service-menu":
            from subsystems.line.service_help_application import _service_menu_payload
            payload = _service_menu_payload()
        elif key == "identity-pending" or key.startswith("identity-bound-"):
            from subsystems.line.message_copy import IDENTITY_PENDING, IDENTITY_SUCCESS_DEFAULTS
            payload = {"type": "text", "text": (
                IDENTITY_PENDING if key == "identity-pending"
                else IDENTITY_SUCCESS_DEFAULTS.get(key.removeprefix("identity-bound-"), "")
            )}
        elif descriptor.template_id == _LEAVE:
            if not leave:
                return PreviewResult("unavailable", "此案件沒有可用的月嫂請假紀錄，無法產生請假確認卡。", "flex", facts=tuple(facts))
            from subsystems.line.staff_leave_customer_coordination import _inquiry_payload
            payload = _inquiry_payload(leave.request_id, leave.version, case.case_no, leave.start_date,
                                       leave.end_date, description=rendered_payload["text"])
        elif descriptor.id == "card-customer-profiles":
            from subsystems.scheduling.matching_line_cards import customer_profiles_card
            note = rendered_payload["text"] if rendered_payload else ""
            from subsystems.line.message_preview_samples import STAFF_WEB_PREVIEW_URL
            profiles = ({"id": staff.id, "name": staff.name, "staff_web_url": STAFF_WEB_PREVIEW_URL},)
            payload = json.loads(customer_profiles_card(case.case_no, profiles, "preview-only", note))
        elif descriptor.id in {"card-caregiver-information", "card-caregiver-information-2"}:
            from domains.scheduling.matching_communication import MatchingNotificationKind
            from subsystems.scheduling.matching_line_cards import caregiver_information_card
            if not case.start_date or not case.end_date:
                return PreviewResult("unavailable", "案件缺少完整服務期間，無法產生案件資訊卡。", "flex", facts=tuple(facts))
            kind = MatchingNotificationKind.CAREGIVER_INFO_1 if key == "card-caregiver-information" else MatchingNotificationKind.CAREGIVER_INFO_2
            payload = json.loads(caregiver_information_card(kind,
                                                            asdict(case), "preview-only"))
        else:
            payload = rendered_payload
        copy_key = "helper-menu-card" if key == "helper-menu-completed" else key
        if copy_key in default_copy_templates():
            if sample:
                from subsystems.line.message_preview_samples import VALUES, CASE, STAFF
                copy_values = {**VALUES, "staff_name": STAFF.name, "identity_url": VALUES["bind_url"], "registration_url": VALUES["url"],
                    "recipient_count": 2, "amount_ntd": "6,000", "due_date": "2026-11-01", "service_dates": "2026-11-02、2026-11-04、2026-11-06", "service_period": "服務日期：2026-11-02、2026-11-04、2026-11-06",
                    "assignments": STAFF.name + "：2026-11-02、2026-11-04、2026-11-06", "status": "訂單成立", "start_date": CASE.start_date, "end_date": CASE.end_date,
                    "heading": "系統異常通知", "check_name": "LINE Worker（公版）", "message": "公版心跳逾期情境", "occurred_at": "2026-11-01 01:00:00",
                    "payment_stage": {"payment-overdue-deposit": "訂金", "payment-overdue-first": "第一期款", "payment-overdue-second": "第二期款"}.get(key, ""),
                    "remaining_amount": {"payment-overdue-deposit": "6,000", "payment-overdue-first": "12,000", "payment-overdue-second": "8,000"}.get(key, "")}
            else:
                copy_values = values
            copy_content = content if not descriptor.allows_draft or (content and content.lstrip().startswith("{")) else None
            if cancellation_copy:
                copy_content = cancellation_draft
            if key == "runtime-system-health":
                copy_values["status"] = "critical"
            if key == "registration-approved-non-citizen":
                copy_values["case_no"] = "A000000"
            payload = render_copy_payload(templates, copy_key, payload, copy_values, copy_content if copy_key == key else None)
        if key in {"helper-menu-card", "helper-menu-completed"}:
            from subsystems.line.message_preview_samples import CASE
            from subsystems.line.service_start_messages import render_group_helper_menu_state
            service_completed = key == "helper-menu-completed"
            payload = render_group_helper_menu_state(
                payload,
                case_no=CASE.case_no,
                planned_start_date=CASE.start_date,
                service_commenced=service_completed,
                has_confirmed_start=True,
                service_completed=service_completed,
                show_satisfaction_survey=service_completed,
            )
        if cancellation_copy:
            from subsystems.line.message_preview_samples import cancellation_notice_sample
            payload["text"] += "\n\n" + cancellation_notice_sample(key)
        if sample:
            from subsystems.line.message_preview_samples import sample_bindings
            facts = flow_facts if flow_facts is not None else sample_bindings(descriptor, template, content, rendered_payload.get("text", "") if rendered_payload else "")
        if payload.get("type") == "text":
            return PreviewResult("ready", "公版範例資料，非真實案件或月嫂；不會儲存或發送。" if sample else "使用資料庫資訊預覽；不會實際發送。", "text", str(payload["text"]), facts=tuple(facts))
        documents = {}
        if card_source and card_source.table_documents_json:
            from subsystems.line.table_image_contracts import TableDocument
            from subsystems.line.table_image_messages import with_table_images, DOCUMENTS_KEY
            models = tuple(TableDocument.from_mapping(item) for item in json.loads(card_source.table_documents_json))
            profile_count = len(payload["contents"]["contents"]) - 4 if key == "card-customer-confirmation" else 0
            payload = with_table_images(
                payload, models, candidate=key.startswith('card-candidate-information-'),
                customer_profile_count=profile_count,
            )
            documents = {item['url']: TableDocument.from_mapping(item['document']) for item in payload[DOCUMENTS_KEY]}
        container = payload["contents"]
        bubbles = container["contents"] if container["type"] == "carousel" else [container]
        return PreviewResult("ready", "公版範例資料，使用正式卡片組裝；按鈕只供預覽，不會執行。" if sample else "使用正式卡片組裝邏輯；按鈕僅展示動作，不會送出。", "flex",
                             bubbles=tuple(_project_node(b, documents, self._image_renderer) for b in bubbles), facts=tuple(facts))


_SPACING = {"none": 0, "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "xxl": 24}
_BUTTON_HEIGHTS = {"sm": 40, "md": 52}
_ALIGNMENT_ALIASES = {"flex-start": "start", "flex-end": "end"}


def _preview_pixels(value, named_sizes: dict[str, int] | None = None) -> int | None:
    if not isinstance(value, str):
        return None
    if named_sizes and value in named_sizes:
        return named_sizes[value]
    if re.fullmatch(r"[0-9]{1,4}px", value):
        pixels = int(value[:-2])
        if pixels <= 1000:
            return pixels
    return None


def _project_appearance(node, kind: str) -> PreviewAppearance | None:
    appearance: PreviewAppearance = {}
    for source, target in (
        ("backgroundColor", "background_color"), ("color", "color"), ("borderColor", "border_color"),
    ):
        value = node.get(source)
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value):
            appearance[target] = value
    for source, target in (
        ("borderWidth", "border_width"), ("cornerRadius", "corner_radius"), ("width", "width"),
        ("height", "height"), ("spacing", "gap"), ("margin", "margin"),
        ("paddingTop", "padding_top"), ("paddingEnd", "padding_right"),
        ("paddingBottom", "padding_bottom"), ("paddingStart", "padding_left"),
    ):
        value = node.get(source)
        sizes = _SPACING if source in {"spacing", "margin"} or source.startswith("padding") else None
        if source.startswith("padding"):
            value = node.get(source, node.get("paddingAll"))
        elif source == "height" and kind == "button":
            sizes = _BUTTON_HEIGHTS
        pixels = _preview_pixels(value, sizes)
        if pixels is not None:
            appearance[target] = pixels
    flex = node.get("flex")
    if type(flex) is int and 0 <= flex <= 100:
        appearance["flex"] = flex
    wrap = node.get("wrap")
    if isinstance(wrap, bool):
        appearance["wrap"] = wrap
    for source, target, choices in (
        ("align", "align", ("start", "center", "end")),
        ("justifyContent", "justify_content", ("start", "center", "end", "space-between", "space-around", "space-evenly")),
        ("alignItems", "align_items", ("start", "center", "end", "stretch")),
    ):
        value = node.get(source)
        if isinstance(value, str):
            value = _ALIGNMENT_ALIASES.get(value, value)
            if value in choices:
                appearance[target] = value
    style = node.get("style")
    if kind == "button" and style in ("primary", "secondary", "link"):
        appearance["button_style"] = style
    size = node.get("size")
    if kind == "bubble" and size in ("nano", "micro", "deca", "hecto", "kilo", "mega", "giga"):
        appearance["bubble_size"] = size
    return appearance or None


def _project_node(node, documents=None, image_renderer=None) -> PreviewNode:
    """Project display-only nodes; never expose postbacks, tokens, URLs or provider identities."""
    kind = node["type"]
    appearance = _project_appearance(node, kind)
    if kind == 'image':
        import base64
        document = (documents or {}).get(node.get('url'))
        if document is None or image_renderer is None:
            raise ValueError('table image preview renderer is unavailable')
        return PreviewNode('image', text=document.title, appearance=appearance,
            image_data='data:image/png;base64,' + base64.b64encode(image_renderer(document)).decode('ascii'))
    if kind == "text":
        return PreviewNode("text", text=str(node.get("text", "")), bold=node.get("weight") == "bold",
                           size=str(node.get("size", "sm")), appearance=appearance)
    if kind == "button":
        action = node["action"]
        description = "開啟相關服務頁面" if action["type"] == "uri" else "將選擇交由原業務流程處理"
        return PreviewNode("button", text=str(action["label"]), primary=node.get("style") == "primary",
                           action_description=description + "；此處只預覽，不會執行。", appearance=appearance)
    if kind == "separator":
        return PreviewNode("separator", appearance=appearance)
    children = [node[k] for k in ("header", "hero", "body", "footer") if k in node] if kind == "bubble" else node.get("contents", [])
    if kind not in {"bubble", "box"}:
        raise ValueError("unsupported preview component")
    return PreviewNode("box", layout="horizontal" if node.get("layout") in {"horizontal", "baseline"} else "vertical",
                       children=tuple(_project_node(child, documents, image_renderer) for child in children),
                       appearance=appearance)
