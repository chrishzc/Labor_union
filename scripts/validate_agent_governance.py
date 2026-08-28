"""
File: validate_agent_governance.py
Description: 驗證 Agent 任務分級、文件路由與 DB gate canonical 連結沒有漂移。
"""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "AGENTS.md": (
        "00_Agent任務分級與交付規範.md",
        "10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門",
    ),
    "document/架構重整/00_Agent任務分級與交付規範.md": (
        "| T0 |",
        "| T1 |",
        "| T2 |",
        "| T3 |",
        "NONCOMPLIANCE",
        "PACKAGE_OMISSION",
        "SPEC_GAP",
    ),
    "document/架構重整/00_開發者與Agent導覽.md": (
        "00_Agent任務分級與交付規範.md",
    ),
    "document/架構重整/00_Phase3-6執行SOP.md": (
        "00_Agent任務分級與交付規範.md",
        "10_Global_保留資料Migration與Cutover_Subsystem.md#9-agent-與開發者-db-變更執行門",
    ),
    "document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md": (
        "## 9. Agent 與開發者 DB 變更執行門",
        "PASS | BLOCKED | NOT_RUN",
        "DB_CHANGE_NOT_READY",
    ),
    "document/架構重整/02_決策與退役執行記錄/README.md": (
        "00_Agent任務分級與交付規範.md",
    ),
    "document/架構重整/03_追蹤清單與證據/README.md": (
        "00_Agent任務分級與交付規範.md",
        "不按 slice 建 tracked receipt",
    ),
}

FORBIDDEN_MARKERS: dict[str, tuple[str, ...]] = {
    "AGENTS.md": (
        "### 3.2 既有開發測試 DB 的受控驗收裁決",
        "1. **Scope gate**",
    ),
    "document/架構重整/00_Phase3-6執行SOP.md": (
        "完整執行AGENTS 3.1七個 gate",
    ),
    "document/架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md": (
        "每個新的 bounded execution slice 都必須先經",
        "未同時具備 current `SPEC_READY`",
    ),
}


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    checked: dict[str, str] = {}
    for relative_path in set(REQUIRED_MARKERS) | set(FORBIDDEN_MARKERS):
        target = root / relative_path
        if not target.is_file():
            errors.append(f"missing_file:{relative_path}")
            continue
        try:
            checked[relative_path] = target.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"invalid_utf8:{relative_path}")

    for relative_path, markers in REQUIRED_MARKERS.items():
        text = checked.get(relative_path)
        if text is None:
            continue
        for marker in markers:
            if marker not in text:
                errors.append(f"missing_marker:{relative_path}:{marker}")

    for relative_path, markers in FORBIDDEN_MARKERS.items():
        text = checked.get(relative_path)
        if text is None:
            continue
        for marker in markers:
            if marker in text:
                errors.append(f"forbidden_marker:{relative_path}:{marker}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Agent governance routing.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    errors = validate(arguments.root.resolve())
    if errors:
        for error in errors:
            print(error)
        return 1
    print("agent_governance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
