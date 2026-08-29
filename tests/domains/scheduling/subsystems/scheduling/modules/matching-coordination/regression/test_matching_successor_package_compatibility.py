"""
File: test_matching_successor_package_compatibility.py
Description: 驗證空候選 successor package 可由既有 Matching reader 完整還原。
"""

from datetime import date, datetime, timezone
import json

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingDomainError,
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
)
from infrastructure.mysql.matching_coordination_repository import (
    MySqlMatchingCoordinationRepository,
    _json_dump,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint


class _Cursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, sql, params=()):
        self._executed_sql = sql

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _Cursor(self._row)


def _sources() -> tuple[MatchingSourceVersion, ...]:
    return tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, f"{index:064x}")
        for index, kind in enumerate(SOURCE_KINDS, start=1)
    )


def _candidate_pool_open_package() -> MatchingPackage:
    return MatchingPackage(
        package_id="package:case-001:1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(),
        required_service_dates=(date(2026, 9, 1),),
        candidate_results=(),
        criteria_snapshot_id="snapshot:case-001:1",
        source_versions=_sources(),
        state=MatchingPackageState.CANDIDATE_POOL_OPEN,
    )


def test_candidate_pool_open_is_the_only_empty_package_state() -> None:
    package = _candidate_pool_open_package()

    assert package.state is MatchingPackageState.CANDIDATE_POOL_OPEN
    assert package.segments == ()
    assert package.candidate_results == ()
    assert package.canonical_payload()["state"] == "candidate_pool_open"

    for state in (
        MatchingPackageState.PROPOSED,
        MatchingPackageState.NO_CANDIDATE,
        MatchingPackageState.REMATCH_REQUIRED,
    ):
        with pytest.raises(MatchingDomainError):
            MatchingPackage(
                package_id=f"package:case-001:{state.value}",
                version=1,
                mode=MatchingPackageMode.SINGLE,
                segments=(),
                required_service_dates=(date(2026, 9, 1),),
                candidate_results=(),
                criteria_snapshot_id="snapshot:case-001:1",
                source_versions=_sources(),
                state=state,
            )


def test_existing_load_current_package_reader_round_trips_open_successor() -> None:
    package = _candidate_pool_open_package()
    row = {
        "package_snapshot": json.loads(_json_dump(package)),
        "package_digest": package.fingerprint.value,
    }
    repository = MySqlMatchingCoordinationRepository(
        _Connection(row),
        FixedBusinessClock(datetime(2026, 8, 28, tzinfo=timezone.utc)),
    )

    loaded = repository.load_current_package("CASE-001")

    assert loaded == package
    assert loaded is not None
    assert loaded.state is MatchingPackageState.CANDIDATE_POOL_OPEN
    assert loaded.fingerprint == PreviewFingerprint(package.fingerprint.value)


def test_candidate_pool_open_rejects_candidate_or_segment_facts() -> None:
    candidate = MatchingCandidateResult(
        "candidate:1", 7, CandidateEligibility.INELIGIBLE, ()
    )
    common = dict(
        package_id="package:case-001:1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        required_service_dates=(date(2026, 9, 1),),
        criteria_snapshot_id="snapshot:case-001:1",
        source_versions=_sources(),
        state=MatchingPackageState.CANDIDATE_POOL_OPEN,
    )

    with pytest.raises(MatchingDomainError):
        MatchingPackage(**common, segments=(), candidate_results=(candidate,))
    with pytest.raises(MatchingDomainError):
        MatchingPackage(
            **common,
            segments=(MatchingSegment(7, (date(2026, 9, 1),), 1),),
            candidate_results=(),
        )
