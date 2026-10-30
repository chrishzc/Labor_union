"""Editable LINE display copy; defaults come from the existing pure composers.

This catalog contains no recipient lookup, operation token or provider action.
"""
from copy import deepcopy
import json

from subsystems.line.message_copy import (
    CONTACT_RECEIVED, CONTACT_RESOLVED, IDENTITY_PENDING, CANDIDATE_WILLING_RECEIVED,
    IDENTITY_SUCCESS_DEFAULTS, IDENTITY_SUCCESS_TEMPLATES, copy_fields, copy_template_id,
    message_definition, apply_copy_payload,
)


def _text_defaults():
    from domains.customer_service.ticket import CustomerServiceCategory
    from domains.line.identity_flow import LineIdentityFlowPurpose
    from domains.scheduling.matching_communication import CustomerMatchingDecision
    from subsystems.line import service_help_application as help
    from subsystems.line.deposit_notifications import ASSISTANCE_ACK
    from subsystems.line.service_day_log_reminders import reminder_text as log_reminder
    from subsystems.line.service_start_day import start_day_response_text
    from subsystems.line.webhook_identity_handlers import _identity_link_message
    from subsystems.scheduling.matching_notification_application import matching_response_text
    from subsystems.contract_signing.line_delivery import external_platform_staff_reminder_text
    result = {
        "service-contact": CONTACT_RECEIVED, "service-resolved": CONTACT_RESOLVED,
        "identity-pending": IDENTITY_PENDING,
        "service-profile-update": help._TICKET_ACKNOWLEDGEMENTS[CustomerServiceCategory.PROFILE_UPDATE],
        "service-order-update": help._ORDER_UPDATE_ACKNOWLEDGEMENT,
        "deposit-assistance": ASSISTANCE_ACK,
        "payment-first-reminder": "案件 {case_no} 今天開始服務，祝服務順利！第一期款尚待確認入帳：{amount_ntd} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。",
        "payment-first-greeting": "案件 {case_no} 今天開始服務，祝服務順利！",
        "payment-second-reminder": "案件 {case_no} 第二期款尚待確認入帳 {amount_ntd} 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。",
        "service-day-log-reminder": log_reminder("{staff_name}"),
        "candidate-willing-received": CANDIDATE_WILLING_RECEIVED,
        "service-start-normal-received": start_day_response_text("normal"),
        "service-start-help-received": start_day_response_text("help"),
        "service-start-result": "服務日期安排\n案件：{case_no}\n{assignments}",
        "service-progress": "最新案件：{case_no}\n目前狀態：{status}\n服務期間：{start_date} 至 {end_date}",
        "service-progress-unbound": help._unbound_progress_reply("{identity_url}"),
        "service-registration": help._registration_reply("{registration_url}"),
        "service-registration-unavailable": help._registration_reply(None),
        "identity-staff-link": _identity_link_message(LineIdentityFlowPurpose.STAFF_VERIFICATION, "{identity_url}"),
        "identity-admin-link": _identity_link_message(LineIdentityFlowPurpose.ADMIN_BINDING, "{identity_url}"),
    }
    for role in ("client", "staff"):
        result["contract-signing-" + role] = external_platform_staff_reminder_text("{case_no}")
    for stage in ("deposit", "first", "second"):
        result["payment-overdue-" + stage] = "本案{payment_stage}尚有 NT$ {remaining_amount} 未確認入帳，請協助確認繳款，謝謝。"
    for key, willing, decision in (
        ("matching-willing-received", "willing", None),
        ("matching-customer-accepted", None, CustomerMatchingDecision.ACCEPTED),
        ("matching-customer-assistance", None, CustomerMatchingDecision.CONTACT_REQUESTED),
        ("matching-customer-response", None, None),
    ):
        result[key] = matching_response_text(willing, decision)
    return result


def _card_defaults():
    from subsystems.line.service_help_application import _service_menu_payload, _order_update_menu_payload
    from subsystems.line.order_group_application import group_invitation_payload
    from subsystems.line.service_start_messages import substitute_inquiry
    result = {"service-menu": _service_menu_payload(),
              "order-update-menu": _order_update_menu_payload(),
              "service-start-inquiry": substitute_inquiry("{case_no}", "", "", "not-a-token", service_dates=["{service_dates}"])}
    result["service-start-inquiry"]["contents"]["body"]["contents"][1]["text"] = "案件：{case_no}\n{service_period}"
    for role, label in (("customer", "媽媽"), ("staff", "月嫂")):
        result["group-invitation-" + role] = group_invitation_payload("{case_no}", label, "https://invalid.local")
    # Amounts stay authoritative variables, never public sample values.
    for key, paid in (("deposit-reminder", False), ("deposit-settled", True)):
        from subsystems.line.deposit_notifications import deposit_notification_payload, REMINDER, SETTLED
        class Amount:
            def __format__(self, spec):
                return "{amount_ntd}"
        result[key] = deposit_notification_payload("{case_no}", Amount(), "{due_date}", SETTLED if paid else REMINDER, "https://invalid.local")
    from domains.scheduling.matching_communication import MatchingNotificationKind
    from subsystems.scheduling.matching_line_cards import (
        caregiver_information_card, candidate_contact_information_card, customer_profiles_card,
        customer_confirmation_card, candidate_customer_question_card, candidate_caregiver_answer_card,
    )
    facts = {key: "{business_value}" for key in ("case_no", "start_date", "end_date", "city", "service_type", "service_time", "baby_info", "residence_type")}
    for number in (1, 2):
        kind = MatchingNotificationKind.CAREGIVER_INFO_1 if number == 1 else MatchingNotificationKind.CAREGIVER_INFO_2
        result["card-caregiver-information" + ("-2" if number == 2 else "")] = json.loads(caregiver_information_card(kind, facts, "not-a-token"))
    for number in (1, 2, 3):
        result["card-candidate-information-" + str(number)] = json.loads(candidate_contact_information_card(
            "{case_no}", number, [("{business_value}", [("{business_value}", "{business_value}")])], "not-a-token", "https://invalid.local"))
    profile = {"id": 1, "name": "{business_value}", "city": "{business_value}", "care_babies": 1,
               "service_regions": ["{business_value}"], "special_skills": ["{business_value}"], "has_massage_cert": False}
    result["card-customer-profiles"] = json.loads(customer_profiles_card("{case_no}", [profile], "not-a-token", "{business_value}"))
    result["card-customer-confirmation"] = json.loads(customer_confirmation_card("{case_no}", [profile],
        [{"text": "{business_value}"}], [{"text": "{business_value}"}], [], {1: "https://invalid.local"}, "not-a-token", "{business_value}"))
    result["card-union-question"] = json.loads(candidate_customer_question_card("{case_no}", "{business_value}", "https://invalid.local"))
    result["card-union-answer"] = json.loads(candidate_caregiver_answer_card("{case_no}", "{business_value}", "not-a-token", "https://invalid.local"))
    return result


def default_copy_templates():
    """Virtual genesis entries; reads never persist or replace existing settings."""
    result = {}
    for key, content in _text_defaults().items():
        result[key] = _template(copy_template_id(key), key, content)
    for key, payload in _card_defaults().items():
        if key == 'card-candidate-information-3':
            continue  # The weekly picture contains owner data, not editable copy.
        fields = copy_fields(payload)
        if key.startswith("card-"):
            # Owner-projected rows, profile values and authored questions are
            # facts, not reusable announcement copy.
            fields = [f for f in fields if "{business_value}" not in f["content"]
                      and not (key in {"card-customer-profiles", "card-customer-confirmation"} and f["id"].endswith("/contents/1/text"))
                      and f["content"] not in {"目前無法產生每周服務中說明。", "目前無法產生資料。"}]
            if key == 'card-customer-confirmation':
                fields = [field for field in fields if field['id'].startswith('contents/contents/4/')]
            elif key in {'card-candidate-information-1', 'card-candidate-information-2'}:
                fields = [field for field in fields if field['id'].startswith('contents/footer/')
                    or field['id'] == 'contents/body/contents/0/text'
                    or field['content'] == '請確認檔期與條件後回覆是否願意承接。']
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
    result = deepcopy(definition)
    specs = {t["id"]: t for t in default_copy_templates().values() if t.get("copy_fields")}
    for template in result.get("templates", []):
        if template["id"] in specs:
            key = template['id'].removeprefix('LINE-COPY-')
            if key == 'order-update-menu':
                current = json.loads(template['content'])
                defaults = json.loads(specs[template['id']]['content'])
                if isinstance(current, dict) and not set(current) <= set(defaults):
                    # Project the former five-button menu without rewriting its history.
                    template['content'] = specs[template['id']]['content']
            if key in {'card-customer-confirmation', 'card-candidate-information-1', 'card-candidate-information-2'}:
                # Preserve saved action wording while retiring image-body copy.
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
    for template in default_copy_templates().values():
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
    return result
