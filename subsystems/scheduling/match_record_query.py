"""
================================================================================
檔案名稱: services/match_record_idempotent_service.py
功能說明: 案件與月嫂媒合紀錄建立與查詢等冪防爆服務 (MatchRecordIdempotentService)
================================================================================
"""

from typing import Dict, Any, List
from subsystems.scheduling.ports import unconfigured_connection_factory


get_connection = unconfigured_connection_factory

def get_order_match_records(case_no: str) -> List[Dict[str, Any]]:
    """查詢特定案件之全量媒合紀錄列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT mr.id AS match_id, mr.case_no, mr.staff_id,
                       mr.caregiver_accepted,mr.sent_info_1_at,
                       mr.sent_info_2_at,mr.sent_resume_at,
                       s.name AS staff_name, s.phone AS staff_phone
                FROM matching_records mr
                JOIN staff s ON mr.staff_id = s.id
                WHERE mr.case_no = %s
                ORDER BY mr.id ASC
            """, (case_no,))
            return cursor.fetchall()
    finally:
        conn.close()
