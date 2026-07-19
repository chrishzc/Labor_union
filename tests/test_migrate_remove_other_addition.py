"""
File: test_migrate_remove_other_addition.py
Description: 測試 scripts/migrate_remove_other_addition.py 遷移指令，包含可還原的資料庫整合測試。
"""
import sys
import subprocess
import pytest
sys.path.insert(0, ".")
sys.path.insert(0, "services")
import db_service
from scripts.migrate_remove_other_addition import RemoveOtherAdditionMigration

def test_migration_pure_function_logic():
    # 測試純函式邏輯與 Invariants
    res = RemoveOtherAdditionMigration(50, 0)
    assert res["contract_complete"] is True
    assert res["row_count"] == 50

    with pytest.raises(ValueError, match="nonzero other_addition"):
        RemoveOtherAdditionMigration(50, 100)

def test_database_migration_integration():
    # 整合測試：模擬真實資料庫遷移，測試後能自動還原 (Self-cleaning / Rollbackable)
    conn = db_service.get_connection()
    with conn.cursor() as cursor:
        # 1. 備份原有狀態，確保測試後能恢復
        cursor.execute("SHOW COLUMNS FROM orders LIKE 'other_addition'")
        had_column = bool(cursor.fetchone())
        
        original_values = {}
        if had_column:
            cursor.execute("SELECT case_no, other_addition FROM orders")
            for r in cursor.fetchall():
                original_values[r["case_no"]] = r["other_addition"]
            # 清理非零值以方便測試
            cursor.execute("UPDATE orders SET other_addition = 0")
            conn.commit()

        try:
            # 2. 測試：資料庫中沒有 column 時，直接執行應成功
            if had_column:
                cursor.execute("ALTER TABLE orders DROP COLUMN other_addition")
                conn.commit()

            # 執行 scripts/migrate_remove_other_addition.py，應成功退出 0
            res_no_col = subprocess.run(
                [sys.executable, "scripts/migrate_remove_other_addition.py"],
                capture_output=True,
                text=True
            )
            assert res_no_col.returncode == 0
            assert "does not exist" in res_no_col.stdout or "dropped" in res_no_col.stdout

            # 3. 測試：增加 column，值全為 0，執行應成功並移除 column
            cursor.execute("ALTER TABLE orders ADD COLUMN other_addition DECIMAL(10,2) DEFAULT 0.00")
            conn.commit()
            
            res_zeros = subprocess.run(
                [sys.executable, "scripts/migrate_remove_other_addition.py"],
                capture_output=True,
                text=True
            )
            assert res_zeros.returncode == 0
            assert "Successfully dropped" in res_zeros.stdout
            
            # 確認欄位真的被移除了
            cursor.execute("SHOW COLUMNS FROM orders LIKE 'other_addition'")
            assert cursor.fetchone() is None

            # 4. 測試：增加 column，且含有非零值，執行應失敗並以非零結束碼退出
            cursor.execute("SELECT case_no FROM orders LIMIT 1")
            row = cursor.fetchone()
            if row:
                case_no = row["case_no"]
                cursor.execute("ALTER TABLE orders ADD COLUMN other_addition DECIMAL(10,2) DEFAULT 0.00")
                cursor.execute(f"UPDATE orders SET other_addition = 100.00 WHERE case_no = '{case_no}'")
                conn.commit()

                res_nonzero = subprocess.run(
                    [sys.executable, "scripts/migrate_remove_other_addition.py"],
                    capture_output=True,
                    text=True
                )
                assert res_nonzero.returncode != 0
                assert "Nonzero other_addition" in res_nonzero.stderr

        finally:
            # 5. 還原資料庫結構與資料
            cursor.execute("SHOW COLUMNS FROM orders LIKE 'other_addition'")
            has_col_now = bool(cursor.fetchone())
            
            if had_column:
                if not has_col_now:
                    cursor.execute("ALTER TABLE orders ADD COLUMN other_addition DECIMAL(10,2) DEFAULT 0.00")
                    conn.commit()
                for c_no, val in original_values.items():
                    cursor.execute("UPDATE orders SET other_addition = %s WHERE case_no = %s", (val, c_no))
                conn.commit()
            else:
                if has_col_now:
                    cursor.execute("ALTER TABLE orders DROP COLUMN other_addition")
                    conn.commit()
