from infrastructure.mysql.scheduling_anomaly_recheck_sink import (
    MySqlSchedulingAnomalyRecheckSink,
)
from subsystems.scheduling.current_anomaly_facts import (
    build_scheduling_coverage_recheck_request,
)


class _Repository:
    def __init__(self) -> None:
        self.intents = []

    def append_recheck_intent(self, intent) -> None:
        self.intents.append(intent)


def test_infrastructure_composes_owner_request_into_anomalies_intent() -> None:
    repository = _Repository()
    sink = MySqlSchedulingAnomalyRecheckSink.__new__(MySqlSchedulingAnomalyRecheckSink)
    sink._repository = repository

    sink.append_scheduling_recheck(
        build_scheduling_coverage_recheck_request(
            "CASE-1", 5, 3, "assignment-plan-current-anomaly-1"
        )
    )

    assert len(repository.intents) == 1
    intent = repository.intents[0]
    assert intent.scope.subject_type == "SCHEDULE-006"
    assert intent.scope.subject_ids == ("CASE-1:5",)
    assert intent.scope.owner_lock_keys == (
        "scheduling:scheduling_current_fact:case:CASE-1",
    )
    assert intent.owner_version == 3
