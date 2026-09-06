from pathlib import Path

route_path = Path('api/routes/order_intake_terms_bootstrap.py')
route = route_path.read_text(encoding='utf-8')
old_router = 'router = APIRouter(tags=["Orders"])'
new_router = 'router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])'
assert route.count(old_router) == 1, route.count(old_router)
route_path.write_text(route.replace(old_router, new_router, 1), encoding='utf-8')

main_path = Path('api/main.py')
main = main_path.read_text(encoding='utf-8')
old_import = '''    order_actual_start,\n    order_auto_completion,'''
new_import = '''    order_actual_start,\n    order_intake_terms_bootstrap,\n    order_auto_completion,'''
assert main.count(old_import) == 1, main.count(old_import)
main = main.replace(old_import, new_import, 1)
old_include = '''app.include_router(order_actual_start.router)\napp.include_router(order_auto_completion.router)'''
new_include = '''app.include_router(order_actual_start.router)\napp.include_router(order_intake_terms_bootstrap.router)\napp.include_router(order_auto_completion.router)'''
assert main.count(old_include) == 1, main.count(old_include)
main_path.write_text(main.replace(old_include, new_include, 1), encoding='utf-8')

test_path = Path('tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/unit/test_order_intake_route_composition.py')
test_path.parent.mkdir(parents=True, exist_ok=True)
test_path.write_text('''"""HTTP composition proof for the existing Orders intake repair contract."""\n\nimport pytest\nfrom fastapi.testclient import TestClient\n\nfrom api.main import app\n\n\n_CASE = "SYN-218-ROUTE"\n_FP = "0" * 64\n\n\n@pytest.mark.parametrize(\n    ("path", "body", "headers"),\n    [\n        (\n            f"/api/v1/orders/{_CASE}/intake-terms-bootstrap/preview",\n            {"proposed_start_date": "2026-09-10", "proposed_service_days": 5},\n            {},\n        ),\n        (\n            f"/api/v1/orders/{_CASE}/intake-terms-bootstrap/apply",\n            {\n                "proposed_start_date": "2026-09-10",\n                "proposed_service_days": 5,\n                "expected_lifecycle_version": 0,\n                "preview_fingerprint": _FP,\n                "reason": "synthetic route composition proof",\n            },\n            {"Idempotency-Key": "route-terms", "X-Correlation-ID": "route-terms"},\n        ),\n        (\n            f"/api/v1/orders/{_CASE}/intake-completion/client-name/preview",\n            {"client_name": "合成姓名"},\n            {},\n        ),\n        (\n            f"/api/v1/orders/{_CASE}/intake-completion/client-name/apply",\n            {\n                "client_name": "合成姓名",\n                "expected_lifecycle_version": 0,\n                "preview_fingerprint": _FP,\n                "reason": "synthetic route composition proof",\n            },\n            {"Idempotency-Key": "route-name", "X-Correlation-ID": "route-name"},\n        ),\n        (f"/api/v1/orders/{_CASE}/intake-completion/preview", None, {}),\n        (\n            f"/api/v1/orders/{_CASE}/intake-completion/apply",\n            {\n                "expected_lifecycle_version": 0,\n                "preview_fingerprint": _FP,\n                "reason": "synthetic route composition proof",\n            },\n            {"Idempotency-Key": "route-completion", "X-Correlation-ID": "route-completion"},\n        ),\n    ],\n)\ndef test_intake_repair_public_paths_reach_persisted_admin_boundary(path, body, headers):\n    client = TestClient(app)\n    response = client.post(path, json=body, headers=headers)\n\n    assert response.status_code == 401\n    assert response.status_code != 404\n''', encoding='utf-8')
