"""Authenticated, zero-effect LINE message rendering from typed owner read models."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, ContextManager, Literal, Protocol

from domains.line.configuration import LineConfigurationKind
from shared_kernel.identities import ActorContext
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.message_configuration import render_message_template
from subsystems.line.message_copy_catalog import default_copy_templates, effective_copy_definition, render_copy_payload


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
    baby_info: str = ""
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


@dataclass(frozen=True)
class PreviewNode:
    kind: Literal["text", "box", "button", "separator"]
    text: str = ""
    bold: bool = False
    size: str = "sm"
    layout: str = "vertical"
    primary: bool = False
    action_description: str = ""
    children: tuple[PreviewNode, ...] = ()


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

_RETIRED = {"LU96-M1-LEAVE-EXTENSION-CARD-V1", "LU96-M3-LEAVE-AGREE-CARD-V1", "LU96-M3-LEAVE-DISAGREE-CARD-V1","new_user_d1", "new_user_d2", "new_user_d3", "LU96-M3-ZERO-POOL-CARD-V1",
            "LU96-ORDER-PRE-START-REMINDER-CARD-V1", "LU96-ORDER-SECOND-PAYMENT-REMINDER-CARD-V1",
            "LINE-SERVICE-DAY-LOG-REMINDER-TEXT-V1"}
_IDENTITY_TEMPLATES = (
    "staff_switch_success", "staff_switch_fail", "staff_menu_not_set", "esc_success", "esc_fail",
    "bind_link_msg", "register_success", "bind_success_new_order", "bind_success_existing",
    "bind_confirm_rebind", "bind_fail_no_data", "client_rebind_approved", "client_rebind_rejected",
    "staff_verification_requested", "staff_verification_rejected",
)
_CURRENT_FLOW_PREVIEWS = (
    ("contract-signing-client", "簽署提醒－客戶", "text"),
    ("contract-signing-staff", "簽署提醒－月嫂", "text"),
    ("payment-overdue-deposit", "訂金逾期－人工提醒客戶", "text"),
    ("payment-overdue-first", "第一期款逾期－人工提醒案件群組", "text"),
    ("payment-overdue-second", "第二期款逾期－人工提醒案件群組", "text"),
    ("service-day-log-reminder", "服務日誌－工會發送案件群組提醒", "text"),
    ("deposit-reminder", "訂金繳費提醒卡", "flex"),
    ("deposit-settled", "訂金已確認入帳卡", "flex"),
    ("deposit-assistance", "訂金專人協助－受理回覆", "text"),
    ("group-bound", "案件群組－設定完成", "text"),
    ("group-invitations-queued", "案件群組－邀請排入發送", "text"),
    ("group-invitation-customer", "案件群組邀請卡－客戶", "flex"),
    ("service-start-inquiry", "服務開始－代班接案意願詢問", "flex"),
    ("service-start-result", "服務開始－群組日期結果紀錄", "text"),
    ("service-start-normal-received", "服務當天－服務正常受理回覆", "text"),
    ("service-start-help-received", "服務當天－協助需求受理回覆", "text"),
    ("group-invitation-staff", "案件群組邀請卡－月嫂", "flex"),
    ("group-error-invitation-url", "案件群組－尚未設定邀請網址", "text"),
    ("group-format-invite", "群組指令－發送邀請格式錯誤", "text"),
    ("group-error-admin", "案件群組－尚未綁定工會身分", "text"),
    ("group-error-order", "案件群組－找不到訂單", "text"),
    ("group-error-unbound", "案件群組－尚未設定群組", "text"),
    ("group-error-identity", "案件群組－客戶或月嫂尚未綁定", "text"),
    ("group-error-cancelled", "案件群組－訂單已取消", "text"),
    ("group-error-unpaid", "案件群組－訂金尚未核銷", "text"),
    ("group-error-occupied", "案件群組－已綁定其他訂單", "text"),
    ("group-format-empty", "群組指令－缺案件與網址", "text"),
    ("group-format-case", "群組指令－缺案件編號", "text"),
    ("group-format-url", "群組指令－缺邀請網址", "text"),
    ("group-format-spacing", "群組指令－缺分隔空白", "text"),
    ("group-format-split", "群組指令－網址被拆開", "text"),
    ("group-format-invalid-case", "群組指令－案件編號格式錯誤", "text"),
    ("group-format-invalid-url", "群組指令－邀請網址格式錯誤", "text"),
    ("candidate-willing-received", "候選月嫂－願意承接受理", "text"),
    ("matching-willing-received", "正式媒合－月嫂意願受理", "text"),
    ("matching-customer-accepted", "客戶推薦－接受配對回覆", "text"),
    ("matching-customer-assistance", "客戶推薦－專人協助回覆", "text"),
    ("matching-customer-response", "客戶推薦－選擇受理回覆", "text"),
    ("service-progress", "服務進度查詢結果", "text"),
    ("service-progress-unbound", "服務進度－未綁定提示", "text"),
    ("service-registration", "服務登記入口訊息", "text"),
    ("service-registration-unavailable", "服務登記入口尚未設定", "text"),
    ("identity-staff-link", "月嫂身分資料填寫入口", "text"),
    ("identity-admin-link", "工會帳號綁定入口", "text"),
    ("runtime-system-health", "系統健康異常－管理員通知", "text"),
)
_CURRENT_FLOW_IDS = {row[0] for row in _CURRENT_FLOW_PREVIEWS}
_BUILTINS = (
    ("card-caregiver-information", "月嫂案件資訊卡（一）", "flex", True, True, False),
    ("card-caregiver-information-2", "月嫂案件資訊卡（二）", "flex", True, True, False),
    ("card-customer-profiles", "月嫂資料與確認卡", "flex", True, True, False),
    ("card-customer-confirmation", "客戶完整推薦確認包", "flex", True, True, False),
    ("card-candidate-information-1", "候選聯絡－訂單資訊一", "flex", True, True, False),
    ("card-candidate-information-2", "候選聯絡－訂單資訊二", "flex", True, True, False),
    ("card-candidate-information-3", "候選聯絡－每週服務說明", "flex", True, True, False),
    ("card-union-question", "工會詢問客戶卡", "flex", True, False, True),
    ("card-union-answer", "工會回覆月嫂卡", "flex", True, True, True),
    ("service-menu", "服務與問答導覽卡", "flex", False, False, False),
    ("order-update-menu", "修改訂單資訊導覽卡", "flex", False, False, False),
    ("service-contact", "呼叫專員－需求受理", "text", False, False, False),
    ("service-resolved", "客服案件處理完成", "text", False, False, False),
    ("service-flow", "服務流程說明", "text", False, False, False),
    ("service-payment", "收費與補助說明", "text", False, False, False),
    ("service-profile-update", "登記資料修改受理", "text", False, False, False),
    ("service-order-update", "訂單資訊修改受理", "text", False, False, False),
    ("service-other", "其他問題－自助服務導覽", "flex", False, False, False),
    ("identity-pending", "身分申請受理通知", "text", False, False, False),
    ("identity-bound-customer", "客戶綁定成功", "text", False, False, False),
    ("identity-bound-staff", "月嫂綁定成功", "text", False, False, False),
    ("identity-bound-admin", "工會人員綁定成功", "text", False, False, False),
)


class LineMessagePreviewApplication:
    def __init__(self, configuration, reader_factory: Callable[[], ContextManager[MessagePreviewReader]]):
        self._configuration = configuration
        self._reader_factory = reader_factory

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
    def _catalog(templates, rules):
        by_id = {t["id"]: t for t in templates.get("templates", [])}
        references = [("welcome", "customer_onboarding_welcome")]
        references += [(r["id"], r["template_id"]) for r in rules.get("rules", [])
                       if r["template_id"] != "customer_onboarding_welcome" and r["template_id"] not in _RETIRED]
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
                           for key, name, fmt, case, staff, draft in _BUILTINS)
        descriptors.extend(PreviewDescriptor(key, None, name, fmt, False, False, True)
                           for key, name, fmt in _CURRENT_FLOW_PREVIEWS)
        return tuple(descriptors)

    def options(self, kind: str, search: str, after: str | None, actor: ActorContext) -> PreviewOptionPage:
        require_line_capability(actor, LineCapability.CONFIG_READ)
        with self._reader_factory() as reader:
            return reader.options(kind, search, after)

    def render(self, key: str, content: str | None, case_no: str | None,
               staff_id: int | None, actor: ActorContext, *, sample: bool = False) -> PreviewResult:
        key = {"template-bind_success_new_order": "identity-bound-customer", "template-staff_switch_success": "identity-bound-staff"}.get(key, key)
        templates, rules = self._definitions(actor)
        descriptor = next((d for d in self._catalog(templates, rules) if d.id == key), None)
        if descriptor is None:
            raise MessagePreviewNotFound("message")
        if descriptor.template_id in {'LINE-ORDER-SERVICE-START-DAY-CARD-V1',
                'LINE-SECOND-PAYMENT-DUE-TEXT-V1', 'LINE-SECOND-PAYMENT-SETTLED-TEXT-V1',
                'LINE-SERVICE-COMPLETION-TEXT-V1'} and not sample:
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
                    candidate["content"] = apply_copy_payload(template["content"], content, copy_fields(template["content"]), {v: "{" + v + "}" for v in declared})
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
        elif key in {"card-union-question", "card-union-answer"}:
            if content and content.lstrip().startswith("{"):
                # Stored reusable card copy is independent of per-case authored text.
                authored_content = "工會於案件中輸入的詢問或回覆內容（公版範例）"
            else:
                authored_content = content
            if not content or not content.strip():
                return PreviewResult("unavailable", "請輸入僅供預覽的工會詢問或回覆文案，不會儲存或發送。", "flex", facts=tuple(facts))
            from subsystems.scheduling.matching_line_cards import candidate_customer_question_card, candidate_caregiver_answer_card
            payload = json.loads(candidate_customer_question_card(case.case_no, authored_content, "https://preview.invalid/question")
                if key == "card-union-question" else candidate_caregiver_answer_card(case.case_no, authored_content, "preview-only", "https://preview.invalid/answer"))
        elif key in {"service-menu", "service-other", "order-update-menu"}:
            from subsystems.line.service_help_application import _service_menu_payload, _order_update_menu_payload
            payload = _order_update_menu_payload() if key == "order-update-menu" else _service_menu_payload()
        elif key in {"service-flow", "service-payment", "service-profile-update", "service-order-update"}:
            from domains.customer_service.ticket import CustomerServiceCategory
            from subsystems.line.service_help_application import _SERVICE_FLOW_REPLY, _PAYMENT_REPLY, _TICKET_ACKNOWLEDGEMENTS, _ORDER_UPDATE_ACKNOWLEDGEMENT
            payload = {"type": "text", "text": {"service-flow": _SERVICE_FLOW_REPLY, "service-payment": _PAYMENT_REPLY,
                "service-profile-update": _TICKET_ACKNOWLEDGEMENTS[CustomerServiceCategory.PROFILE_UPDATE],
                "service-order-update": _ORDER_UPDATE_ACKNOWLEDGEMENT}[key]}
        elif key in {"service-contact", "service-resolved", "identity-pending"} or key.startswith("identity-bound-"):
            from subsystems.line.message_copy import CONTACT_RECEIVED, CONTACT_RESOLVED, IDENTITY_PENDING, IDENTITY_SUCCESS_DEFAULTS
            payload = {"type": "text", "text": {"service-contact": CONTACT_RECEIVED, "service-resolved": CONTACT_RESOLVED,
                "identity-pending": IDENTITY_PENDING}.get(key, IDENTITY_SUCCESS_DEFAULTS.get(key.removeprefix("identity-bound-"), ""))}
        elif descriptor.template_id == _LEAVE:
            if not leave:
                return PreviewResult("unavailable", "此案件沒有可用的月嫂請假紀錄，無法產生請假確認卡。", "flex", facts=tuple(facts))
            from subsystems.line.staff_leave_customer_coordination import _inquiry_payload
            payload = _inquiry_payload(leave.request_id, leave.version, case.case_no, leave.start_date,
                                       leave.end_date, description=rendered_payload["text"])
        elif descriptor.id == "card-customer-profiles":
            from subsystems.scheduling.matching_line_cards import customer_profiles_card
            note = rendered_payload["text"] if rendered_payload else ""
            profiles = (asdict(staff),)
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
        if key in default_copy_templates():
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
            if key == "runtime-system-health":
                copy_values["status"] = "critical"
            payload = render_copy_payload(templates, key, payload, copy_values, copy_content)
        if sample:
            from subsystems.line.message_preview_samples import sample_bindings
            binding_content = authored_content if key in {"card-union-question", "card-union-answer"} else content
            facts = flow_facts if flow_facts is not None else sample_bindings(descriptor, template, binding_content, rendered_payload.get("text", "") if rendered_payload else "")
        if payload.get("type") == "text":
            return PreviewResult("ready", "公版範例資料，非真實案件或月嫂；不會儲存或發送。" if sample else "使用資料庫資訊預覽；不會實際發送。", "text", str(payload["text"]), facts=tuple(facts))
        container = payload["contents"]
        bubbles = container["contents"] if container["type"] == "carousel" else [container]
        return PreviewResult("ready", "公版範例資料，使用正式卡片組裝；按鈕只供預覽，不會執行。" if sample else "使用正式卡片組裝邏輯；按鈕僅展示動作，不會送出。", "flex",
                             bubbles=tuple(_project_node(b) for b in bubbles), facts=tuple(facts))


def _project_node(node) -> PreviewNode:
    """Project display-only nodes; never expose postbacks, tokens, URLs or provider identities."""
    kind = node["type"]
    if kind == "text":
        return PreviewNode("text", text=str(node.get("text", "")), bold=node.get("weight") == "bold",
                           size=str(node.get("size", "sm")))
    if kind == "button":
        action = node["action"]
        description = "開啟相關服務頁面" if action["type"] == "uri" else "將選擇交由原業務流程處理"
        return PreviewNode("button", text=str(action["label"]), primary=node.get("style") == "primary",
                           action_description=description + "；此處只預覽，不會執行。")
    if kind == "separator":
        return PreviewNode("separator")
    children = [node[k] for k in ("header", "hero", "body", "footer") if k in node] if kind == "bubble" else node.get("contents", [])
    if kind not in {"bubble", "box"}:
        raise ValueError("unsupported preview component")
    return PreviewNode("box", layout="horizontal" if node.get("layout") in {"horizontal", "baseline"} else "vertical",
                       children=tuple(_project_node(child) for child in children))
