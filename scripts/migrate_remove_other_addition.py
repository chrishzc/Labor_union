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
    raise SystemExit(
        "migrate_remove_other_addition 已退役；請使用受治理的 preserve-data migration runner。"
    )
