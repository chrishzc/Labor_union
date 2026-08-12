import pytest

from domains.anomalies.registry import default_anomaly_registry
from subsystems.anomalies.government_return_outbound_overage_anomaly_source import (
    GovernmentReturnOutboundOverageAnomalyConsumer,
    GovernmentReturnOutboundOverageRootFact,
    GovernmentReturnOutboundOverageScanPage,
    GovernmentReturnOutboundOverageScanRequest,
    build_government_return_outbound_overage_request,
)


def test_outgoing_government_return_overage_projects_a_state_only_root_fact() -> None:
    request = build_government_return_outbound_overage_request(_root_fact())

    assert request.desired.definition_code == "GOVSUB-007"
    assert request.desired.active is True
    assert request.display_snapshot["excess_amount_ntd"] == 250
    assert request.desired.source_identity == "finance-import-row:17:return:return-1"
    assert default_anomaly_registry().require("GOVSUB-007").available_actions == ()


def test_non_overage_cannot_create_a_government_return_overage_alert() -> None:
    with pytest.raises(ValueError, match="not_present"):
        build_government_return_outbound_overage_request(
            GovernmentReturnOutboundOverageRootFact(17, "bank-17", "return-1", "over-1", 500, 500, 2)
        )


def test_projector_consumes_only_the_bounded_overage_source_page() -> None:
    application = _Application()
    consumer = GovernmentReturnOutboundOverageAnomalyConsumer(
        _Source((_root_fact(),)), application
    )

    result = consumer.scan_page(GovernmentReturnOutboundOverageScanRequest(limit=1))

    assert result.next_finance_import_row_id == 17
    assert len(application.requests) == 1
    assert application.requests[0].desired.definition_code == "GOVSUB-007"


def _root_fact() -> GovernmentReturnOutboundOverageRootFact:
    return GovernmentReturnOutboundOverageRootFact(17, "bank-17", "return-1", "over-1", 750, 500, 2)


class _Source:
    def __init__(self, facts) -> None:
        self._facts = facts

    def load_page(self, request):
        assert request.limit == 1
        return GovernmentReturnOutboundOverageScanPage(self._facts, 17)


class _Application:
    def __init__(self) -> None:
        self.requests = []

    def project(self, request):
        self.requests.append(request)
        return request.desired
