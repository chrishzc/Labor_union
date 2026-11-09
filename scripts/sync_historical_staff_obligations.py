"""
檔案：scripts/sync_historical_staff_obligations.py
說明：批次或單案同步歷史已完成訂單之月嫂薪資基準應付義務，支援乾跑與實際寫入。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.payroll.historical_baseline_obligation_sync import (
    sync_historical_staff_baseline_obligations,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="同步歷史完成訂單之月嫂薪資應付義務至 staff_obligations"
    )
    parser.add_argument(
        "--case-no",
        type=str,
        default=None,
        help="指定案號（選填，未填時同步所有歷史服務完成與帳務完成訂單）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅預覽檢查，不實際寫入資料庫",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="確認執行實際寫入",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("請指定 --dry-run 進行乾跑預覽，或指定 --apply 執行實際寫入。")
        return 1

    dry_run = args.dry_run

    conn = get_connection()
    try:
        print(f"開始同步歷史月嫂薪資基準義務 (dry_run={dry_run}, case_no={args.case_no or 'ALL'})...")
        result = sync_historical_staff_baseline_obligations(
            conn,
            case_no=args.case_no,
            dry_run=dry_run,
        )
        if not dry_run:
            conn.commit()
            print("寫入已提交。")
        else:
            conn.rollback()
            print("乾跑完成，已回滾。")

        print("=== 執行結果摘要 ===")
        print(f"掃描訂單數: {result['scanned_orders']}")
        print(f"新建義務數: {result['created_count']}")
        print(f"更新義務數: {result['updated_count']}")
        print(f"略過訂單數: {result['skipped_count']}")
        if result["details"]:
            print("\n詳細異動:")
            for item in result["details"]:
                print(f"  - 案號 {item['case_no']}: {item['action']} ({item.get('amount_ntd', '')} NT$, 付款日: {item.get('due_date', '')})")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"執行失敗: {exc}")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
