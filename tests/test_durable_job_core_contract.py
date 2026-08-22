"""
File: test_durable_job_core_contract.py
Description: 驗證 Durable Job canonical equality、actor/key、closed outcome 與 canonical repository 零 hidden commit。
"""

from __future__ import annotations

import math

import pytest

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobLease
from subsystems.jobs.contracts import (
    DurableJobContractViolation,
    DurableJobFailureOutcome,
    DurableJobSuccessOutcome,
    canonicalize_payload,
    equality_for,
    equality_mismatches,
    validate_command_key,
    validate_submitted_by,
)


def _command(**overrides) -> DurableJobCommand:
    values = {
        "job_id": "job-1",
        "command_identity": "job.core.key-1",
        "command_type": "test.command",
        "command_version": 1,
        "payload": {"array": [1, 1.0, None, "台灣"], "object": {"b": 2, "a": 1}},
        "submitted_by": "admin_user_id:7",
        "correlation_id": "corr-1",
        "max_attempts": 3,
    }
    values.update(overrides)
    return DurableJobCommand(**values)


def test_canonical_payload_preserves_json_type_order_and_unicode_contract() -> None:
    first = canonicalize_payload({"z": None, "items": [1, 1.0, "台灣"], "a": {"b": 2}})
    second = canonicalize_payload({"a": {"b": 2}, "items": [1, 1.0, "台灣"], "z": None})

    assert first == second
    assert first == '{"a":{"b":2},"items":[1,1.0,"台灣"],"z":null}'
    assert canonicalize_payload({"value": 1}) != canonicalize_payload({"value": 1.0})
    assert canonicalize_payload({"items": [1, 2]}) != canonicalize_payload({"items": [2, 1]})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_payload_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(DurableJobContractViolation):
        canonicalize_payload({"value": value})


def test_canonical_payload_requires_object_and_string_keys() -> None:
    with pytest.raises(DurableJobContractViolation):
        canonicalize_payload(["not-an-object"])
    with pytest.raises(DurableJobContractViolation):
        canonicalize_payload({1: "not-a-string-key"})


@pytest.mark.parametrize("value", ["Key", " key", "key/unsafe", "", "a" * 192])
def test_canonical_command_key_rejects_non_lowercase_or_unsafe_values(value: str) -> None:
    with pytest.raises(DurableJobContractViolation):
        validate_command_key(value)


@pytest.mark.parametrize(
    "value",
    ["admin", "Admin_user_id:1", "admin_user_id:0", "system", "system:Owner"],
)
def test_submitted_actor_requires_immutable_approved_identity(value: str) -> None:
    with pytest.raises(DurableJobContractViolation):
        validate_submitted_by(value)
    assert validate_submitted_by("admin_user_id:1") == "admin_user_id:1"
    assert validate_submitted_by("system:durable-worker") == "system:durable-worker"


def test_business_equality_excludes_correlation_but_detects_all_frozen_fields() -> None:
    baseline = equality_for("test.command", 1, {"value": 1}, "admin_user_id:1")
    same_with_other_correlation = equality_for(
        "test.command", 1, {"value": 1}, "admin_user_id:1"
    )
    assert equality_mismatches(baseline, same_with_other_correlation) == ()
    assert equality_mismatches(
        baseline,
        equality_for("other.command", 1, {"value": 1}, "admin_user_id:1"),
    ) == ("command_type",)
    assert equality_mismatches(
        baseline,
        equality_for("test.command", 2, {"value": 1}, "admin_user_id:1"),
    ) == ("command_version",)
    assert equality_mismatches(
        baseline,
        equality_for("test.command", 1, {"value": 1.0}, "admin_user_id:1"),
    ) == ("canonical_payload",)
    assert equality_mismatches(
        baseline,
        equality_for("test.command", 1, {"value": 1}, "admin_user_id:2"),
    ) == ("submitted_by",)


def test_terminal_outcomes_are_closed_versioned_and_allowlisted() -> None:
    success = DurableJobSuccessOutcome("result:1").to_payload()
    failure = DurableJobFailureOutcome(
        "domain_blocked",
        "test_blocked",
        "The command is blocked.",
        domain_blockers=("hold.active",),
    ).to_payload()

    assert success == {"kind": "success", "result_reference": "result:1", "schema_version": 1}
    assert set(failure) == {"error", "kind", "schema_version"}
    assert set(failure["error"]) == {
        "category",
        "code",
        "domain_blockers",
        "message",
        "retryable",
    }


class _Cursor:
    def __init__(self, row=None):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _sql, _params=()):
        return 1

    def fetchone(self):
        return self.row

    def fetchall(self):
        return ()


class _NoHiddenTransactionConnection:
    def __init__(self, row=None):
        self.row = row
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self.row)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_all_canonical_repository_mutations_have_zero_hidden_commit_or_rollback() -> None:
    connection = _NoHiddenTransactionConnection()
    repository = BackgroundJobRepository(connection)
    command = _command()
    lease = DurableJobLease(command.job_id, "lease-1", command, 1)

    assert repository.enqueue_canonical_command(command) == command.job_id
    assert repository.recover_expired_canonical_leases(0) == 2
    assert repository.claim_next_canonical_command("worker-1", 60) is None
    repository.complete_canonical_claim(lease, DurableJobSuccessOutcome("result:1"))
    repository.fail_canonical_claim(
        lease,
        DurableJobFailureOutcome("unavailable", "retry", "Retry later.", retryable=True),
        1,
    )

    assert connection.commits == 0
    assert connection.rollbacks == 0


@pytest.mark.parametrize(
    "row",
    [
        ("job-1", "job.key", "test.command", 1, None, "admin_user_id:1", "corr", 0, 3),
        ("job-1", "job.key", "test.command", 1, "[]", "admin_user_id:1", "corr", 0, 3),
        ("job-1", "job.key", "test.command", 1, "not-json", "admin_user_id:1", "corr", 0, 3),
        ("job-1", "job.key", "test.command", 1, "{}", None, "corr", 0, 3),
    ],
)
def test_canonical_reader_fails_closed_for_legacy_or_invalid_rows(row) -> None:
    repository = BackgroundJobRepository(_NoHiddenTransactionConnection(row))
    with pytest.raises(DurableJobContractViolation):
        repository.read_canonical_command_by_identity("job.key")
