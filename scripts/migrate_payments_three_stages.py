"""將 payments 安全遷移為訂金、第一期、第二期完整應收／實收結構。"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.db_service import get_connection


NEW_COLUMNS = {
    "deposit_receivable": "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '訂金應收金額' AFTER client_name",
    "deposit_due_date": "DATE NULL COMMENT '訂金應收日期' AFTER deposit_received",
    "first_payment_receivable": "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第一期應收金額' AFTER deposit_received_at",
    "first_payment_due_date": "DATE NULL COMMENT '第一期應收日期' AFTER first_payment_received",
    "second_payment_receivable": "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第二期應收金額' AFTER first_payment_received_at",
    "second_payment_due_date": "DATE NULL COMMENT '第二期應收日期' AFTER second_payment_received",
    "amount_received": "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '實收總額' AFTER amount_receivable",
}


ORDERED_COLUMNS = [
    ("deposit_receivable", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '訂金應收金額' AFTER client_name"),
    ("deposit_received", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '訂金實收金額' AFTER deposit_receivable"),
    ("deposit_due_date", "DATE NULL COMMENT '訂金應收日期' AFTER deposit_received"),
    ("deposit_received_at", "DATE NULL COMMENT '訂金實收日期' AFTER deposit_due_date"),
    ("first_payment_receivable", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第一期應收金額' AFTER deposit_received_at"),
    ("first_payment_received", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第一期實收金額' AFTER first_payment_receivable"),
    ("first_payment_due_date", "DATE NULL COMMENT '第一期應收日期' AFTER first_payment_received"),
    ("first_payment_received_at", "DATE NULL COMMENT '第一期實收日期' AFTER first_payment_due_date"),
    ("second_payment_receivable", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第二期應收金額' AFTER first_payment_received_at"),
    ("second_payment_received", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '第二期實收金額' AFTER second_payment_receivable"),
    ("second_payment_due_date", "DATE NULL COMMENT '第二期應收日期' AFTER second_payment_received"),
    ("second_payment_received_at", "DATE NULL COMMENT '第二期實收日期' AFTER second_payment_due_date"),
    ("amount_receivable", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '應收總額' AFTER second_payment_received_at"),
    ("amount_received", "DECIMAL(10, 2) NOT NULL DEFAULT 0.00 COMMENT '實收總額' AFTER amount_receivable"),
]


def migrate() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM payments")
            existing = {row["Field"] for row in cursor.fetchall()}

            for name, definition in NEW_COLUMNS.items():
                if name not in existing:
                    cursor.execute(f"ALTER TABLE payments ADD COLUMN {name} {definition}")

            cursor.execute("""
                UPDATE payments
                SET deposit_receivable = GREATEST(deposit_receivable, deposit_received),
                    first_payment_receivable = GREATEST(first_payment_receivable, first_payment_received),
                    second_payment_receivable = GREATEST(
                        second_payment_receivable,
                        second_payment_received,
                        amount_receivable
                            - GREATEST(deposit_receivable, deposit_received)
                            - GREATEST(first_payment_receivable, first_payment_received)
                    ),
                    deposit_due_date = COALESCE(deposit_due_date, deposit_received_at),
                    first_payment_due_date = COALESCE(first_payment_due_date, first_payment_received_at),
                    second_payment_due_date = COALESCE(second_payment_due_date, second_payment_received_at),
                    amount_received = deposit_received + first_payment_received + second_payment_received
            """)
            cursor.execute("""
                UPDATE payments
                SET amount_receivable = deposit_receivable
                    + first_payment_receivable
                    + second_payment_receivable
            """)

            for name, definition in ORDERED_COLUMNS:
                cursor.execute(f"ALTER TABLE payments MODIFY COLUMN {name} {definition}")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("payments 三階段欄位遷移完成")
