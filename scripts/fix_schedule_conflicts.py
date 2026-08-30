# -*- coding: utf-8 -*-
"""
================================================================================
專案名稱: Lobar_union
檔案名稱: scripts/fix_schedule_conflicts.py
作者: Antigravity
建立日期: 2026-07-06
描述: canonical Scheduling effective occupancy 的唯讀衝突報告。
      舊 --repair 會直接改 Orders 並刪除排班，已永久停用；修正必須由異常中心導向
      Assignment Plan Preview／Apply。
================================================================================
"""
import argparse
import sys
import os
import re

# 確保可讀取上層 service 模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.mysql_adapter import DB_CONFIG

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

_REPAIR_RETIRED_CODE = "legacy_schedule_conflict_repair_retired"

def _require_target_database(target: str) -> None:
    if not target or target != str(DB_CONFIG.get("database") or ""):
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if target == "union_db" or not re.fullmatch(r"lu_test_[a-z0-9_]+", target):
        raise ValueError("target database must be an explicitly named lu_test_* database")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("production environment is not permitted for this read-only CLI")


def _check_connected_identity(target: str) -> None:
    if not os.getenv("DB_HOST", "").strip():
        raise RuntimeError("DB_HOST must be configured explicitly")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN "
                "('scheduling_effective_occupancy','scheduling_generations') "
                "ORDER BY TABLE_NAME"
            )
            objects = cursor.fetchall()
        if not identity or identity.get("database_name") != target:
            raise RuntimeError("connected database does not match --target-database")
        if not str(identity.get("server") or "").strip():
            raise RuntimeError("connected MySQL server identity is unavailable")
        names = [row.get("TABLE_NAME") for row in objects]
        if names != ["scheduling_effective_occupancy", "scheduling_generations"]:
            raise RuntimeError("canonical Scheduling conflict schema is incomplete")
    finally:
        conn.close()


def detect_schedule_conflicts():
    """Read duplicate canonical effective occupancy without modifying facts."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_CONFLICT_REPORT_SQL)
            conflicts = cursor.fetchall()
        _print_conflict_report(conflicts)
        return conflicts
    finally:
        conn.close()


def repair_schedule_conflicts():
    """Reject the retired destructive writer before opening a connection."""
    raise RuntimeError(_REPAIR_RETIRED_CODE)


def _print_conflict_report(conflicts):
    if not conflicts:
        print("目前 canonical effective occupancy 沒有重複檔期。")
        return
    print(f"發現 {len(conflicts)} 組重複檔期，請至異常中心處理：")
    for conflict in conflicts:
        print(
            f"staff #{conflict['staff_id']} "
            f"{conflict['occupancy_date']}：{conflict['case_numbers']}"
        )


_CONFLICT_REPORT_SQL = """
SELECT occupancy.staff_id,occupancy.occupancy_date,
       GROUP_CONCAT(DISTINCT generations.case_no
                    ORDER BY generations.case_no) AS case_numbers,
       COUNT(*) AS occupancy_count
FROM scheduling_effective_occupancy occupancy
JOIN scheduling_generations generations
  ON generations.id=occupancy.generation_id
WHERE occupancy.occupancy_type='assignment_interval'
GROUP BY occupancy.staff_id,occupancy.occupancy_date
HAVING COUNT(*)>1
ORDER BY occupancy.staff_id,occupancy.occupancy_date
"""

if __name__ == "__main__":
    if "--repair" in sys.argv[1:]:
        print(_REPAIR_RETIRED_CODE, file=sys.stderr)
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    try:
        _require_target_database(args.target_database)
        _check_connected_identity(args.target_database)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    conflicts = detect_schedule_conflicts()
    if args.test and conflicts:
        raise SystemExit(1)
