"""
File: test_line_delivery_public_query.py
Description: 驗證 LINE Delivery 查詢的安全投影、篩選與資料形狀邊界。
"""

from datetime import datetime, timezone

import pytest

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId
from infrastructure.mysql.line_delivery_task_repository import _admin_record
from api.routes.line_tasks import _public_source_type
from api.schemas.line_tasks import LineDeliveryPublicSourceType
from subsystems.line.delivery_admin_contracts import LineDeliveryAdminQuery


def _row(*, extra: bool = False) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 7,
        "recipient_type": "user",
        "recipient_identity": "U-secret",
        "message_kind": "text",
        "payload_snapshot": '{"text":"secret"}',
        "processing_status": "sent",
        "scheduled_at_utc": datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
        "source_aggregate_type": "customer_service_ticket",
        "source_aggregate_identity": "CASE-secret",
        "completed_attempts": 1,
        "max_attempts": 3,
        "next_attempt_at_utc": None,
        "provider_message_id": "provider-secret",
        "error_code": "provider-secret-error",
        "error_message": "provider raw error",
        "sent_at_utc": datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
        "failed_at_utc": None,
        "created_at_utc": datetime(2026, 8, 20, 0, tzinfo=timezone.utc),
        "updated_at_utc": datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
    }
    if extra:
        row["unexpected_sensitive_field"] = "must-fail-closed"
    return row


def test_admin_record_rejects_extra_sensitive_columns() -> None:
    with pytest.raises(ValueError, match="shape"):
        _admin_record(_row(extra=True))


def test_admin_record_rejects_missing_contract_columns() -> None:
    row = _row()
    row.pop("updated_at_utc")

    with pytest.raises(ValueError, match="shape"):
        _admin_record(row)


def test_admin_record_masks_group_invitation_uri_in_representative_row() -> None:
    row = _row()
    row["source_aggregate_type"] = "line_order_group_invitation"
    row["payload_snapshot"] = (
        '{"contents":{"footer":{"contents":[{"action":'
        '{"uri":"https://private.example/invitation"}}]}}}'
    )

    record = _admin_record(row)

    assert "https://private.example/invitation" not in record.payload_json
    assert "[REDACTED]" in record.payload_json


def test_admin_query_accepts_only_bounded_safe_source_types() -> None:
    query = LineDeliveryAdminQuery(
        source_aggregate_types=("customer_service_ticket",),
        page=1,
        page_size=25,
    )
    assert query.source_aggregate_types == ("customer_service_ticket",)


def test_public_projection_does_not_use_internal_record_as_public_view() -> None:
    record = _admin_record(_row())
    assert isinstance(record.task_id, LineDeliveryTaskId)
    assert record.status is LineDeliveryStatus.SENT


@pytest.mark.parametrize(
    "source_aggregate_type",
    ("matching_schedule_recipient", "matching_schedule_snapshot"),
)
def test_matching_schedule_records_keep_bounded_source_and_redact_payload(
    source_aggregate_type: str,
) -> None:
    row = _row()
    row["source_aggregate_type"] = source_aggregate_type
    row["payload_snapshot"] = '{"recipient":"U-secret","uri":"https://secret.example"}'

    record = _admin_record(row)

    assert record.source_aggregate_type == source_aggregate_type
    assert _public_source_type(record.source_aggregate_type) is LineDeliveryPublicSourceType.MATCHING
