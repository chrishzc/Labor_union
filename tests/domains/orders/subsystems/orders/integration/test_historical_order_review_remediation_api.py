"""
File: test_historical_order_review_remediation_api.py
Description: 驗證 Historical Orders remediation 的後端與 React strict DTO 對齊。
"""

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.routes.historical_order_review_remediation import (
    _apply_payload,
    _preview_payload,
    _query_payload,
)
from api.schemas.historical_order_review_remediation import (
    HistoricalReviewRemediationPreviewView,
    HistoricalReviewRemediationQueryView,
    HistoricalReviewRemediationReceiptView,
)
from domains.orders.historical_review_remediation import (
    HistoricalReviewContext,
    HistoricalReviewCorrectionCandidate,
    HistoricalReviewCorrectionSource,
    HistoricalReviewDisposition,
    conflict_for_issue,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_review_remediation_workflow import (
    HistoricalReviewRemediationPreview,
    HistoricalReviewRemediationQuery,
    HistoricalReviewRemediationReceipt,
)


def _context(identity="prior-review", *, remediation_version=0, alert_active=True):
    return HistoricalReviewContext(
        identity,
        f"historical-orders:{'a' * 64}:row:2",
        "b" * 64,
        "CA****01",
        "CASE-1",
        1,
        "review_required",
        None,
        0,
        remediation_version,
        (conflict_for_issue("historical_status_invalid", current_value="1"),),
        "王小明",
        alert_active,
    )


def test_query_payload_matches_react_contract_shape():
    payload = _query_payload(HistoricalReviewRemediationQuery(_context()))
    view = HistoricalReviewRemediationQueryView.model_validate(payload)
    assert view.issues[0].field_label == "訂單狀態"
    assert view.workbook_contract.single_row_only is True
    assert view.prior_alert_active is True


def test_preview_payload_is_flat_and_contains_complete_remaining_issue():
    source = HistoricalReviewCorrectionSource(
        "c" * 64,
        "source:2",
        "d" * 64,
        "CASE-1",
        "王小明",
        ("historical_status_invalid",),
        object(),
    )
    candidate = HistoricalReviewCorrectionCandidate(
        "prior-review",
        source,
        HistoricalReviewDisposition.SUPERSEDED_BY_REPLACEMENT_REVIEW,
        True,
        ("historical_status_invalid",),
        PreviewFingerprint("e" * 64),
    )
    payload = _preview_payload(
        HistoricalReviewRemediationPreview(
            _context(), candidate, ExpectedVersion(0), ExpectedVersion(0), PreviewFingerprint("f" * 64)
        )
    )
    view = HistoricalReviewRemediationPreviewView.model_validate(payload)
    assert view.prior_review_identity == "prior-review"
    assert view.remaining_issues[0].process_blocker


def test_apply_payload_keeps_alert_active_until_projector_readback():
    receipt = HistoricalReviewRemediationReceipt(
        "prior-review",
        "receipt:1",
        "corrected_source_adopted",
        None,
        "c" * 64,
        1,
        PreviewFingerprint("f" * 64),
        False,
    )

    class Application:
        def apply(self, command):
            return receipt

        def query(self, identity, correlation):
            assert identity == "prior-review"
            assert correlation == CorrelationId("corr")
            return HistoricalReviewRemediationQuery(
                _context(remediation_version=1, alert_active=True)
            )

    command = SimpleNamespace(correlation_id=CorrelationId("corr"))
    view = HistoricalReviewRemediationReceiptView.model_validate(
        _apply_payload(Application(), command)
    )
    assert view.prior_alert_active is True
    assert view.readback.remediation_version == 1
    assert view.readback.remaining_issues[0].issue_code == "historical_status_invalid"


def test_apply_payload_has_no_remaining_issues_only_after_explicit_inactive_readback():
    receipt = HistoricalReviewRemediationReceipt(
        "prior-review",
        "receipt:1",
        "corrected_source_adopted",
        None,
        "c" * 64,
        1,
        PreviewFingerprint("f" * 64),
        False,
    )

    class Application:
        def apply(self, _command):
            return receipt

        def query(self, _identity, _correlation):
            return HistoricalReviewRemediationQuery(
                _context(remediation_version=1, alert_active=False)
            )

    view = HistoricalReviewRemediationReceiptView.model_validate(
        _apply_payload(
            Application(),
            SimpleNamespace(correlation_id=CorrelationId("corr")),
        )
    )

    assert view.prior_alert_active is False
    assert view.readback.remaining_issues == []


def test_orders_owner_capability_is_required_and_materialized():
    request = SimpleNamespace(state=SimpleNamespace())
    unscoped = AdminPrincipal(
        None,
        "unscoped",
        "Unscoped",
        "line_viewer",
        capabilities=frozenset(),
    )
    with pytest.raises(HTTPException) as denied:
        require_historical_order_review_remediator(request, unscoped)
    assert denied.value.status_code == 403

    owner = AdminPrincipal(
        None,
        "orders-owner",
        "Orders Owner",
        "line_viewer",
        capabilities=frozenset({"orders.historical_review.remediate"}),
    )
    assert require_historical_order_review_remediator(request, owner) is owner
    assert request.state.admin_actor.permission_scope == (
        "orders.historical_review.remediate",
    )
