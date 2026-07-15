from services.db_service import get_connection


def prepare_monthly_payments(target_month: str) -> list[dict]:
    """
    Prepare unpaid staff payments (pending or partially_paid) due in the target_month (e.g., '2026-07').
    Returns a list of dicts, each containing:
      - staff_payment_id: int
      - case_no: str
      - staff_id: int
      - due_date: str (YYYY-MM-DD)
      - total_payable: float
      - amount_paid: float
      - remaining_amount: float
    """
    try:
        parts = target_month.split("-")
        year = int(parts[0])
        month = int(parts[1])
    except (ValueError, IndexError):
        raise ValueError("Invalid target_month format. Expected 'YYYY-MM'.")

    import calendar
    _, last_day = calendar.monthrange(year, month)
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, case_no, staff_id, due_date, total_payable, amount_paid, payment_status
                FROM staff_payments
                WHERE due_date >= %s AND due_date <= %s
                  AND payment_status IN ('pending', 'partially_paid')
                ORDER BY due_date ASC, id ASC
            """, (start_date, end_date))
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                total = float(row["total_payable"])
                paid = float(row["amount_paid"])
                remaining = total - paid
                if remaining > 0:
                    results.append({
                        "staff_payment_id": row["id"],
                        "case_no": row["case_no"],
                        "staff_id": row["staff_id"],
                        "due_date": row["due_date"].strftime("%Y-%m-%d") if row["due_date"] else None,
                        "total_payable": total,
                        "amount_paid": paid,
                        "remaining_amount": remaining
                    })
            return results
    finally:
        conn.close()
