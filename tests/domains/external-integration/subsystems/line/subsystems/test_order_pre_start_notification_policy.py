"""
File: test_order_pre_start_notification_policy.py
Description: 驗證服務開始前 3 天提醒事件在 Policy 評估與 Template 渲染時完全符合契約規格。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from subsystems.line.message_configuration import render_message_template
from subsystems.line.notification_policy import evaluate_notification_rules
from subsystems.line.notification_source_adapters import from_order_pre_start_checkpoint


def test_order_pre_start_rule_evaluates_to_intent_created() -> None:
    rules_def = json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8"))

    event = from_order_pre_start_checkpoint(
        case_no="CASE-TEST-888",
        planned_start_date="2026-08-20",
        first_payment_amount=24000,
        already_settled=False,
        occurred_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )

    decisions = evaluate_notification_rules(event, rules_def)

    matching_decisions = [d for d in decisions if d.rule_id == "LU96-ORDER-PRE-START-REMINDER-V1"]
    assert len(matching_decisions) == 1
    assert matching_decisions[0].status == "intent_created"
    assert matching_decisions[0].reason_code == "rule_matched"


def test_order_pre_start_template_renders_properly() -> None:
    templates_def = json.loads(Path("config/message_templates.json").read_text(encoding="utf-8"))

    event = from_order_pre_start_checkpoint(
        case_no="CASE-TEST-888",
        planned_start_date="2026-08-20",
        first_payment_amount=24000,
        already_settled=False,
        occurred_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )

    rendered = render_message_template(
        templates_def,
        "LU96-ORDER-PRE-START-REMINDER-CARD-V1",
        {
            "case_no": event.facts["case_no"],
            "planned_start_date": event.facts["planned_start_date"],
            "first_payment_amount": event.facts["first_payment_amount"],
            "first_payment_status": event.facts["first_payment_status"],
        },
    )

    payload = json.loads(rendered.payload_json)
    assert payload["type"] == "text"
    text = payload["text"]
    assert "CASE-TEST-888" in text
    assert "2026-08-20" in text
    assert "NT$ 24,000" in text
    assert "寶寶與產婦狀況確認" in text
    assert "第一期款繳費說明" in text


def test_order_pre_start_template_renders_for_already_settled_case() -> None:
    templates_def = json.loads(Path("config/message_templates.json").read_text(encoding="utf-8"))

    event = from_order_pre_start_checkpoint(
        case_no="CASE-TEST-999",
        planned_start_date="2026-08-20",
        first_payment_amount=0,
        already_settled=True,
        occurred_at=datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )

    rendered = render_message_template(
        templates_def,
        "LU96-ORDER-PRE-START-REMINDER-CARD-V1",
        {
            "case_no": event.facts["case_no"],
            "planned_start_date": event.facts["planned_start_date"],
            "first_payment_amount": event.facts["first_payment_amount"],
            "first_payment_status": event.facts["first_payment_status"],
        },
    )

    payload = json.loads(rendered.payload_json)
    text = payload["text"]
    assert "CASE-TEST-999" in text
    assert "已結清" in text
    assert "已核銷完成" in text


def test_order_second_payment_rule_evaluates_to_intent_created() -> None:
    from subsystems.line.notification_source_adapters import from_order_second_payment_checkpoint

    rules_def = json.loads(Path("config/notification_rules.json").read_text(encoding="utf-8"))

    event = from_order_second_payment_checkpoint(
        case_no="CASE-TEST-777",
        second_payment_due_date="2026-09-10",
        second_payment_amount=36000,
        already_settled=False,
        occurred_at=datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc),
    )

    decisions = evaluate_notification_rules(event, rules_def)

    matching_decisions = [d for d in decisions if d.rule_id == "LU96-ORDER-SECOND-PAYMENT-REMINDER-V1"]
    assert len(matching_decisions) == 1
    assert matching_decisions[0].status == "intent_created"
    assert matching_decisions[0].reason_code == "rule_matched"


def test_order_second_payment_template_renders_properly() -> None:
    from subsystems.line.notification_source_adapters import from_order_second_payment_checkpoint

    templates_def = json.loads(Path("config/message_templates.json").read_text(encoding="utf-8"))

    event = from_order_second_payment_checkpoint(
        case_no="CASE-TEST-777",
        second_payment_due_date="2026-09-10",
        second_payment_amount=36000,
        already_settled=False,
        occurred_at=datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc),
    )

    rendered = render_message_template(
        templates_def,
        "LU96-ORDER-SECOND-PAYMENT-REMINDER-CARD-V1",
        {
            "case_no": event.facts["case_no"],
            "second_payment_due_date": event.facts["second_payment_due_date"],
            "second_payment_amount": event.facts["second_payment_amount"],
            "second_payment_status": event.facts["second_payment_status"],
        },
    )

    payload = json.loads(rendered.payload_json)
    assert payload["type"] == "text"
    text = payload["text"]
    assert "CASE-TEST-777" in text
    assert "2026-09-10" in text
    assert "NT$ 36,000" in text
    assert "第二期款（尾款）繳款提醒" in text
    assert "待繳納" in text
