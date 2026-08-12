"""Regression coverage for Government Subsidy durable-job status reads."""

from pathlib import Path


CLIENT = Path("ui/api_clients/government_subsidy_api_client.py")


def test_job_status_uses_the_client_typed_get_request_path() -> None:
    source = CLIENT.read_text(encoding="utf-8")

    assert '"GET",\n            f"/api/v1/jobs/{job_id}"' in source
    assert "return self._query(f\"/api/v1/jobs/{job_id}\"" not in source
