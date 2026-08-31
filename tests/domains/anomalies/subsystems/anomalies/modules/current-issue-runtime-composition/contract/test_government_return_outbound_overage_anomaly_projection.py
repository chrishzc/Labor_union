import pytest

from domains.anomalies.registry import default_anomaly_registry
from subsystems.anomalies.government_return_outbound_overage_anomaly_source import (
    GovernmentReturnOutboundOverageAnomalyConsumer,
    GovernmentReturnOutboundOverageRootFact,
    GovernmentReturnOutboundOverageScanRequest,
    build_government_return_outbound_overage_request,
)


def test_retired_government_overage_producer_fails_closed() -> None:
    with pytest.raises(ValueError, match="GOVSUB-007 runtime anomaly producer is retired"):
        build_government_return_outbound_overage_request(_root_fact())

    with pytest.raises(ValueError, match="anomaly_definition_not_found"):
        default_anomaly_registry().require("GOVSUB-007")


def test_non_overage_cannot_create_a_government_return_overage_alert() -> None:
    with pytest.raises(ValueError, match="GOVSUB-007 runtime anomaly producer is retired"):
        build_government_return_outbound_overage_request(
            GovernmentReturnOutboundOverageRootFact(17, "bank-17", "return-1", "over-1", 500, 500, 2)
        )


def test_retired_government_overage_consumer_fails_closed() -> None:
    consumer = GovernmentReturnOutboundOverageAnomalyConsumer(object(), object())

    with pytest.raises(RuntimeError, match="GOVSUB-007 runtime anomaly producer is retired"):
        consumer.scan_page(GovernmentReturnOutboundOverageScanRequest(limit=1))


def _root_fact() -> GovernmentReturnOutboundOverageRootFact:
    return GovernmentReturnOutboundOverageRootFact(17, "bank-17", "return-1", "over-1", 750, 500, 2)
