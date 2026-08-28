"""
File: test_anomaly_source_version.py
Description: 驗證異常掃描版號可跨越 legacy 日期值並反映同日 owner root 變更。
"""

from datetime import date, datetime

import pytest

from subsystems.anomalies.source_version import daily_root_source_version


def test_daily_root_version_supersedes_legacy_date_and_moves_with_root() -> None:
    business_date = date(2026, 8, 27)

    first = daily_root_source_version(as_of=business_date, root_version=0)
    second = daily_root_source_version(as_of=business_date, root_version=1)

    assert first > business_date.toordinal()
    assert second == first + 1


def test_next_business_date_is_newer_than_largest_supported_prior_root() -> None:
    prior = daily_root_source_version(
        as_of=date(2026, 8, 27), root_version=999_999_999
    )
    following = daily_root_source_version(as_of=date(2026, 8, 28), root_version=0)

    assert following > prior


@pytest.mark.parametrize("root_version", [-1, True, 1_000_000_000])
def test_daily_root_version_rejects_unusable_owner_versions(root_version) -> None:
    with pytest.raises((TypeError, ValueError)):
        daily_root_source_version(as_of=date(2026, 8, 27), root_version=root_version)


def test_daily_root_version_rejects_datetime() -> None:
    with pytest.raises(TypeError, match="as of date"):
        daily_root_source_version(
            as_of=datetime(2026, 8, 27, 12, 0), root_version=1
        )
