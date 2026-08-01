"""Thin CLI adapter for the finance workbook import application service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.finance_import_application import (
    _order_for_snapshot,
    allocate_receipt,
    build_snapshot_plan,
    import_finance_workbook,
)


def _write_report(path: str, manifest: dict[str, Any]) -> str:
    report_path = Path(path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        default=str,
        allow_nan=False,
    )
    report_path.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    return str(report_path)


def _console_summary(
    manifest: dict[str, Any],
    report_path: str | None,
) -> dict[str, Any]:
    format_manifest = manifest.get("format_manifest")
    if not isinstance(format_manifest, dict):
        format_manifest = {}
    alert = manifest.get("alert_action")
    if not isinstance(alert, dict):
        alert = {}
    return {
        "mode": manifest.get("mode"),
        "transaction_outcome": manifest.get("transaction_outcome"),
        "source_path": manifest.get("source_path"),
        "format_id": format_manifest.get("format_id"),
        "normalized_row_count": format_manifest.get("normalized_row_count"),
        "batch_id": manifest.get("batch_id"),
        "inserted_rows": manifest.get("inserted_rows"),
        "skipped_existing": manifest.get("skipped_existing"),
        "reconciled_counts": manifest.get("reconciled_counts"),
        "pending_count": sum(
            row.get("dispatch_result") == "pending"
            for row in (manifest.get("row_results") or [])
            if isinstance(row, dict)
        ),
        "import_review_alert_action": alert.get("alert_action"),
        "report_path": report_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="匯入銀行對帳 Excel；預設正式寫入，--dry-run 完整執行後回滾。",
    )
    parser.add_argument("--excel-path", required=True, help="銀行 Excel 完整路徑")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="完整執行匯入流程後 rollback",
    )
    parser.add_argument(
        "--report-path",
        help="可選：將完整 UTF-8 JSON manifest 寫入此路徑",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    excel_path = Path(args.excel_path).expanduser()
    if not excel_path.is_file():
        raise FileNotFoundError(f"找不到帳務 Excel：{args.excel_path}")
    manifest = import_finance_workbook(
        str(excel_path.resolve()),
        dry_run=bool(args.dry_run),
    )
    report_path = (
        _write_report(args.report_path, manifest)
        if args.report_path
        else None
    )
    print(
        json.dumps(
            _console_summary(manifest, report_path),
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
