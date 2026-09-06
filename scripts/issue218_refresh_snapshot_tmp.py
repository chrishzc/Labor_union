from pathlib import Path

path = Path(
    "tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/"
    "integration/test_order_intake_disposable_mysql_http.py"
)
text = path.read_text(encoding="utf-8")
old = """def _snapshot(connection, case_no: str) -> dict[str, Any]:\n    with connection.cursor() as cursor:\n"""
new = """def _snapshot(connection, case_no: str) -> dict[str, Any]:\n    # End the observer transaction so each acceptance readback sees current committed facts.\n    connection.commit()\n    with connection.cursor() as cursor:\n"""
assert text.count(old) == 1, text.count(old)
path.write_text(text.replace(old, new, 1), encoding="utf-8")
