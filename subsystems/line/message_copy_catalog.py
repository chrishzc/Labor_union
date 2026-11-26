"""
File: message_copy_catalog.py
Description: 定義 LINE 可編修文案預設目錄與純樣板渲染，不讀取收件對象或執行外送。
"""
from copy import deepcopy
import json

from subsystems.line.message_copy import (
    IDENTITY_PENDING,
    IDENTITY_SUCCESS_DEFAULTS, IDENTITY_SUCCESS_TEMPLATES, copy_fields, copy_template_id,
    message_definition, apply_copy_payload,
)


INACTIVE_CANDIDATE_COPY_TEMPLATE_IDS = frozenset(copy_template_id(key) for key in (
    "card-union-question", "card-union-answer", "candidate-willing-received",
))
RETIRED_SIGNING_REMINDER_TEMPLATE_IDS = frozenset(
    copy_template_id(key) for key in ("contract-signing-client", "contract-signing-staff")
)
RETIRED_PAYMENT_RECEIPT_TEMPLATE_IDS = frozenset({
    copy_template_id("deposit-settled"),
    copy_template_id("payment-first-settled"),
    "LINE-SECOND-PAYMENT-SETTLED-TEXT-V1",
})
RETIRED_START_DAY_REPORT_TEMPLATE_IDS = frozenset({
    'LINE-ORDER-SERVICE-START-DAY-CARD-V1',
    copy_template_id('service-start-normal-received'),
    copy_template_id('service-start-help-received'),
})
RETIRED_SERVICE_COMPLETION_PUSH_TEMPLATE_ID = "LINE-SERVICE-COMPLETION-TEXT-V1"


_RETIRED_CUSTOMER_SERVICE_COPY_KEYS = frozenset({
    "service-contact",
    "service-resolved",
    "service-profile-update",
    "service-order-update",
    "order-update-menu",
    "complaint-handoff-received",
    "customer-service-ticket-reply",
    "helper-staff-assistance-ack",
    "helper-staff-assistance-closed",
    "deposit-assistance",
    "payment-assistance",
    "matching-customer-assistance",
})
RETIRED_CUSTOMER_SERVICE_TEMPLATE_IDS = frozenset(
    copy_template_id(key) for key in _RETIRED_CUSTOMER_SERVICE_COPY_KEYS
)


def _text_defaults():
    from domains.line.identity_flow import LineIdentityFlowPurpose
    from domains.scheduling.matching_communication import CustomerMatchingDecision
    from subsystems.line import service_help_application as help
    from subsystems.line.service_day_log_reminders import reminder_text as log_reminder
    from subsystems.line.service_start_day import GREETING_COPY, PAYMENT_COPY
    from subsystems.line.webhook_identity_handlers import _identity_link_message
    from subsystems.scheduling.matching_notification_application import matching_response_text
    from subsystems.line.cancellation_notifications import DEFAULT_COPY as CANCELLATION_NOTICE_COPY
    from subsystems.line.staff_web_expiry_reminders import COPY_KEY as STAFF_WEB_EXPIRY, DEFAULT_COPY as STAFF_WEB_EXPIRY_COPY
    from subsystems.line.service_start_messages import HELPER_TEXT_DEFAULTS
    from subsystems.case_import.provisional_registration_application import registration_confirmation_text
    result = {
        **{key: value for key, value in HELPER_TEXT_DEFAULTS.items() if key not in _RETIRED_CUSTOMER_SERVICE_COPY_KEYS},
        "registration-approved-citizen": registration_confirmation_text("{name}", approved=True),
        "registration-approved-non-citizen": registration_confirmation_text(
            "{name}", approved=True, case_no="{case_no}"
        ),
        "identity-pending": IDENTITY_PENDING,
        "payment-reminder-ack": "已收到您的回覆，感謝您。工會將於核對後通知，請耐心等候不需重複繳款。",
        "payment-first-reminder": PAYMENT_COPY,
        "payment-first-greeting": GREETING_COPY,
        "payment-second-reminder": "案件 {case_no} 第二期款尚待確認入帳 {amount_ntd} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。",
        "service-day-log-reminder": log_reminder("{staff_name}"),
        STAFF_WEB_EXPIRY: STAFF_WEB_EXPIRY_COPY,
        "service-start-result": "服務日期安排\n案件：{case_no}\n{assignments}",
        "service-progress": "最新案件：{case_no}\n目前狀態：{status}\n服務期間：{start_date} 至 {end_date}",
        "service-progress-unbound": help._unbound_progress_reply("{identity_url}"),
        "service-registration": help._registration_reply("{registration_url}"),
        "service-registration-unavailable": help._registration_reply(None),
        "identity-customer-link": _identity_link_message(LineIdentityFlowPurpose.CUSTOMER_BINDING, "{identity_url}"),
        "identity-staff-link": _identity_link_message(LineIdentityFlowPurpose.STAFF_VERIFICATION, "{identity_url}"),
        "identity-admin-link": _identity_link_message(LineIdentityFlowPurpose.ADMIN_BINDING, "{identity_url}"),
        **{f"cancellation-notice-{kind}": copy for kind, copy in CANCELLATION_NOTICE_COPY.items()},
    }
    for stage in ("deposit", "first", "second"):
        result["payment-overdue-" + stage] = "本案{payment_stage}尚有 NT$ {remaining_amount} 未確認入帳，請協助確認繳款，謝謝。"
    for key, willing, decision in (
        ("matching-willing-received", "willing", None),
        ("matching-customer-accepted", None, CustomerMatchingDecision.ACCEPTED),
        ("matching-customer-response", None, None),
    ):
        result[key] = matching_response_text(willing, decision)
    return result


def _card_defaults():
    from subsystems.line.service_help_application import _service_menu_payload
    from subsystems.line.order_group_application import group_invitation_payload
    from subsystems.line.service_start_messages import (
        confirm_start_date_card,
        group_guidelines_card,
        group_helper_menu_card,
        mutual_postponement_card,
        substitute_inquiry,
    )
    result = {"service-menu": _service_menu_payload(),
              "helper-menu-card": group_helper_menu_card("{case_no}", "{staff_name}"),
              "helper-confirm-start-card": confirm_start_date_card("{case_no}", "{staff_name}", "{start_date}", "{end_date}"),
              "helper-postponement-card": mutual_postponement_card("{case_no}", "{staff_name}", "{leave_start_date}", "{leave_end_date}"),
              "helper-guidelines-card": group_guidelines_card(),
              "service-start-inquiry": substitute_inquiry("{case_no}", "", "", "not-a-token", service_dates=["{service_dates}"])}
    result["service-start-inquiry"]["contents"]["body"]["contents"][1]["text"] = "案件：{case_no}\n{service_period}"
    for role, label in (("customer", "媽媽"), ("staff", "月嫂")):
        result["group-invitation-" + role] = group_invitation_payload("{case_no}", label, "https://invalid.local")
    # Amounts stay authoritative variables, never public sample values.
    from subsystems.line.deposit_notifications import deposit_notification_payload, REMINDER
    from subsystems.line.payment_reminder_notifications import payment_reminder_card_payload
    class Amount:
        def __init__(self, var="amount_ntd"):
            self.var = var
        def __str__(self):
            return "{" + self.var + "}"
        def __format__(self, spec):
            return "{" + self.var + "}"
    result["deposit-reminder"] = deposit_notification_payload("{case_no}", Amount("amount_ntd"), "{due_date}", REMINDER)
    result["payment-second-reminder"] = payment_reminder_card_payload("second", "{case_no}", Amount("amount_ntd"), "{due_date}", "reminder")
    for stage in ("deposit", "first", "second"):
        result["payment-overdue-" + stage] = payment_reminder_card_payload(stage, "{case_no}", Amount("remaining_amount"), "{due_date}", "overdue")
    from domains.scheduling.matching_communication import MatchingNotificationKind
    from subsystems.scheduling.matching_line_cards import (
        caregiver_information_card, candidate_contact_information_card, customer_profiles_card,
        customer_confirmation_card,
    )
    facts = {key: "{business_value}" for key in ("case_no", "start_date", "end_date", "city", "service_type", "service_time", "multi_birth_count", "residence_type")}
    for number in (1, 2):
        kind = MatchingNotificationKind.CAREGIVER_INFO_1 if number == 1 else MatchingNotificationKind.CAREGIVER_INFO_2
        result["card-caregiver-information" + ("-2" if number == 2 else "")] = json.loads(caregiver_information_card(kind, facts, "not-a-token"))
    for number in (1, 2, 3):
        result["card-candidate-information-" + str(number)] = json.loads(candidate_contact_information_card(
            "{case_no}", number, [("{business_value}", [("{business_value}", "{business_value}")])], "not-a-token"))
    result["card-candidate-information-package"] = result["card-candidate-information-1"]
    profile = {"id": 1, "name": "{business_value}", "city": "{business_value}", "care_babies": 1,
               "service_regions": ["{business_value}"], "special_skills": ["{business_value}"], "has_massage_cert": False}
    result["card-customer-profiles"] = json.loads(customer_profiles_card("{case_no}", [profile], "not-a-token", "{business_value}"))
    result["card-customer-confirmation"] = json.loads(customer_confirmation_card("{case_no}", [profile],
        [{"text": "{business_value}"}], [{"text": "{business_value}"}], [], "not-a-token", "{business_value}"))
    return result


def default_copy_templates():
    """Virtual genesis entries; reads never persist or replace existing settings."""
    from subsystems.line.deposit_notifications import ASSISTANCE_ACK
    from subsystems.line.service_start_messages import GROUP_ASSISTANCE_DIRECTIONS
    from subsystems.scheduling.matching_line_cards import MATCHING_ASSISTANCE_DIRECTIONS

    fixed_guidance = {ASSISTANCE_ACK, GROUP_ASSISTANCE_DIRECTIONS, MATCHING_ASSISTANCE_DIRECTIONS}
    result = {}
    for key, content in _text_defaults().items():
        result[key] = _template(copy_template_id(key), key, content)
    for key, payload in _card_defaults().items():
        if key == 'card-candidate-information-3':
            continue  # The weekly picture contains owner data, not editable copy.
        fields = copy_fields(payload, fixed_text=fixed_guidance)
        if key == "service-menu":
            # Do not reapply old AI promotions from persisted service-menu copy.
            fields = [field for field in fields if field["id"] not in {
                "contents/footer/contents/0/text",
                "contents/header/contents/2/text",
            }]
        if key.startswith("card-"):
            # Owner-projected rows, profile values and authored questions are
            # facts, not reusable announcement copy.
            fields = [f for f in fields if "{business_value}" not in f["content"]
                      and not (key in {"card-customer-profiles", "card-customer-confirmation"} and f["id"].endswith("/contents/1/text"))
                      and f["content"] not in {"目前無法產生每周服務中說明。", "目前無法產生資料。"}]
            if key == 'card-customer-confirmation':
                fields = [field for field in fields if field['id'].startswith('contents/contents/4/')]
            elif key.startswith('card-candidate-information-'):
                fields = [field for field in fields if field['id'].startswith('contents/footer/')
                    or field['id'] == 'contents/body/contents/0/text'
                    or field['content'] == '請確認檔期與條件後回覆是否願意承接。']
                if key == 'card-candidate-information-package':
                    fields = [field for field in fields if not field['id'].startswith('contents/footer/')]
            if key in {"card-customer-profiles", "card-customer-confirmation"}:
                for field in fields:
                    parts = field["id"].split("/")
                    if parts[:2] == ["contents", "contents"]:
                        parts[2] = "*"
                        field["path"] = "/".join(parts)
                        field["match"] = field["content"]
                        if 'append_to' in field:
                            target = field['append_to'].split('/')
                            target[2] = '*'
                            field['append_to'] = '/'.join(target)
            elif key.startswith("card-candidate-information-"):
                for field in fields:
                    parts = field["id"].split("/")
                    if parts[:3] == ["contents", "body", "contents"]:
                        parts[3] = "*"
                        field["path"] = "/".join(parts)
                        field["match"] = field["content"]
        elif key == "helper-postponement-card":
            field_labels = {
                "contents/header/contents/0/contents/0/contents/0/text": ("狀態標籤", "label"),
                "contents/header/contents/1/text": ("卡片主標題", "title"),
                "contents/header/contents/2/text": ("副標題說明", "label"),
            }
            for field in fields:
                if field["id"] in field_labels:
                    field["label"], field["kind"] = field_labels[field["id"]]
        elif key == "helper-guidelines-card":
            field_labels = {
                "altText": ("訊息摘要", "summary"),
                "contents/header/contents/0/contents/0/contents/0/text": ("標籤徽章", "label"),
                "contents/header/contents/1/text": ("卡片主標題", "title"),
                "contents/header/contents/2/text": ("副標題說明", "body"),
                "contents/body/contents/0/contents/0/text": ("重要提醒區塊標題", "label"),
                "contents/body/contents/0/contents/1/text": ("提醒重點 1", "body"),
                "contents/body/contents/0/contents/2/text": ("提醒重點 2", "body"),
                "contents/body/contents/0/contents/3/text": ("提醒重點 3", "body"),
                "contents/body/contents/1/text": ("常見問題區塊標題", "label"),
                "contents/body/contents/2/contents/0/contents/0/text": ("問題 1 題目", "body"),
                "contents/body/contents/2/contents/0/action/label": ("問題 1 按鈕名稱", "button"),
                "contents/body/contents/2/contents/1/contents/0/text": ("問題 2 題目", "body"),
                "contents/body/contents/2/contents/1/action/label": ("問題 2 按鈕名稱", "button"),
                "contents/body/contents/2/contents/2/contents/0/text": ("問題 3 題目", "body"),
                "contents/body/contents/2/contents/2/action/label": ("問題 3 按鈕名稱", "button"),
            }
            custom_fields = []
            for f in fields:
                if f["id"] in field_labels:
                    lbl, knd = field_labels[f["id"]]
                    f["label"] = lbl
                    f["kind"] = knd
                    custom_fields.append(f)
            fields = custom_fields
        content = json.dumps({field["id"]: field["content"] for field in fields}, ensure_ascii=False)
        template = _template(copy_template_id(key), key, content)
        if key.startswith('card-') and 'case_no' not in {v['name'] for v in template['variables']}:
            template['variables'].append({'name': 'case_no', 'required': False})
        template["copy_fields"] = fields
        result[key] = template
    for role, template_id in IDENTITY_SUCCESS_TEMPLATES.items():
        key = "identity-bound-" + role
        result[key] = _template(template_id, {"customer": "客戶綁定成功", "staff": "月嫂綁定成功", "admin": "工會人員綁定成功"}[role], IDENTITY_SUCCESS_DEFAULTS[role])
    return result


def _template(identifier, name, content):
    import re
    return {"id": identifier, "name": name, "message_type": "text", "enabled": True,
            "content": content, "variables": [{"name": v, "required": True} for v in sorted(set(re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", content)))]}


def effective_copy_definition(definition):
    from subsystems.line.service_start_day import PAYMENT_COPY_VARIABLES

    result = deepcopy(definition)
    defaults_by_key = default_copy_templates()
    first_reminder = defaults_by_key['payment-first-reminder']
    specs = {t["id"]: t for t in defaults_by_key.values() if t.get("copy_fields")}
    for template in result.get("templates", []):
        if template['id'] == first_reminder['id']:
            content = template['content']
            try:
                saved_fields = json.loads(content)
            except json.JSONDecodeError:
                saved_fields = None
            if isinstance(saved_fields, dict) or not all(variable in content for variable in PAYMENT_COPY_VARIABLES):
                # Card copy and text missing mandatory payment fields cannot be sent as an opening notice.
                template['content'] = first_reminder['content']
            template.pop('copy_fields', None)
            template['variables'] = deepcopy(first_reminder['variables'])
        if template["id"] in specs:
            key = template['id'].removeprefix('LINE-COPY-')
            if key in {
                "service-menu", "helper-menu-card", "deposit-reminder", "payment-second-reminder",
                "payment-overdue-deposit", "payment-overdue-first", "payment-overdue-second",
                "card-customer-profiles", "card-customer-confirmation",
            }:
                current = json.loads(template["content"])
                defaults = json.loads(specs[template["id"]]["content"])
                if isinstance(current, dict):
                    template["content"] = json.dumps(
                        {**defaults, **{field: value for field, value in current.items() if field in defaults}},
                        ensure_ascii=False,
                    )
            if key in {'card-candidate-information-1', 'card-candidate-information-2', 'card-candidate-information-package'}:
                # Preserve only text fields still editable in the current card.
                current = json.loads(template['content'])
                legacy_ids = {field['id'] for field in copy_fields(_card_defaults()[key])}
                if isinstance(current, dict) and set(current) <= legacy_ids:
                    selected = json.loads(specs[template['id']]['content'])
                    selected.update({field: value for field, value in current.items() if field in selected})
                    template['content'] = json.dumps(selected, ensure_ascii=False)
            current = json.loads(template['content'])
            defaults = json.loads(specs[template['id']]['content'])
            if isinstance(current, dict) and set(current) <= set(defaults):
                template['content'] = json.dumps({**defaults, **current}, ensure_ascii=False)
            template["copy_fields"] = deepcopy(specs[template["id"]]["copy_fields"])
            template['variables'] = deepcopy(specs[template['id']]['variables'])
    existing = {t["id"] for t in result.get("templates", [])}
    for template in defaults_by_key.values():
        if template["id"] not in existing:
            seeded = deepcopy(template)
            legacy_id = {"identity_bound_customer": "bind_success_new_order", "identity_bound_staff": "staff_switch_success"}.get(template["id"])
            legacy = next((t for t in result.get("templates", []) if t["id"] == legacy_id), None)
            if legacy and legacy.get("content") not in {"綁定成功，專屬選單將稍後更新。", "月嫂身分已完成綁定，專屬選單將稍後更新。"}:
                seeded["content"] = legacy["content"]
                seeded["variables"] = deepcopy(legacy.get("variables", []))
            result.setdefault("templates", []).append(seeded)
            existing.add(template["id"])
    return result


def configured_payload(unit, key, payload, variables=None):
    return render_copy_payload(message_definition(unit), key, payload, variables)


def render_copy_payload(definition, key, payload, variables=None, content=None):
    from subsystems.line.message_configuration import render_message_template
    defaults = default_copy_templates().get(key)
    if defaults is None:
        return payload
    definition = effective_copy_definition(definition)
    template = next((t for t in definition.get("templates", []) if t["id"] == defaults["id"]), None)
    if template is None and content is None:
        return payload
    template = template or defaults
    text = content if content is not None else template["content"]
    if "copy_fields" in defaults:
        return apply_copy_payload(payload, text, defaults["copy_fields"], variables)
    candidate = {**defaults, **template, "content": text}
    used = {v["name"] for v in candidate.get("variables", [])}
    rendered = render_message_template({"templates": [candidate]}, candidate["id"], {k: v for k, v in (variables or {}).items() if k in used})
    result = deepcopy(payload)
    result["text"] = json.loads(rendered.payload_json)["text"]
    if key in {'payment-first-greeting', 'payment-first-reminder'}:
        from subsystems.line.service_start_day import render_greeting_text
        result['text'] = render_greeting_text(key, result['text'], variables or {})
    return result
