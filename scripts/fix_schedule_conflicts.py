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
import sys
import os

# 確保可讀取上層 service 模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.mysql.mysql_adapter import get_connection

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

_REPAIR_RETIRED_CODE = "legacy_schedule_conflict_repair_retired"

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
    if len(sys.argv) > 1 and sys.argv[1] == '--repair':
        print(_REPAIR_RETIRED_CODE, file=sys.stderr)
        raise SystemExit(2)
    elif len(sys.argv) > 1 and sys.argv[1] == '--test':
        conflicts = detect_schedule_conflicts()
        if conflicts:
            raise SystemExit(1)
    else:
        detect_schedule_conflicts()
