"""Stage 4.R contracts for isolated LINE migration rehearsals."""

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
    )
)


def test_line_release_chain_selects_stage2_through_stage4() -> None:
    original = _runner_release_state()
    try:
        runner.configure_release_manifests(MANIFESTS)

        assert tuple(path.name for path in runner.SCHEMA_PARTS) == (
            "154_line_integration_inbox_delivery.sql",
            "155_line_identity_review_configuration.sql",
            "156_line_publication_media_order_group.sql",
            "157_line_runtime_control.sql",
            "158_line_identity_runtime.sql",
        )
        assert runner.MANIFEST_DRIVEN_RELEASE is True
        assert len(runner.RELEASE_MANIFEST.manifests) == 3
        assert set(runner.OWNED_OBJECTS) == {
            path.name for path in runner.SCHEMA_PARTS
        }
    finally:
        _restore_runner_release_state(original)


def test_line_release_chain_rejects_reverse_order() -> None:
    original = _runner_release_state()
    try:
        with pytest.raises(
            runner.UpgradeBlocked,
            match="unique and ordered",
        ):
            runner.configure_release_manifests(reversed(MANIFESTS))
    finally:
        _restore_runner_release_state(original)


@pytest.mark.parametrize(
    ("source", "candidate"),
    (
        ("labor_union", "lu_test_candidate"),
        ("lu_test_source", "labor_union_candidate"),
    ),
)
def test_rehearsal_rejects_non_test_database_names(
    source: str,
    candidate: str,
) -> None:
    with pytest.raises(runner.UpgradeBlocked, match=r"lu_test_\*"):
        runner.validate_rehearsal_database_names(source, candidate)


def test_candidate_can_add_tables_while_preserving_source_data() -> None:
    source = {"line_users": {"count": 2, "checksum": 10}}
    candidate = {
        **source,
        "line_platform_users": {"count": 2, "checksum": 20},
    }

    assert runner._candidate_preserves_source_data(source, candidate) is True


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
