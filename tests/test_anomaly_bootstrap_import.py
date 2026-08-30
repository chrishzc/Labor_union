def test_application_bootstraps_canonical_anomalies() -> None:
    import api.main

    paths = api.main.app.openapi()["paths"]

    assert "/api/v1/anomalies" in paths
    assert "/api/v1/anomaly-recovery/{issue_key}" in paths
