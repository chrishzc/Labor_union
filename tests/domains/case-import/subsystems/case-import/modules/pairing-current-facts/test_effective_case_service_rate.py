"""Effective BeClass birth-count corrections drive the shared service rate."""

from datetime import date

import pytest

from infrastructure.mysql.effective_case_service_rate import (
    load_explicit_case_service_rate,
)


class _Cursor:
    def __init__(self, responses):
        self._responses = iter(responses)
        self._current = None
        self.statements = []

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        self._current = next(self._responses)

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


def test_explicit_twins_correction_resolves_the_effective_450_policy():
    cursor = _Cursor(
        [
            {
                "identity_status": "一般市民",
                "start_date": date(2026, 10, 1),
                "effective_values_json": '{"multi_birth_count":"雙胞胎"}',
            },
            (
                {
                    "policy_version": "2026-twins",
                    "policy_kind": "twins",
                    "hourly_rate_ntd": 450,
                },
            ),
        ]
    )

    result = load_explicit_case_service_rate(cursor, "CASE-450", lock=True)

    assert result is not None
    assert result.multi_birth_count == "雙胞胎"
    assert result.policy_kind == "twins"
    assert result.hourly_rate_ntd == 450
    assert all("FOR UPDATE" in statement for statement, _ in cursor.statements)


def test_missing_explicit_birth_count_keeps_the_existing_rate_snapshot():
    cursor = _Cursor(
        [
            {
                "identity_status": "一般市民",
                "start_date": date(2026, 10, 1),
                "effective_values_json": '{"phone":"0912345678"}',
            }
        ]
    )

    assert load_explicit_case_service_rate(cursor, "CASE-300") is None
    assert len(cursor.statements) == 1


def test_overlapping_effective_rate_policies_fail_closed():
    cursor = _Cursor(
        [
            {
                "identity_status": "一般市民",
                "start_date": date(2026, 10, 1),
                "effective_values_json": '{"multi_birth_count":"雙胞胎"}',
            },
            (
                {"policy_version": "a", "policy_kind": "twins", "hourly_rate_ntd": 450},
                {"policy_version": "b", "policy_kind": "twins", "hourly_rate_ntd": 450},
            ),
        ]
    )

    with pytest.raises(ValueError, match="payroll_rate_policy_not_found"):
        load_explicit_case_service_rate(cursor, "CASE-AMBIGUOUS")
