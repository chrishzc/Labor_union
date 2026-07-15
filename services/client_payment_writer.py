"""Persist client transactions and recalculate the client payment summary."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from services.client_payment_transactions import calculate_client_payment_state
from services.db_service import get_connection


def build_client_summary_update(receivables, transactions, occurred_at):
    state = calculate_client_payment_state(receivables, transactions)
    settlement_dates = _settlement_dates(receivables, transactions, occurred_at)
    first_received_at = settlement_dates["first_payment_received_at"]
    second_due_date = None
    if Decimal(str(receivables["second_payment"])) > 0 and first_received_at:
        second_due_date = (_as_date(first_received_at) + timedelta(days=15)).isoformat()
    return state | settlement_dates | {"second_payment_due_date": second_due_date}


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("occurred_at must be a date or ISO date string")


def _settlement_dates(receivables, transactions, fallback_occurred_at):
    received = {"deposit": Decimal("0"), "first_payment": Decimal("0"), "second_payment": Decimal("0")}
    dates = {stage: None for stage in received}
    ordered_transactions = sorted(
        enumerate(transactions),
        key=lambda item: (_as_date(item[1].get("occurred_at") or fallback_occurred_at), item[0]),
    )
    for _, transaction in ordered_transactions:
        if transaction.get("transaction_status") != "succeeded":
            continue
        stage = transaction.get("stage")
        if stage not in received:
            continue
        amount = Decimal(str(transaction["amount"]))
        transaction_type = transaction.get("transaction_type")
        received[stage] += amount if transaction_type == "receipt" else -amount
        receivable = Decimal(str(receivables[stage]))
        if receivable == 0:
            dates[stage] = None
        elif received[stage] == receivable:
            dates[stage] = _as_date(transaction.get("occurred_at") or fallback_occurred_at).isoformat()
        else:
            dates[stage] = None
    return {
        "deposit_received_at": dates["deposit"],
        "first_payment_received_at": dates["first_payment"],
        "second_payment_received_at": dates["second_payment"],
    }


def record_client_payment_transaction(client_payment_id, stage, transaction_type, transaction_status,
                                      amount, occurred_at, external_reference, notes=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM client_payments WHERE id = %s FOR UPDATE", (client_payment_id,))
            payment = cursor.fetchone()
            if not payment:
                raise ValueError("client payment does not exist")
            cursor.execute("""SELECT stage, transaction_type, transaction_status, amount, occurred_at, external_reference
                FROM client_payment_transactions
                WHERE client_payment_id = %s
                  AND stage IN ('deposit', 'first_payment', 'second_payment')
                ORDER BY occurred_at, id
                FOR UPDATE""", (client_payment_id,))
            transactions = cursor.fetchall()
            transactions.append({"stage": stage, "transaction_type": transaction_type, "transaction_status": transaction_status, "amount": amount, "occurred_at": occurred_at, "external_reference": external_reference})
            receivables = {"deposit": payment["deposit_receivable"], "first_payment": payment["first_payment_receivable"], "second_payment": payment["second_payment_receivable"]}
            update = build_client_summary_update(receivables, transactions, occurred_at)
            cursor.execute("""INSERT INTO client_payment_transactions
                (client_payment_id, case_no, stage, transaction_type, transaction_status, amount, occurred_at, external_reference, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (client_payment_id, payment["case_no"], stage, transaction_type, transaction_status, amount, occurred_at, external_reference, notes))
            cursor.execute("""UPDATE client_payments SET deposit_received=%s, first_payment_received=%s,
                second_payment_received=%s, amount_received=%s,
                deposit_received_at=%s, first_payment_received_at=%s, second_payment_received_at=%s,
                second_payment_due_date=%s
                WHERE id=%s""", (update["deposit_received"], update["first_payment_received"], update["second_payment_received"], update["amount_received"], update["deposit_received_at"], update["first_payment_received_at"], update["second_payment_received_at"], update["second_payment_due_date"], client_payment_id))
            if update["deposit_received_at"]:
                cursor.execute("""UPDATE orders
                    SET status = '訂單成立'
                    WHERE case_no = %s AND status = '洽談中'""", (payment["case_no"],))
        conn.commit()
        return update
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
