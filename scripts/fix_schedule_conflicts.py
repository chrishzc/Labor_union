# -*- coding: utf-8 -*-
"""
================================================================================
專案名稱: Lobar_union
檔案名稱: scripts/fix_schedule_conflicts.py
作者: Antigravity
建立日期: 2026-07-06
描述: 月嫂檔期衝突檢測與自動修復工具腳本。
      1. 掃描資料庫中是否存在同一位月嫂同時間承接多筆訂單 (重疊檔期) 的異常。
      2. 提供自動修復策略：保留較高優先級案件，將衝突案件退回待指派狀態 (staff_id = NULL)
         並清理衝突排班，確保行事曆檔期 100% 獨佔且正確。
================================================================================
"""
import sys
import os

# 確保可讀取上層 service 模組
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.db_service import get_connection

# 確保中文輸出編碼正確
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

STATUS_PRIORITY = {
    '服務中': 4,
    '訂單成立': 3,
    '洽談中': 2,
    '訂單完成': 1,
    '訂單取消': 0
}

def detect_schedule_conflicts():
    """
    掃描資料庫中所有同月嫂重疊的訂單區間。
    回傳衝突筆數與詳細衝突清單。
    """
    print("🔍 開始檢測資料庫中的月嫂檔期重疊衝突...")
    conn = get_connection()
    conflicts = []
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT 
                    o1.staff_id, 
                    s.name AS staff_name, 
                    o1.case_no AS order1_case_no, o1.status AS status1, o1.start_date AS s1, o1.end_date AS e1,
                    o2.case_no AS order2_case_no, o2.status AS status2, o2.start_date AS s2, o2.end_date AS e2
                FROM orders o1
                JOIN orders o2 ON o1.staff_id = o2.staff_id AND o1.case_no < o2.case_no
                JOIN staff s ON o1.staff_id = s.id
                WHERE o1.status NOT IN ('訂單取消') 
                  AND o2.status NOT IN ('訂單取消')
                  AND o1.start_date IS NOT NULL AND o1.end_date IS NOT NULL
                  AND o2.start_date IS NOT NULL AND o2.end_date IS NOT NULL
                  AND o1.start_date <= o2.end_date 
                  AND o1.end_date >= o2.start_date
                ORDER BY o1.staff_id, o1.start_date;
            """
            cursor.execute(query)
            conflicts = cursor.fetchall()
            
            if not conflicts:
                print("✅ 檢測通過！目前資料庫中完全沒有月嫂檔期重疊衝突。")
            else:
                print(f"⚠️ 發現 {len(conflicts)} 筆月嫂檔期重疊衝突案件：")
                for idx, c in enumerate(conflicts, 1):
                    print(f"  [{idx}] 月嫂: {c['staff_name']} (ID:{c['staff_id']})")
                    print(f"      - 案件 #{c['order1_case_no']} [{c['status1']}]: {c['s1']} ~ {c['e1']}")
                    print(f"      - 案件 #{c['order2_case_no']} [{c['status2']}]: {c['s2']} ~ {c['e2']}")
            return conflicts
    finally:
        conn.close()

def repair_schedule_conflicts():
    """
    自動修復檔期衝突：
    保留優先級較高 (或建案較早) 的訂單，將次要訂單的 staff_id 解綁 (設為 NULL)
    並刪除其 staff_schedule 檔期細項。
    """
    conflicts = detect_schedule_conflicts()
    if not conflicts:
        print("🎉 無需修復，資料庫檔期結構良好。")
        return

    print("\n🛠️ 開始執行資料庫檔期衝突自動修復程序...")
    conn = get_connection()
    repaired_count = 0
    try:
        with conn.cursor() as cursor:
            for c in conflicts:
                p1 = STATUS_PRIORITY.get(c['status1'], 0)
                p2 = STATUS_PRIORITY.get(c['status2'], 0)

                # 決定保留者與解綁者
                if p1 >= p2:
                    keep_case_no, unbind_case_no = c['order1_case_no'], c['order2_case_no']
                    unbind_status = c['status2']
                else:
                    keep_case_no, unbind_case_no = c['order2_case_no'], c['order1_case_no']
                    unbind_status = c['status1']

                # 解綁次要訂單的 staff_id 並將其狀態降級為 '洽談中' 或標記無月嫂
                cursor.execute("""
                    UPDATE orders 
                    SET staff_id = NULL, status = '洽談中' 
                    WHERE case_no = %s
                """, (unbind_case_no,))

                # 刪除解綁訂單舊有的排班細項
                cursor.execute("DELETE FROM staff_schedule WHERE case_no = %s", (unbind_case_no,))
                repaired_count += 1
                print(f"  - 已自動將衝突案件 #{unbind_case_no} (原狀態: {unbind_status}) 解綁月嫂，保留權重較高之案件 #{keep_case_no}。")

            conn.commit()
            print(f"✅ 修復完成！共解除 {repaired_count} 筆衝突綁定並修復行事曆。")
    except Exception as e:
        conn.rollback()
        print(f"❌ 自動修復出錯: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--repair':
        repair_schedule_conflicts()
    elif len(sys.argv) > 1 and sys.argv[1] == '--test':
        conflicts = detect_schedule_conflicts()
        assert len(conflicts) == 0, f"❌ ADAD 不變量驗證失敗 (INV-SCRIPT-01/INV-SCRIPT-02): 發現 {len(conflicts)} 筆月嫂檔期衝突"
        print("✅ ADAD 不變量驗證成功 (INV-SCRIPT-01/02)！所有月嫂檔期嚴格獨佔且無時間重疊。")
    else:
        detect_schedule_conflicts()
