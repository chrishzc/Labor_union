"""
File: migrate_remove_other_addition.py
Description: 驗證舊 orders.other_addition 全為零後安全移除欄位，保留 floor_fee 為唯一樓層加收欄位。
"""
import sys

def RemoveOtherAdditionMigration(row_count: int, nonzero_other_addition: int) -> dict:
    # ponytail: 依 invariants 限制，若有 nonzero_other_addition 非零則阻擋
    if nonzero_other_addition != 0:
        raise ValueError("Cannot migrate: nonzero other_addition detected.")
    return {"contract_complete": True, "row_count": row_count}

if __name__ == "__main__":
    try:
        sys.path.insert(0, "services")
        import db_service
        conn = db_service.get_connection()
        with conn.cursor() as cursor:
            # check if other_addition column exists
            cursor.execute("SHOW COLUMNS FROM orders LIKE 'other_addition'")
            col = cursor.fetchone()
            if col:
                cursor.execute("SELECT COUNT(*) AS cnt FROM orders WHERE other_addition != 0")
                res = cursor.fetchone()
                if res and res.get("cnt", 0) > 0:
                    print("Error: Nonzero other_addition values detected in database!", file=sys.stderr)
                    sys.exit(1)
                cursor.execute("ALTER TABLE orders DROP COLUMN other_addition")
                conn.commit()
                print("Successfully dropped other_addition column.")
            else:
                print("Column other_addition does not exist, nothing to do.")
    except Exception as e:
        print(f"Migration error: {e}", file=sys.stderr)
        sys.exit(1)
