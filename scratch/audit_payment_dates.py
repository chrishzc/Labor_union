import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import db_service

orders = db_service.get_order_details()
print("=== ORDER PAYMENT DATES AUDIT ===")
for o in orders[:5]:
    print(f"Order #{o['order_id']} ({o['client_name']}):")
    print(f"  actual_start_date: {o.get('actual_start_date')}")
    print(f"  actual_end_date: {o.get('actual_end_date')}")
    print(f"  salary_payment_date_1: {o.get('salary_payment_date_1')}")
    print(f"  salary_payment_date_2: {o.get('salary_payment_date_2')}")
    print(f"  first_payment_date: {o.get('first_payment_date')}")
    print(f"  second_payment_date: {o.get('second_payment_date')}")
