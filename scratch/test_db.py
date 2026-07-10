# -*- coding: utf-8 -*-
import os
import sys
import pymysql

# 確保可以載入 admin.utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from admin.utils import get_db_connection

def inspect_db():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 檢查 clients
            cursor.execute("SELECT id, name, phone, line_user_id FROM clients LIMIT 5")
            clients = cursor.fetchall()
            print("=== Clients in DB ===")
            for c in clients:
                print(f"ID: {c['id']}, Name: {c['name']}, Phone: {c['phone']}, Line ID: {c['line_user_id']}")
            
            # 如果沒有客戶，我們手動插入兩筆張三以測試同名同姓防錯機制
            if not clients:
                print("\nNo clients found. Creating mock clients...")
                cursor.execute("""
                    INSERT INTO clients (name, phone, case_no) 
                    VALUES ('張三', '0912345678', '115000001'), 
                           ('張三', '0987654321', '115000002')
                """)
                # 取得新增客戶的 ID
                cursor.execute("SELECT id, name, phone FROM clients WHERE name='張三'")
                mock_clients = cursor.fetchall()
                print("Mock clients created:")
                for mc in mock_clients:
                    print(f"ID: {mc['id']}, Name: {mc['name']}, Phone: {mc['phone']}")
                    
                    # 順便幫第一位建立訂單
                    cursor.execute("""
                        INSERT INTO orders (client_id, status)
                        VALUES (%s, '洽談中')
                    """, (mc['id'],))
                conn.commit()
                print("Mock orders created for mock clients.")
            else:
                # 確保有一筆「張三」供測試
                cursor.execute("SELECT id FROM clients WHERE name='張三' AND REPLACE(REPLACE(phone, '-', ''), ' ', '')='0912345678'")
                if not cursor.fetchone():
                    print("\nCreating specific test client '張三' (0912345678)...")
                    cursor.execute("""
                        INSERT INTO clients (name, phone, case_no)
                        VALUES ('張三', '0912345678', '115000099')
                    """)
                    client_id = conn.insert_id()
                    cursor.execute("""
                        INSERT INTO orders (client_id, status)
                        VALUES (%s, '洽談中')
                    """, (client_id,))
                    conn.commit()
                    print(f"Test client '張三' and order created (ID: {client_id})")
                    
    except Exception as e:
        print(f"Error inspecting DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_db()
