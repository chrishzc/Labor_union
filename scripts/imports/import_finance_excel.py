"""Thin CLI adapter for the finance workbook import application service."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.finance_import.application import (
    _order_for_snapshot,
    allocate_receipt,
    build_snapshot_plan,
    import_finance_workbook,
)
from subsystems.finance_import.ingestion import ingest_finance_workbook
from shared_kernel.identities import ActorContext, IdempotencyKey


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
        "formal_dispatch": manifest.get("formal_dispatch"),
    }


# CLI flags stay together so Preview remains the visible default contract.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "銀行對帳 Excel 預設保存不可變銀行根事實與分類；"
            "正式帳務仍須由人員 Preview 後 Apply。"
        ),
    )
    parser.add_argument("--excel-path", required=True, help="銀行 Excel 完整路徑")
    execution_mode = parser.add_mutually_exclusive_group()
    execution_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="相容診斷：執行舊格式完整檢查後 rollback，不保存根事實",
    )
    execution_mode.add_argument(
        "--apply",
        action="store_true",
        help="相容參數；預設即保存根事實，正式帳務仍須另行 Preview/Apply",
    )
    parser.add_argument(
        "--actor",
        default="finance-import-cli",
        help="流水入庫操作者識別",
    )
    parser.add_argument(
        "--idempotency-key",
        help="可選；省略時依檔案內容產生穩定冪等鍵",
    )
    parser.add_argument(
        "--report-path",
        help="可選：將完整 UTF-8 JSON manifest 寫入此路徑",
    )
    return parser


# The thin adapter keeps one linear parse-call-render boundary.
def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    excel_path = Path(args.excel_path).expanduser()
    if not excel_path.is_file():
        raise FileNotFoundError(f"找不到帳務 Excel：{args.excel_path}")
    source_path = excel_path.resolve()
    manifest = (
        import_finance_workbook(str(source_path), dry_run=True)
        if args.dry_run
        else _ingest_manifest(source_path, args)
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


def _ingest_manifest(source_path, args):
    idempotency_key = args.idempotency_key or _content_key(source_path)
    receipt = ingest_finance_workbook(
        str(source_path),
        IdempotencyKey(idempotency_key),
        ActorContext(str(args.actor).strip()),
    )
    return {
        "mode": "apply",
        "transaction_outcome": "committed",
        "source_path": str(source_path),
        "batch_id": receipt.batch_identity,
        "inserted_rows": receipt.canonical_created_count,
        "skipped_existing": receipt.duplicate_occurrence_count,
        "formal_dispatch": "preview_required",
    }


def _content_key(source_path):
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return f"finance-import-cli:{digest}"


if __name__ == "__main__":
    raise SystemExit(main())
