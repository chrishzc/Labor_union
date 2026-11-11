"""
File: validate_spec_hygiene.py
Description: 驗證規格書是否符合純淨現行契約、行數上限與無舊規殘留規範。
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Sequence


DEFAULT_TARGET = Path("document/架構重整/01_規格基線")
DEFAULT_MAX_LINES = 600
TOP_PATCH_SCAN_LINES = 35

_TOP_PATCH_RE = re.compile(
    r"^>\s*(?:(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)|.*(?:最新.*裁決|人工裁決|人工授權|補充裁決|規格同步))"
)
_DATED_HEADING_RE = re.compile(r"^#{1,6}\s+.*(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)")
_NON_SPEC_FILENAME_RE = re.compile(r"(?:Closeout|盤點|驗收紀錄|測試手冊)", re.IGNORECASE)
_NON_SPEC_PROSE_RE = re.compile(r"不是新的業務規格|人工測試手冊")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_PORTABLE_URL_PREFIXES = ("http://", "https://", "mailto:", "#")
_NON_PORTABLE_LINK_RE = re.compile(
    r"^(?:file://|[A-Za-z]:[/\\]|/(?:private|tmp|Users|home|var)/)",
    re.IGNORECASE,
)

_PROSE_PATTERN_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "chronological_patch",
        re.compile(
            r"(?<!\d)20\d{2}-\d{2}-\d{2}(?!\d)\s*(?:最新)?(?:人工)?(?:明確)?(?:裁決|授權|核准|修訂|補充|更正|實作)"
        ),
        "內文不得保留編年史裁決敘事，應直接改寫為現行規則。",
    ),
    (
        "legacy_residue",
        re.compile(
            r"已取代|僅供歷史追溯|歷史追溯|舊規則|舊機制|舊流程|舊路徑|舊敘述|舊版本|舊版|"
            r"較早文字|較舊文字|歷史來源|歷史實作包|(?<![A-Za-z])supersedes?(?![A-Za-z])",
            re.IGNORECASE,
        ),
        "內文殘留已廢止或歷史對照用語。",
    ),
    (
        "retired_tech_residue",
        re.compile(r"(?<![A-Za-z])Streamlit(?![A-Za-z])|ui/app\.py|\.streamlit/", re.IGNORECASE),
        "內文殘留已退役前端技術名詞（Streamlit）。",
    ),
    (
        "execution_status_residue",
        re.compile(
            r"尚未實作|未實作|待實作|待施工|尚未施工|本輪僅|僅更新規格|僅修規格|只修規格|"
            r"只更新規格|未修改程式|只改文件|測試通過|\d+\s*(?:項|個)[^\n]{0,12}(?:通過|passed)|"
            r"(?<!\d)\d+\s+(?i:passed)(?![A-Za-z])|(?<![A-Za-z])NOT_RUN(?![A-Za-z])|"
            r"(?<![A-Za-z])Living Work Package(?![A-Za-z])",
        ),
        "規格書內不得混入暫態施工進度或測試數字。",
    ),
)


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    rule: str
    message: str
    snippet: str = ""


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_markdown_files(target: Path, excludes: set[str]) -> list[Path]:
    if target.is_file():
        return [target]
    files: list[Path] = []
    for path in sorted(target.rglob("*.md")):
        if "assets" in path.parts:
            continue
        if path.name in excludes or path.name == "README.md":
            continue
        files.append(path)
    return files


def _validate_structure(
    lines: list[str], display_path: str, max_lines: int
) -> list[Violation]:
    violations: list[Violation] = []
    if len(lines) > max_lines:
        violations.append(
            Violation(
                file=display_path,
                line=len(lines),
                rule="max_lines_exceeded",
                message=f"單檔行數 {len(lines)} 超過上限 {max_lines} 行，應依邊界拆片。",
            )
        )

    non_empty = [(idx, line) for idx, line in enumerate(lines, 1) if line.strip()]
    if not non_empty:
        violations.append(
            Violation(
                file=display_path,
                line=1,
                rule="missing_h1_title",
                message="規格檔案不可為空，首行必須為單一 H1 標題。",
            )
        )
        return violations

    first_line_no, first_line = non_empty[0]
    if not re.match(r"^#\s+\S+", first_line):
        violations.append(
            Violation(
                file=display_path,
                line=first_line_no,
                rule="missing_h1_title",
                message="首個非空白行必須為 `# <正式名稱>` H1 標題。",
                snippet=first_line.strip()[:100],
            )
        )
    return violations


def _validate_links(
    line: str, line_no: int, md_file: Path, display_path: str
) -> list[Violation]:
    violations: list[Violation] = []
    cleaned = _INLINE_CODE_RE.sub("", line)
    for match in _MARKDOWN_LINK_RE.finditer(cleaned):
        raw_expr = match.group(1).strip()
        if raw_expr.startswith("<") and ">" in raw_expr:
            raw_target = raw_expr[1 : raw_expr.index(">")].strip()
        else:
            raw_target = raw_expr.split(maxsplit=1)[0]
        if not raw_target or raw_target.startswith(_PORTABLE_URL_PREFIXES):
            continue
        if _NON_PORTABLE_LINK_RE.search(raw_target):
            violations.append(
                Violation(
                    file=display_path,
                    line=line_no,
                    rule="non_portable_link",
                    message="連結不得使用不可攜的絕對本機路徑或 file:// URI。",
                    snippet=raw_target[:100],
                )
            )
            continue
        rel_part = raw_target.split("#", 1)[0].split("?", 1)[0]
        if not rel_part:
            continue
        resolved = (md_file.parent / rel_part).resolve()
        if not resolved.exists():
            violations.append(
                Violation(
                    file=display_path,
                    line=line_no,
                    rule="broken_markdown_link",
                    message=f"相對連結目標不存在：{rel_part}",
                    snippet=raw_target[:100],
                )
            )
    return violations


def validate_file(
    md_file: Path,
    root: Path,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[Violation]:
    display_path = _relative_display(md_file, root)
    try:
        text = md_file.read_text(encoding="utf-8")
    except UnicodeError:
        return [
            Violation(
                file=display_path,
                line=0,
                rule="invalid_utf8",
                message="規格檔案必須使用嚴格 UTF-8 編碼。",
            )
        ]

    lines = text.splitlines()
    violations = _validate_structure(lines, display_path, max_lines)

    if _NON_SPEC_FILENAME_RE.search(md_file.name):
        violations.append(
            Violation(
                file=display_path,
                line=1,
                rule="non_spec_document",
                message="檔名顯示屬於結案備忘、盤點或測試手冊，不得置於現行規格基線目錄。",
            )
        )

    h1_count = 0
    h2_count = 0
    fence_char: str | None = None

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence_char is None:
                fence_char = marker
            elif fence_char == marker:
                fence_char = None
            continue
        if fence_char is not None:
            continue

        if re.match(r"^#\s+\S+", line):
            h1_count += 1
            if h1_count > 1:
                violations.append(
                    Violation(
                        file=display_path,
                        line=idx,
                        rule="duplicate_h1_title",
                        message="每份規格書只允許單一 H1 主標題。",
                        snippet=stripped[:100],
                    )
                )

        if re.match(r"^##\s+\S+", line):
            h2_count += 1

        if _NON_SPEC_PROSE_RE.search(line):
            violations.append(
                Violation(
                    file=display_path,
                    line=idx,
                    rule="non_spec_document",
                    message="檔案內容宣告非業務規格或屬人工測試手冊。",
                    snippet=stripped[:100],
                )
            )

        line_flagged_as_patch = False
        if idx <= TOP_PATCH_SCAN_LINES and _TOP_PATCH_RE.search(line):
            violations.append(
                Violation(
                    file=display_path,
                    line=idx,
                    rule="top_patch_blockquote",
                    message="檔案開頭禁止堆疊日期裁決或同步引言補丁，應原地改寫正文。",
                    snippet=stripped[:100],
                )
            )
            line_flagged_as_patch = True

        if _DATED_HEADING_RE.search(line):
            violations.append(
                Violation(
                    file=display_path,
                    line=idx,
                    rule="dated_heading",
                    message="章節標題不得嵌入日期標籤，應改為純主題標題。",
                    snippet=stripped[:100],
                )
            )
            line_flagged_as_patch = True

        for rule_name, pattern, message in _PROSE_PATTERN_RULES:
            if rule_name == "chronological_patch" and line_flagged_as_patch:
                continue
            if pattern.search(line):
                violations.append(
                    Violation(
                        file=display_path,
                        line=idx,
                        rule=rule_name,
                        message=message,
                        snippet=stripped[:100],
                    )
                )

        violations.extend(_validate_links(line, idx, md_file, display_path))

    if lines and h2_count == 0:
        violations.append(
            Violation(
                file=display_path,
                line=1,
                rule="missing_section",
                message="規格書至少須包含一個 `## ` 二級章節。",
            )
        )

    return violations


def validate_specs(
    target: Path,
    root: Path,
    *,
    max_lines: int = DEFAULT_MAX_LINES,
    excludes: Sequence[str] = (),
) -> tuple[int, list[Violation]]:
    resolved_target = target if target.is_absolute() else (root / target)
    display_target = _relative_display(resolved_target, root)
    if not resolved_target.exists():
        return 0, [
            Violation(
                file=display_target,
                line=0,
                rule="missing_target",
                message=f"規格目標路徑不存在：{display_target}",
            )
        ]

    md_files = _iter_markdown_files(resolved_target, set(excludes))
    if not md_files:
        return 0, [
            Violation(
                file=display_target,
                line=0,
                rule="empty_target",
                message=f"目標路徑內未找到任何規格 Markdown 檔案：{display_target}",
            )
        ]

    all_violations: list[Violation] = []
    for md_file in md_files:
        all_violations.extend(validate_file(md_file, root, max_lines=max_lines))
    return len(md_files), all_violations


def _format_text_report(
    target_display: str,
    mode: str,
    files_checked: int,
    violations: list[Violation],
) -> str:
    if not violations:
        return f"spec_hygiene: PASS ({files_checked} files checked in {target_display})"

    counts = Counter(v.rule for v in violations)
    by_file: dict[str, list[Violation]] = {}
    for violation in violations:
        by_file.setdefault(violation.file, []).append(violation)

    lines: list[str] = [
        f"spec_hygiene: {'FAIL' if mode == 'strict' else 'REPORT'} "
        f"({len(violations)} violations across {len(by_file)}/{files_checked} files in {target_display})",
        "summary_by_rule: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    for file_path, items in by_file.items():
        lines.append(f"\n[{file_path}] ({len(items)} issues)")
        for item in items:
            snippet_part = f" | {item.snippet}" if item.snippet else ""
            lines.append(f"  L{item.line} [{item.rule}] {item.message}{snippet_part}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate specification documents against the Living Current Truth hygiene standard."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root directory.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_TARGET,
        help="Target specification directory or markdown file (relative to --root or absolute).",
    )
    parser.add_argument(
        "--mode",
        choices=("strict", "report"),
        default="strict",
        help="strict exits 1 on violations; report prints summary and exits 0 unless target is missing.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help="Maximum allowed lines per specification file (default: 600).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Filename to exclude from directory scan (can be repeated).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    files_checked, violations = validate_specs(
        args.path,
        root,
        max_lines=args.max_lines,
        excludes=args.exclude,
    )
    target_resolved = args.path if args.path.is_absolute() else (root / args.path)
    target_display = _relative_display(target_resolved, root)

    has_target_error = any(v.rule in {"missing_target", "empty_target"} for v in violations)
    failed = bool(violations) if args.mode == "strict" else has_target_error

    if args.json:
        payload = {
            "status": "failed" if failed else ("report_with_issues" if violations else "passed"),
            "mode": args.mode,
            "target": target_display,
            "files_checked": files_checked,
            "violations_count": len(violations),
            "summary_by_rule": dict(sorted(Counter(v.rule for v in violations).items())),
            "violations": [asdict(v) for v in violations],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_text_report(target_display, args.mode, files_checked, violations))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
