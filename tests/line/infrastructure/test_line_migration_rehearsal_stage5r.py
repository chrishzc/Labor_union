"""Stage 5.R contracts for isolated LINE messaging migration rehearsals."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import migrate_preserved_database_additive_schema as runner


ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = tuple(
    ROOT / "db" / "migration_releases" / name
    for name in (
        "labor_union_2026_08_08_line_stage2_v1.json",
        "labor_union_2026_08_08_line_stage3_v1.json",
        "labor_union_2026_08_08_line_stage4_v1.json",
        "labor_union_2026_08_08_line_stage5_v1.json",
    )
)


def test_line_release_chain_selects_stage2_through_stage5() -> None:
    original = _runner_release_state()
    try:
        runner.configure_release_manifests(MANIFESTS)

        assert tuple(path.name for path in runner.SCHEMA_PARTS) == (
            "154_line_integration_inbox_delivery.sql",
            "155_line_identity_review_configuration.sql",
            "156_line_publication_media_order_group.sql",
            "157_line_runtime_control.sql",
            "158_line_identity_runtime.sql",
            "159_line_messaging_publication_runtime.sql",
        )
        assert runner.MANIFEST_DRIVEN_RELEASE is True
        assert len(runner.RELEASE_MANIFEST.manifests) == 4
        assert set(runner.OWNED_OBJECTS) == {
            path.name for path in runner.SCHEMA_PARTS
        }
    finally:
        _restore_runner_release_state(original)


def test_additive_columns_compare_only_the_source_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {
        "columns": [
            {"table_name": "line_domain_outbox", "column_name": "id"},
            {"table_name": "line_domain_outbox", "column_name": "status"},
        ]
    }
    calls: list[tuple[str, tuple[str, ...]]] = []

    def evidence(_config, database, _table, columns):
        calls.append((database, tuple(columns)))
        return {
            "columns": columns,
            "row_count": 1,
            "rows_sha256": "same-legacy-values",
        }

    monkeypatch.setattr(runner, "_table_projection_evidence", evidence)

    result = runner._verify_source_column_projection_preserved(
        None,
        "lu_test_source",
        "lu_test_candidate",
        "line_domain_outbox",
        snapshot,
    )

    assert result["rows_sha256"] == "same-legacy-values"
    assert calls == [
        ("lu_test_source", ("id", "status")),
        ("lu_test_candidate", ("id", "status")),
    ]


def test_additive_projection_rejects_changed_legacy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {
        "columns": [
            {"table_name": "line_domain_outbox", "column_name": "id"},
        ]
    }

    def evidence(_config, database, _table, columns):
        return {
            "columns": columns,
            "row_count": 1,
            "rows_sha256": database,
        }

    monkeypatch.setattr(runner, "_table_projection_evidence", evidence)

    with pytest.raises(
        runner.UpgradeBlocked,
        match="preserved table projection changed",
    ):
        runner._verify_source_column_projection_preserved(
            None,
            "lu_test_source",
            "lu_test_candidate",
            "line_domain_outbox",
            snapshot,
        )


def _runner_release_state() -> tuple[object, object, object, bool]:
    return (
        runner.RELEASE_MANIFEST,
        runner.SCHEMA_PARTS,
        runner.OWNED_OBJECTS,
        runner.MANIFEST_DRIVEN_RELEASE,
    )


def _restore_runner_release_state(
    state: tuple[object, object, object, bool],
) -> None:
    (
        runner.RELEASE_MANIFEST,
        runner.SCHEMA_PARTS,
        runner.OWNED_OBJECTS,
        runner.MANIFEST_DRIVEN_RELEASE,
    ) = state
