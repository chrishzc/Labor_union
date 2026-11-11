"""
File: test_spec_hygiene_validator.py
Description: 驗證規格書純淨度檢查腳本能接受合規規格並攔截各類舊規與進度殘留。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_spec_hygiene import main, validate_specs


VALID_SPEC = """# Orders Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Orders
- 關聯引用：見 [Global 共同契約](00_Global.md)

## 2. 核心不變量

- 歷史訂單與一般訂單皆必須保留不可變金額事件，不得直接覆寫歷史帳務事實。
- 已取消與 superseded work 不重新開啟，狀態轉移由明確命令觸發。
- 驗收規則允許於契約中定義 `blocked` 或 `not_run` 等結果枚舉值。

## 3. 範例程式碼區塊不受誤判

```markdown
> 2026-11-05 範例程式碼區塊不應觸發誤判
已取代 / Streamlit / 尚未實作
```
"""


def _write_spec(root: Path, rel_path: str, content: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_clean_spec_passes_strict_validation(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    _write_spec(spec_dir, "00_Global.md", "# Global\n\n## 1. 契約\n\n- 正常內容。\n")
    _write_spec(spec_dir, "01_Orders.md", VALID_SPEC)

    files_checked, violations = validate_specs(spec_dir, tmp_path)

    assert files_checked == 2
    assert violations == []
    assert main(["--root", str(tmp_path), "--path", "specs"]) == 0


def test_rejects_top_patch_and_chronological_narration(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    _write_spec(
        spec_dir,
        "22_Finance.md",
        "# Finance\n\n"
        "> 2026-11-05 最新人工裁決：舊機制停止。\n\n"
        "## 1. 規則（2026-11-03 核准）\n\n"
        "依2026-11-06最新裁決處理。\n",
    )

    _, violations = validate_specs(spec_dir, tmp_path)
    rules = {v.rule for v in violations}

    assert "top_patch_blockquote" in rules
    assert "dated_heading" in rules
    assert "chronological_patch" in rules
    assert "legacy_residue" in rules


def test_rejects_legacy_retired_tech_and_execution_status(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    _write_spec(
        spec_dir,
        "16_Refund.md",
        "# Refund\n\n## 1. 流程\n\n"
        "- 本條目已取代，僅供歷史追溯；此裁決 supersede 前述規則。\n"
        "- 沿用Streamlit畫面與 ui/app.py 舊路徑。\n"
        "- 目前尚未實作，本輪僅更新規格，限定測試28 passed，其餘 NOT_RUN。\n",
    )

    _, violations = validate_specs(spec_dir, tmp_path)
    rules = {v.rule for v in violations}

    assert "legacy_residue" in rules
    assert "retired_tech_residue" in rules
    assert "execution_status_residue" in rules


def test_rejects_non_spec_documents_and_length_limit(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    long_body = "\n".join(f"- 條款 {i}" for i in range(25))
    _write_spec(
        spec_dir,
        "15A_SourceReview_Closeout裁決.md",
        f"# Closeout\n\n## 1. 狀態\n\n本文件不是新的業務規格。\n{long_body}\n",
    )

    _, violations = validate_specs(spec_dir, tmp_path, max_lines=10)
    rules = {v.rule for v in violations}

    assert "non_spec_document" in rules
    assert "max_lines_exceeded" in rules


def test_rejects_broken_and_non_portable_links(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    _write_spec(
        spec_dir,
        "04_Client.md",
        "# Client\n\n## 1. 引用\n\n"
        "- 斷裂：[缺檔](missing_target.md#anchor)\n"
        "- 本機：[暫存](/private/tmp/shot.png)\n"
        "- 磁碟：[絕對](file:///d:/project/a.md)\n",
    )

    _, violations = validate_specs(spec_dir, tmp_path)
    rules = {v.rule for v in violations}

    assert "broken_markdown_link" in rules
    assert "non_portable_link" in rules


def test_report_mode_and_missing_target_behavior(tmp_path: Path, capsys) -> None:
    assert main(["--root", str(tmp_path), "--path", "nonexistent", "--mode", "report"]) == 1
    _ = capsys.readouterr()

    spec_dir = tmp_path / "specs"
    _write_spec(spec_dir, "bad.md", "# Bad\n\n## 1. 舊\n\n- 此處已取代。\n")

    exit_code = main(["--root", str(tmp_path), "--path", "specs", "--mode", "report", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "report_with_issues"
    assert payload["violations_count"] >= 1
    assert payload["summary_by_rule"]["legacy_residue"] >= 1
