import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RETIRED_PROVIDER_NAME = "breezysign"


def test_retired_provider_is_absent_from_current_runtime_schema_and_baselines():
    current_paths = _current_runtime_schema_and_baseline_paths()

    for path in current_paths:
        assert RETIRED_PROVIDER_NAME not in path.read_text(encoding="utf-8").lower(), path


def test_legacy_provider_column_is_absent_outside_its_one_time_migration():
    active_paths = tuple(
        path
        for path in _current_runtime_schema_and_baseline_paths()
        if path.name not in {
            "migrate_order_contract_identity.py",
            "migrate_preserved_database_additive_schema.py",
        }
        and not _is_historical_baseline_artifact(path)
    )

    for path in active_paths:
        content = path.read_text(encoding="utf-8")
        assert re.search(r"\bcontract_id\b", content) is None, path


def _is_historical_baseline_artifact(path: Path) -> bool:
    """The historical projector owns a separate, intentionally named contract_id."""
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    return "historical_baseline" in relative or "historical_operational_baseline" in relative


def _current_runtime_schema_and_baseline_paths() -> tuple[Path, ...]:
    source_roots = ("api", "domains", "infrastructure", "line", "scripts", "services", "subsystems", "ui")
    source_files = tuple(
        path
        for root_name in source_roots
        for path in (REPOSITORY_ROOT / root_name).rglob("*.py")
    )
    schema_files = (REPOSITORY_ROOT / "db" / "schema.sql",) + tuple(
        (REPOSITORY_ROOT / "db" / "schema_parts").glob("*.sql")
    )
    baseline_files = tuple(
        (REPOSITORY_ROOT / "document" / "架構重整" / "01_規格基線").glob("*.md")
    )
    metadata_files = (
        REPOSITORY_ROOT / "document" / "架構重整" / "README.md",
        REPOSITORY_ROOT / "document" / "管理端UI" / "可替換前端與Streamlit薄顯示層重整計畫.md",
    )
    return source_files + schema_files + baseline_files + metadata_files
