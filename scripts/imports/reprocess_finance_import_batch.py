"""Thin, safe CLI for one historical finance-import batch reprocess."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.finance_import_reprocessing import (
    DEFAULT_SAFETY_LIMIT,
    reprocess_finance_import_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="重處理一個 completed finance import batch；預設 dry-run。",
    )
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="依 dry-run plan fingerprint 正式套用",
    )
    parser.add_argument("--actor", help="apply 必填操作者")
    parser.add_argument(
        "--plan-fingerprint",
        help="apply 必填的 dry-run plan fingerprint",
    )
    parser.add_argument(
        "--safety-limit",
        type=int,
        default=DEFAULT_SAFETY_LIMIT,
    )
    parser.add_argument("--report-path", help="可選 UTF-8 JSON 報告路徑")
    return parser


def _validate_before_database(args: argparse.Namespace) -> None:
    if args.batch_id < 1:
        raise ValueError("batch-id must be a positive integer")
    if args.safety_limit < 1:
        raise ValueError("safety-limit must be a positive integer")
    if args.apply and (not isinstance(args.actor, str) or not args.actor.strip()):
        raise ValueError("--actor is required with --apply")
    if args.apply and (
        not isinstance(args.plan_fingerprint, str)
        or len(args.plan_fingerprint) != 64
    ):
        raise ValueError("--plan-fingerprint is required with --apply")


def _write_report(path: str, result: dict[str, Any]) -> str:
    report_path = Path(path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
        allow_nan=False,
    )
    report_path.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    return str(report_path)


def _console_summary(
    result: dict[str, Any],
    report_path: str | None,
) -> dict[str, Any]:
    classification = result.get("classification_summary")
    if not isinstance(classification, dict):
        classification = {}
    dispatch = result.get("dispatch_summary")
    if not isinstance(dispatch, dict):
        dispatch = {}
    alert = result.get("alert_action")
    if not isinstance(alert, dict):
        alert = {}
    alert_summary = alert.get("summary")
    if not isinstance(alert_summary, dict):
        alert_summary = {}
    return {
        "db_identity": result.get("db_identity"),
        "batch_id": (result.get("batch_manifest") or {}).get("batch_id"),
        "selected": classification.get("selected"),
        "unchanged": classification.get("unchanged"),
        "changed": classification.get("changed"),
        "before_reason_counts": classification.get("before_reason_counts"),
        "after_reason_counts": classification.get("after_reason_counts"),
        "dispatch_attempted": dispatch.get("attempted"),
        "reconciled": dispatch.get("reconciled"),
        "pending": dispatch.get("pending"),
        "remaining_review": alert_summary.get("remaining_count"),
        "alert_action": alert.get("alert_action"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "rows_per_second": result.get("rows_per_second"),
        "plan_fingerprint": result.get("plan_fingerprint"),
        "transaction_outcome": result.get("transaction_outcome"),
        "report_path": report_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_before_database(args)
    result = reprocess_finance_import_batch(
        args.batch_id,
        actor=args.actor,
        dry_run=not args.apply,
        expected_plan_fingerprint=args.plan_fingerprint,
        safety_limit=args.safety_limit,
    )
    report_path = (
        _write_report(args.report_path, result)
        if args.report_path
        else None
    )
    print(
        json.dumps(
            _console_summary(result, report_path),
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
