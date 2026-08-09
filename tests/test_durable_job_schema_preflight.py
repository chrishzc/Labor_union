import pytest
import subprocess
import sys
from pathlib import Path

from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    DurableJobSchemaNotReady,
)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        return False

    def execute(self, statement, parameters=()):
        self.statements.append((statement, parameters))

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_queue_schema_preflight_accepts_all_required_columns():
    columns = [
        {"queue_column_name": name}
        for name in (
            "job_id", "command_identity", "command_type", "command_version",
            "command_payload", "submitted_by", "correlation_id", "status",
            "available_at", "attempt_count", "max_attempts", "lease_token",
            "lease_owner", "lease_expires_at", "receipt_payload", "error_payload",
            "result_reference", "completed_at", "created_at", "updated_at",
        )
    ]
    connection = _Connection(columns)

    BackgroundJobRepository(connection).assert_durable_queue_schema()

    statement = connection.cursor_instance.statements[0][0]
    assert "information_schema.columns" in statement
    assert "background_jobs" in statement


def test_queue_schema_preflight_reports_missing_columns_without_mutation():
    connection = _Connection([{"queue_column_name": "job_id"}])

    with pytest.raises(DurableJobSchemaNotReady, match="durable_job_schema_not_ready") as raised:
        BackgroundJobRepository(connection).assert_durable_queue_schema()

    assert "command_payload" in raised.value.missing_columns
    assert len(connection.cursor_instance.statements) == 1


def test_worker_script_help_does_not_require_pythonpath_or_database():
    script = Path(__file__).resolve().parents[1] / "scripts/run_durable_job_worker.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--check" in result.stdout
