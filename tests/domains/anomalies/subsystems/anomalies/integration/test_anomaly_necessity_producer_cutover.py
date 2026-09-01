"""
File: test_anomaly_necessity_producer_cutover.py
Description: 驗證退役的 process-reminder anomaly scan 不再查詢或投影。
"""

import ast
from datetime import date
from pathlib import Path

from infrastructure.mysql.process_reminder_anomaly_source import _scan_all


_PROJECT_ROOT = Path(__file__).resolve().parents[6]
_RUNTIME_ROOTS = tuple(
    _PROJECT_ROOT / relative
    for relative in ("api", "domains", "infrastructure", "line", "subsystems")
)
_RETIRED_ANOMALY_MODULES = frozenset(
    {
        "infrastructure.mysql.beclass_import_review_anomaly_source",
        "infrastructure.mysql.process_reminder_anomaly_source",
        "subsystems.anomalies.beclass_import_anomaly_consumer",
        "subsystems.anomalies.government_return_outbound_overage_anomaly_source",
        "subsystems.anomalies.government_subsidy_anomaly_source",
        "subsystems.anomalies.government_subsidy_integrity_anomaly_source",
        "subsystems.anomalies.government_subsidy_reversal_anomaly_source",
        "subsystems.anomalies.process_reminder_anomaly_source",
        "subsystems.anomalies.staff_payables_anomaly_source",
    }
)
_RETIRED_ANOMALY_PATHS = frozenset(
    module.replace(".", "/") + ".py" for module in _RETIRED_ANOMALY_MODULES
)


class _EmptyCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _parameters=None) -> None:
        self.statements.append(statement)

    def fetchall(self):
        return []


class _EmptyConnection:
    def __init__(self) -> None:
        self.cursor_instance = _EmptyCursor()

    def cursor(self):
        return self.cursor_instance


def test_retired_runtime_scan_does_not_query_or_project_legacy_anomalies() -> None:
    connection = _EmptyConnection()

    assert _scan_all(connection, date(2026, 8, 27)) == ()
    assert all(
        "staff_holiday_availability" not in statement
        for statement in connection.cursor_instance.statements
    )


def test_retired_anomaly_sources_have_no_production_importers() -> None:
    """The only remaining references may be owner tests or test-only runners."""

    importers: list[str] = []
    for runtime_root in _RUNTIME_ROOTS:
        for path in runtime_root.rglob("*.py"):
            relative = path.relative_to(_PROJECT_ROOT).as_posix()
            if relative in _RETIRED_ANOMALY_PATHS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported = None
                if isinstance(node, ast.Import):
                    imported = next(
                        (alias.name for alias in node.names if alias.name in _RETIRED_ANOMALY_MODULES),
                        None,
                    )
                elif isinstance(node, ast.ImportFrom):
                    imported = node.module if node.module in _RETIRED_ANOMALY_MODULES else None
                if imported is not None:
                    importers.append(f"{relative}:{imported}")

    assert importers == []
