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
test_path.write_text('''"""FastAPI composition proof for the existing Orders intake repair contract."""\n\nfrom api.main import app\n\n\n_EXPECTED_PATHS = {\n    "/api/v1/orders/{case_no}/intake-terms-bootstrap/preview",\n    "/api/v1/orders/{case_no}/intake-terms-bootstrap/apply",\n    "/api/v1/orders/{case_no}/intake-completion/client-name/preview",\n    "/api/v1/orders/{case_no}/intake-completion/client-name/apply",\n    "/api/v1/orders/{case_no}/intake-completion/preview",\n    "/api/v1/orders/{case_no}/intake-completion/apply",\n}\n\n\ndef test_intake_repair_routes_are_mounted_on_the_orders_public_prefix():\n    mounted = {route.path for route in app.routes}\n\n    assert _EXPECTED_PATHS <= mounted\n    assert not any(\n        path.startswith("/{case_no}/intake-")\n        for path in mounted\n    )\n''', encoding='utf-8')
