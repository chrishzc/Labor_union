"""
File: ensure_nas_procedures.py
Description: 確保目前連線 MySQL 資料庫具備所有宣告的受控 NAS 預存程序。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.nas_mutations import PROCEDURES, ensure_nas_procedures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="強制重新建立所有預存程序")
    parser.add_argument("--dry-run", action="store_true", help="僅檢查缺少程序，不執行變更")
    args = parser.parse_args(argv)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db_name")
            row = cursor.fetchone()
            db_name = row.get("db_name") if isinstance(row, dict) else row[0]
            cursor.execute(
                "SELECT routine_name AS name FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE'"
            )
            existing = {
                r.get("name") or r.get("NAME") or r.get("routine_name") or r.get("ROUTINE_NAME")
                for r in cursor.fetchall()
                if isinstance(r, dict)
            }
        missing = sorted(set(PROCEDURES.keys()) - existing)
        if args.dry_run:
            result = {
                "status": "planned",
                "database": db_name,
                "missing_count": len(missing),
                "missing_procedures": missing,
                "total_procedures": len(PROCEDURES),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        modified = ensure_nas_procedures(conn, force=args.force)
        result = {
            "status": "passed",
            "database": db_name,
            "modified_count": len(modified),
            "modified_procedures": modified,
            "total_procedures": len(PROCEDURES),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
