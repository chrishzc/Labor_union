"""
File: test_order_auto_completion_routes.py
Description: 驗證服務完成 Preview 與 Apply route 將 value objects materialize 成公開 typed payload。
"""

from datetime import datetime
from types import SimpleNamespace

from api.routes.order_auto_completion import (
    OrderAutoCompletionApplyBody,
    OrderAutoCompletionPreviewBody,
    apply_order_auto_completion,
    preview_order_auto_completion,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.orders.auto_completion_workflow import (
    AutoCompletionPreview,
    AutoCompletionReceipt,
)


NOW = datetime.fromisoformat("2026-08-24T17:00:00+08:00")


def test_preview_route_materializes_preview_fingerprint() -> None:
    application = SimpleNamespace(
        preview=lambda _: AutoCompletionPreview(
            "CASE-1",
            5,
            6,
            "服務中",
            NOW,
            NOW,
            ("2026-08-24",),
            PreviewFingerprint("a" * 64),
        )
    )

    response = preview_order_auto_completion(
        body=OrderAutoCompletionPreviewBody(evaluation_at=NOW),
        case_no="CASE-1",
        correlation_id="preview-correlation",
        principal=SimpleNamespace(username="admin"),
        application=application,
    )

    assert response.data["fingerprint"] == "a" * 64
    assert response.data["expected_order_version"] == 5


def test_apply_route_materializes_receipt_value_objects() -> None:
    application = SimpleNamespace(
        apply=lambda _: AutoCompletionReceipt(
            "CASE-1",
            IdempotencyKey("completion-key"),
            6,
            9,
            NOW,
            NOW,
            PreviewFingerprint("b" * 64),
        )
    )

    response = apply_order_auto_completion(
        body=OrderAutoCompletionApplyBody(
            expected_order_version=5,
            evaluation_at=NOW,
            reason="confirmed completion",
            preview_fingerprint="a" * 64,
        ),
        case_no="CASE-1",
        idempotency_key="completion-key",
        correlation_id="apply-correlation",
        principal=SimpleNamespace(username="admin"),
        application=application,
    )

    assert response.data["idempotency_key"] == "completion-key"
    assert response.data["command_fingerprint"] == "b" * 64
    assert response.data["lifecycle_event_id"] == 9
