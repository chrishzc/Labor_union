"""
File: test_retired_release_fresh_readiness.py
Description: 驗證 fresh schema 缺少已退役 release 時仍可通過 current readiness。
"""

from types import SimpleNamespace

from scripts import migrate_preserved_database_additive_schema as runner
from scripts import update_local_database as update


def test_retired_weekly_batch_absence_does_not_create_a_release_chain_hole(
    monkeypatch,
) -> None:
    entries = (
        {
            "release_id": "baseline",
            "release_fingerprint": "f0",
            "artifact": {"name": runner.LOCAL_ADDITIVE_BASELINE_ARTIFACT},
            "descriptor": {},
        },
        {
            "release_id": "retired-weekly-batches",
            "release_fingerprint": "f1",
            "artifact": {"name": "1031_weekly_report_batches.sql"},
            "descriptor": {},
        },
        {
            "release_id": "current",
            "release_fingerprint": "f2",
            "artifact": {"name": "1035_weekly_report_metrics.sql"},
            "descriptor": {},
        },
    )
    states = iter(("exact", "absent", "exact"))
    monkeypatch.setattr(runner, "_local_ordered_upgrade_entries", lambda: entries)
    monkeypatch.setattr(
        runner,
        "local_additive_target_state",
        lambda *_args, **_kwargs: {"state": next(states)},
    )

    result = runner._local_ordered_chain_plan(
        SimpleNamespace(), "union_db", {"sha256": "a" * 64}
    )

    assert result["pending_releases"] == []
    assert [item["state"] for item in result["artifacts"]] == [
        "exact",
        "retired_absent",
        "exact",
    ]

    preview = {
        **result,
        "status": "current",
        "release_id": "current",
        "release_fingerprint": "f2",
    }
    assert update.require_current_database(preview)["status"] == "current"
