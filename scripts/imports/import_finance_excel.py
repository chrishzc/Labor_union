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

from scripts.imports.finance_statement_normalizer import normalize_workbook
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import.ingestion import ingest_finance_workbook


_TEST_ACTOR = ActorContext("finance-import-cli-test")
_TEST_IDEMPOTENCY_PREFIX = "finance-import-cli-test:"


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


def _test_idempotency_key(excel_path: Path) -> IdempotencyKey:
    digest = hashlib.sha256(excel_path.read_bytes()).hexdigest()
    return IdempotencyKey(f"{_TEST_IDEMPOTENCY_PREFIX}{digest}")


def _dry_run_manifest(excel_path: Path) -> dict[str, Any]:
    normalized = normalize_workbook(str(excel_path))
    return {
        "mode": "dry_run", "transaction_outcome": "not_written",
        "source_path": str(excel_path),
        "format_manifest": {"format_id": normalized["format_id"], "normalized_row_count": len(normalized["normalized_rows"])},
        "batch_id": None, "inserted_rows": 0, "skipped_existing": 0,
        "reconciled_counts": {}, "row_results": [], "alert_action": {},
    }


def _ingestion_manifest(excel_path: Path) -> dict[str, Any]:
    receipt = ingest_finance_workbook(
        str(excel_path), _test_idempotency_key(excel_path), _TEST_ACTOR
    )
    return {
        "mode": "test_ingestion", "transaction_outcome": "committed",
        "source_path": str(excel_path), "format_manifest": {},
        "batch_id": receipt.batch_identity,
        "inserted_rows": receipt.canonical_created_count,
        "skipped_existing": receipt.duplicate_occurrence_count,
        "reconciled_counts": {}, "row_results": [], "alert_action": {},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="匯入銀行對帳 Excel；預設以測試期 typed adapter 寫入銀行根事實，--dry-run 僅驗證格式、不寫入。",
    )
    parser.add_argument("--excel-path", required=True, help="銀行 Excel 完整路徑")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅驗證 Excel 格式與列數，不寫入資料庫",
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
    resolved_path = excel_path.resolve()
    manifest = _dry_run_manifest(resolved_path) if args.dry_run else _ingestion_manifest(resolved_path)
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
