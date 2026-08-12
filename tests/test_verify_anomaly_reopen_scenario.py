from scripts.verify_anomaly_reopen_scenario import _checks


def test_anomaly_reopen_verifier_requires_full_history_and_open_recurrence():
    observed = {"status": "open", "timeline_actions": ["claim", "resolve", "reopen", "auto_resolve", "reopen"]}

    assert all(check["passed"] for check in _checks(observed))
