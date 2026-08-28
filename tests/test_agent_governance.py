"""
File: test_agent_governance.py
Description: 驗證治理檢查器能接受 canonical 路由並拒絕缺漏或舊 blanket gate。
"""

from __future__ import annotations

from pathlib import Path
import shutil

from scripts.validate_agent_governance import (
    FORBIDDEN_MARKERS,
    REQUIRED_MARKERS,
    validate,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _copy_governance_fixture(target_root: Path) -> None:
    for relative_path in set(REQUIRED_MARKERS) | set(FORBIDDEN_MARKERS):
        source = PROJECT_ROOT / relative_path
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_current_governance_routes_are_consistent():
    assert validate(PROJECT_ROOT) == []


def test_missing_task_class_marker_fails_closed(tmp_path):
    _copy_governance_fixture(tmp_path)
    relative_path = "document/架構重整/00_Agent任務分級與交付規範.md"
    target = tmp_path / relative_path
    target.write_text(
        target.read_text(encoding="utf-8").replace("| T2 |", "| TX |", 1),
        encoding="utf-8",
    )

    errors = validate(tmp_path)

    assert any(error.startswith(f"missing_marker:{relative_path}:| T2 |") for error in errors)


def test_retired_per_slice_blanket_gate_fails_closed(tmp_path):
    _copy_governance_fixture(tmp_path)
    relative_path = "document/架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md"
    target = tmp_path / relative_path
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\n每個新的 bounded execution slice 都必須先經 legacy gate\n",
        encoding="utf-8",
    )

    errors = validate(tmp_path)

    assert any(error.startswith(f"forbidden_marker:{relative_path}:") for error in errors)
