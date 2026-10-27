"""Explicit public examples for display-only previews; no database or delivery access."""

import json
import re
from contextlib import contextmanager
from dataclasses import asdict

from subsystems.line.message_preview import PreviewCase, PreviewStaff, PreviewLeave, PreviewCardSource, PreviewOption


CASE = PreviewCase("DEMO-CASE-001", "王小姐（範例）", "2026-11-02", "2026-11-30",
                   "新竹市", "日間到府服務", "09:00～17:00", "單胞胎（範例）", "電梯大樓（範例）")
STAFF = PreviewStaff(1, "陳月嫂（範例）", "新竹市", 1, True, ("新竹市", "竹北市"), ("新生兒照護", "月子餐"))
LEAVE = PreviewLeave(1, 1, "2026-11-10", "2026-11-11")
DEFAULT_DRAFT = "請協助確認本次服務時段，謝謝。"
VALUES = {
    **asdict(CASE), "name": CASE.client_name, "planned_start_date": CASE.start_date,
    "staff_name": STAFF.name, "caregiver_name": STAFF.name, "service_date": "2026-11-03",
    "url": "［公版服務申請連結；不建立實際連結］", "bind_url": "［公版身分綁定連結；不建立實際連結］",
    "first_payment_amount": "NT$ 12,000", "first_payment_status": "尚未繳納（範例）",
    "first_payment_notice": "第一期款尚待繳納：12,000 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。",
    "caregiver_names": STAFF.name, "response_token": "0" * 64,
    "first_payment_due_date": "2026-10-30", "second_payment_amount": "24,000",
    "second_payment_status": "尚未繳納（範例）", "second_payment_due_date": "2026-11-20",
    "leave_start_date": LEAVE.start_date, "leave_end_date": LEAVE.end_date,
    "week_number": 1, "serial_number": 1, "week_start_date": "2026-11-02", "week_end_date": "2026-11-08",
    "service_hours_per_day": 8, "weekly_work_days": 5, "weekly_hours": 40, "employer_name": CASE.client_name,
}
LABELS = {
    "case_no": "案件編號", "name": "客戶姓名", "client_name": "客戶姓名", "start_date": "服務開始日",
    "end_date": "服務結束日", "planned_start_date": "預計服務開始日", "city": "服務縣市",
    "service_type": "服務方式", "service_time": "服務時段", "baby_info": "寶寶資訊", "residence_type": "居住型態",
    "staff_name": "月嫂姓名", "caregiver_name": "月嫂姓名", "service_date": "服務日期",
    "url": "服務申請連結", "bind_url": "身分綁定連結", "first_payment_amount": "第一期款金額",
    "first_payment_status": "第一期款狀態", "first_payment_due_date": "第一期款期限",
    "first_payment_notice": "第一期款繳款段落", "caregiver_names": "當日排班月嫂", "response_token": "服務狀況回覆識別",
    "second_payment_amount": "第二期款金額", "second_payment_status": "第二期款狀態", "second_payment_due_date": "第二期款期限",
    "leave_start_date": "請假開始日", "leave_end_date": "請假結束日", "week_number": "週數", "serial_number": "序號",
    "week_start_date": "每週開始日", "week_end_date": "每週結束日", "service_hours_per_day": "每日服務時數",
    "weekly_work_days": "每週工作日數", "weekly_hours": "每週工時", "employer_name": "雇主姓名",
    "content": "預覽文案", "description": "通知說明", "resume": "履歷下載按鈕",
}
INFO_1 = ("case_no", "start_date", "end_date", "city", "service_type")
WEEKLY = ("week_number", "serial_number", "case_no", "employer_name", "week_start_date", "week_end_date",
          "service_hours_per_day", "weekly_work_days", "weekly_hours")
ORDER_FACTS = {
    **VALUES, "assigned_start_date": CASE.start_date, "assigned_end_date": CASE.end_date,
    "service_days": 20, "address": "新竹市範例路（公版地址）", "phone": "［公版聯絡電話］", "requires_cooking": True,
    "deposit_amount": 6000, "deposit_due_date": "2026-10-25", "first_payment_amount": 12000,
    "second_payment_amount": 24000, "floor_fee": 0, "total_employer_self_pay_payable": 42000,
    "special_holidays": "週末休息（範例）", "notes": "公版服務注意事項",
    "dietary_habits": "葷食，可接受中藥（範例）", "vegetarian_preference": "可接受蛋奶素（範例）",
    "alcohol_ratio": "不加酒（範例）", "cooking_oil_type": "橄欖油（範例）", "maternal_allergy": "無（範例）",
    "special_care_notes": "依需求確認（範例）", "meal_preferences": "清淡飲食（範例）", "cooking_tools": "瓦斯爐、電鍋（範例）",
    "bath_water_prep": "家人協助（範例）", "breastfeeding_method": "母乳（範例）", "holiday_pricing_terms": "另行協調（範例）",
    "multi_birth_count": 1, "stair_floor_fee_mode": "無（範例）", "parking_space_provided": "有（範例）", "other_babies_present": "無（範例）",
}


def _sections(number):
    from subsystems.orders.order_information import build_case_information, build_weekly_information
    if number == 3:
        projection = build_weekly_information(CASE.case_no, CASE.start_date, {"rows": ({key: VALUES[key] for key in WEEKLY},),
            "date_basis": "confirmed", "warnings": ()})
    else:
        projection = build_case_information(CASE.case_no, number, ORDER_FACTS, {})
    return tuple((section.title, section.rows) for section in projection.line_sections)


class PublicPreviewReader:
    def case(self, _): return CASE
    def staff(self, _): return STAFF
    def leave(self, *_): return LEAVE
    def service_date(self, *_): return VALUES["service_date"]
    def payment_values(self, _): return {key: value for key, value in VALUES.items() if "payment" in key}

    def card(self, case_no, staff_id, kind):
        from subsystems.scheduling.matching_line_cards import candidate_contact_information_card, customer_confirmation_card

        if kind == "card-customer-confirmation":
            from subsystems.orders.order_information import build_order_information_message
            def information(number):
                text, _ = build_order_information_message(number, ORDER_FACTS, {}, "公版範例；實際內容由正式方案帶入。")
                return ({"text": text},)
            payload = customer_confirmation_card(CASE.case_no, (asdict(STAFF),), information(1), information(2),
                ({key: VALUES[key] for key in WEEKLY},), {STAFF.id: "https://preview.invalid/resume"}, "preview-only", "")
        else:
            number = int(kind.rsplit("-", 1)[1])
            payload = candidate_contact_information_card(CASE.case_no, number, _sections(number),
                "preview-only", None if number == 3 else "https://preview.invalid/candidate")
        return PreviewCardSource(payload)


@contextmanager
def public_preview_reader():
    yield PublicPreviewReader()


def sample_bindings(descriptor, template, content, rendered_text):
    """List the actual template substitutions and fields used by the public card example."""
    values = dict(VALUES)
    keys = []
    if template:
        text = content if content is not None else template["content"]
        keys.extend(dict.fromkeys(re.findall(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}", text if isinstance(text, str) else json.dumps(text))))
    key = descriptor.id
    if descriptor.template_id == "LU96-M1-LEAVE-EXTENSION-CARD-V1":
        keys.extend(("case_no", "leave_start_date", "leave_end_date", "description"))
        values["description"] = rendered_text
    elif key in {"card-customer-profiles", "card-customer-confirmation"}:
        keys.append("case_no")
        profile_labels = {"name": "月嫂姓名", "city": "月嫂居住地", "care_babies": "照護寶寶數", "has_massage_cert": "嬰幼兒按摩證書",
                          "service_regions": "服務區域", "special_skills": "技能與偏好"}
        for field, label in profile_labels.items():
            name = f"profiles[0].{field}"
            value = asdict(STAFF)[field]
            values[name] = "、".join(value) if isinstance(value, tuple) else ("有" if value is True else value)
            keys.append(name)
        if descriptor.template_id:
            values["description"] = rendered_text
            keys.append("description")
        if key == "card-customer-confirmation":
            keys.extend((*WEEKLY, "resume"))
            values["resume"] = "範例履歷 PDF（僅顯示按鈕，不提供檔案或下載連結）"
    elif key in {"card-caregiver-information", "card-caregiver-information-2"}:
        keys.extend(INFO_1 if key == "card-caregiver-information" else ("case_no", "start_date", "end_date", "city", "service_time", "baby_info", "residence_type"))
    elif key.startswith("card-candidate-information-"):
        keys.append("case_no")
    elif descriptor.allows_draft:
        keys.extend(("case_no", "content"))
        values["content"] = content or ""
    bindings = []
    for field in dict.fromkeys(keys):
        label = profile_labels[field.rsplit(".", 1)[1]] if field.startswith("profiles[0].") else ("月嫂資料清單" if field == "profiles" else LABELS.get(field, field))
        if field in values:
            bindings.append(PreviewOption(f"{label}（{field}）", str(values[field])))
    if key.startswith("card-candidate-information-"):
        for section, rows in _sections(int(key[-1])):
            bindings.extend(PreviewOption(f"{section}／{label}", value) for label, value in rows)
    elif key == "card-customer-confirmation":
        from subsystems.orders.order_information import _project_fields, _candidate_field_value, OrderInformationTemplate
        for number, template_id in ((1, OrderInformationTemplate.INFO_01), (2, OrderInformationTemplate.INFO_02)):
            fields, _, _ = _project_fields(template_id, ORDER_FACTS, {})
            bindings.extend(PreviewOption(f"訂單資訊{number}／{field.label}（{field.field_id}）", _candidate_field_value(field)) for field in fields)
    return tuple(bindings)


def alert_sample_values():
    category = "other"
    summary = "公版去敏事件摘要（不含真實個資）"
    entry = "［工會客服系統入口；仍須驗證管理員身分］"
    return category, summary, entry, (
        PreviewOption("客服分類（category）", category), PreviewOption("去敏摘要（safe_summary）", summary),
        PreviewOption("處理入口（management_entry）", entry),
    )


def current_message_sample(key):
    """Explicit current flow examples, rendered by the same pure helpers as delivery."""
    fields = []
    def field(label, path, value):
        fields.append(PreviewOption(f"{label}（{path}）", str(value)))
        return value
    def case(): return field("案件編號", "case_no", CASE.case_no)
    def text(value): return {"type": "text", "text": value}
    if key in {"contract-signing-client", "contract-signing-staff"}:
        from subsystems.contract_signing.line_delivery import external_platform_staff_reminder_text
        field("收件人", "recipient", "客戶私人聊天室" if key.endswith("client") else "月嫂私人聊天室")
        payload = text(external_platform_staff_reminder_text(case()))
    elif key.startswith("payment-overdue-"):
        from datetime import date
        from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
        from subsystems.line.payment_overdue_reminders import reminder_text, STAGE_LABELS
        stage = key.removeprefix("payment-overdue-")
        field("期別", "payment_stage", STAGE_LABELS[stage])
        field("收件人", "recipient", "客戶私人聊天室" if stage == "deposit" else "案件群組")
        amount = field("剩餘待繳金額", "remaining_amount_ntd", {"deposit": 6000, "first": 12000, "second": 8000}[stage])
        payload = text(reminder_text(OverdueClientPayment(case(), stage, "preview-only", 1, 1, date(2026,11,1), amount)))
    elif key in {"deposit-reminder", "deposit-settled"}:
        from subsystems.line.deposit_notifications import deposit_notification_payload, REMINDER, SETTLED
        amount = field("訂金金額（新臺幣）", "amount_ntd", 6000)
        due = field("繳費期限", "due_date", "2026-11-01") if key == "deposit-reminder" else None
        entry = field("繳費頁面", "payment_entry", "https://preview.invalid/deposit")
        payload = deposit_notification_payload(case(), amount, due, SETTLED if key == "deposit-settled" else REMINDER, entry)
    elif key == "service-day-log-reminder":
        from subsystems.line.service_day_log_reminders import reminder_text
        payload = text(reminder_text(field("月嫂姓名", "staff_name", STAFF.name)))
    elif key == "deposit-assistance":
        from subsystems.line.deposit_notifications import ASSISTANCE_ACK
        payload = text(ASSISTANCE_ACK)
    elif key == "group-bound":
        from subsystems.line.order_group_application import group_binding_acknowledgement
        payload = text(group_binding_acknowledgement(case()))
    elif key == "service-start-inquiry":
        from subsystems.line.service_start_messages import substitute_inquiry
        dates = ['2026-11-02', '2026-11-04', '2026-11-06']
        field("服務日期", "service_dates", '、'.join(dates))
        payload=substitute_inquiry(case(),dates[0],dates[-1],'preview-only-no-operation',service_dates=dates)
    elif key == "service-start-result":
        from subsystems.line.service_start_messages import service_date_record
        dates = ['2026-11-02', '2026-11-04', '2026-11-06']
        name = field("月嫂姓名", "assignments[0].staff_name", STAFF.name)
        field("服務日期", "assignments[0].service_dates", '、'.join(dates))
        payload=service_date_record(case(),[{'staff_name':name,'service_dates':dates}])
    elif key in {"service-start-normal-received", "service-start-help-received"}:
        from subsystems.line.service_start_day import start_day_response_text
        payload = text(start_day_response_text('normal' if key == "service-start-normal-received" else 'help'))
    elif key == "group-invitations-queued":
        from subsystems.line.order_group_application import group_invitation_acknowledgement
        count = field("邀請對象人數", "recipient_count", 2)
        payload = text(group_invitation_acknowledgement(case(), count))
    elif key in {"group-invitation-customer", "group-invitation-staff"}:
        from subsystems.line.order_group_application import group_invitation_payload
        label = field("對象稱呼", "recipient_label", "媽媽" if key.endswith("customer") else "月嫂")
        url = field("公版邀請網址", "invitation_url", "https://preview.invalid/group")
        payload = group_invitation_payload(case(), label, url)
    elif key in {"group-error-invitation-url", "group-format-invite"}:
        from subsystems.line.order_group_application import _INVITATION_URL_REQUIRED, _INVITE_COMMAND_FORMAT
        if key == "group-format-invite":
            field("輸入的指令", "command", "發送邀請 DEMO-CASE-001")
        payload = text(_INVITATION_URL_REQUIRED if key == "group-error-invitation-url" else _INVITE_COMMAND_FORMAT)
    elif key.startswith("group-error-"):
        from subsystems.line.order_group_application import _safe_error_message
        codes = {"admin": "linked_admin_required", "order": "order_not_found", "unbound": "group_not_bound",
                 "identity": "order_line_audience_not_ready", "cancelled": "cancelled_order_cannot_bind_line_group",
                 "unpaid": "settled_deposit_required_for_line_group", "occupied": "line_group_already_bound_to_another_order"}
        payload = text(_safe_error_message(RuntimeError(codes[key.removeprefix("group-error-")])))
    elif key.startswith("group-format-"):
        from subsystems.line.order_group_application import _parse_binding, LineOrderGroupCommandRejected
        commands = {"empty": "綁定訂單", "case": "綁定訂單 https://line.me/R/ti/g/example",
                    "url": "綁定訂單 DEMO-CASE-001", "spacing": "綁定訂單DEMO-CASE-001 https://line.me/R/ti/g/example",
                    "split": "綁定訂單 DEMO-CASE-001 https://line.me/R/ti/g/ example",
                    "invalid-case": "綁定訂單 ??? https://line.me/R/ti/g/example",
                    "invalid-url": "綁定訂單 DEMO-CASE-001 https://example.invalid/group"}
        command = field("輸入的指令", "command", commands[key.removeprefix("group-format-")])
        try:
            _parse_binding(command)
        except LineOrderGroupCommandRejected as error:
            payload = text(str(error))
        else:
            raise ValueError("public group error example must be invalid")
    elif key == "candidate-willing-received":
        from subsystems.line.message_copy import CANDIDATE_WILLING_RECEIVED
        payload = text(CANDIDATE_WILLING_RECEIVED)
    elif key.startswith("matching-"):
        from domains.scheduling.matching_communication import CustomerMatchingDecision
        from subsystems.scheduling.matching_notification_application import matching_response_text
        willing = "willing" if key == "matching-willing-received" else None
        decision = {"matching-customer-accepted": CustomerMatchingDecision.ACCEPTED,
                    "matching-customer-assistance": CustomerMatchingDecision.CONTACT_REQUESTED}.get(key)
        if willing is not None: field("月嫂意願", "caregiver_willingness", willing)
        if decision is not None: field("客戶選擇", "customer_decision", decision.value)
        payload = text(matching_response_text(willing, decision))
    elif key in {"leave-agreed", "leave-substitution"}:
        from subsystems.line.staff_leave_customer_coordination import leave_decision_text
        decision = field("客戶選擇", "decision", "agree_defer" if key == "leave-agreed" else "disagree_defer")
        case_no = case() if key == "leave-substitution" else CASE.case_no
        ticket = field("客服案件編號", "ticket_id", 123) if key == "leave-substitution" else None
        payload = text(leave_decision_text(decision, case_no, ticket))
    elif key in {"leave-stale", "leave-locked", "leave-unavailable"}:
        from subsystems.line.staff_leave_customer_coordination import leave_decision_rejection_text
        code = {"leave-stale": "leave_request_stale", "leave-locked": "leave_customer_decision_idempotency_conflict",
                "leave-unavailable": "unavailable"}[key]
        payload = text(leave_decision_rejection_text(code))
    elif key == "service-progress":
        from subsystems.line.service_help_application import _progress_payload
        context = {"case_no": case(), "status": field("案件狀態", "status", "訂單成立"),
                   "start_date": field("服務開始日", "start_date", CASE.start_date),
                   "end_date": field("服務結束日", "end_date", CASE.end_date)}
        payload = _progress_payload(context)
    elif key == "service-progress-unbound":
        from subsystems.line.service_help_application import _unbound_progress_reply
        payload = text(_unbound_progress_reply(field("身分綁定入口", "identity_url", VALUES["bind_url"])))
    elif key in {"service-registration", "service-registration-unavailable"}:
        from subsystems.line.service_help_application import _registration_reply
        entry = field("服務登記入口", "registration_url", VALUES["url"]) if key == "service-registration" else None
        payload = text(_registration_reply(entry))
    elif key in {"identity-staff-link", "identity-admin-link"}:
        from domains.line.identity_flow import LineIdentityFlowPurpose
        from subsystems.line.webhook_identity_handlers import _identity_link_message
        purpose = LineIdentityFlowPurpose.STAFF_VERIFICATION if key == "identity-staff-link" else LineIdentityFlowPurpose.ADMIN_BINDING
        entry = field("身分入口", "identity_url", VALUES["bind_url"])
        payload = text(_identity_link_message(purpose, entry))
    elif key == "runtime-system-health":
        from datetime import datetime, timezone
        from subsystems.line.runtime_alert_application import _message
        stamp = datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)
        values = {"check_name": field("檢查元件", "check_name", "LINE Worker（公版）"),
                  "resulting_status": field("健康狀態", "resulting_status", "critical"),
                  "message": field("異常說明", "message", "公版心跳逾期情境"), "occurred_at_utc": stamp}
        field("發生時間（UTC）", "occurred_at_utc", stamp.isoformat())
        payload = text(_message(values))
    else:
        raise ValueError("unknown current flow sample")
    return payload, tuple(fields)
