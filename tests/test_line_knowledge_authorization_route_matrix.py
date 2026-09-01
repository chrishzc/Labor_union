"""
File: test_line_knowledge_authorization_route_matrix.py
Description: 盤點 LINE、Knowledge 與 service/public route 的授權邊界。
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "api" / "routes"

KNOWLEDGE_GUARDS = {
    "require_knowledge_reader",
    "require_knowledge_manager",
    "require_knowledge_publisher",
    "require_knowledge_reindexer",
}
LINE_ROUTE_FILES = {
    "line_identity_management.py",
    "customer_service.py",
    "line_tasks.py",
    "line_configurations.py",
    "line_rich_menus.py",
    "line_notification_rules.py",
    "line_order_groups.py",
}
LINE_GUARDS = ("require_line_", "require_customer_service_")

MATCHING_ROUTE_CONTRACT = {
    "candidate_contact_pool.py": {
        "query_candidate_contact_pool": (
            {"require_line_matching_reader"},
            "none",
        ),
        "add_candidate_contact_pool_entries": (
            {"require_line_matching_sender"},
            "none",
        ),
        "send_candidate_information": (
            {"require_line_matching_sender"},
            "durable-provider-worker",
        ),
        "preview_manual_candidate_information_confirmation": (
            {"require_line_matching_override"},
            "none",
        ),
        "apply_manual_candidate_information_confirmation": (
            {"require_line_matching_override"},
            "none",
        ),
        "record_candidate_willingness": (
            {"require_line_matching_override"},
            "none",
        ),
    },
    "matches.py": {
        "get_matching_plan_contact_state_route": (
            {"require_line_matching_reader"},
            "none",
        ),
        "get_active_matching_plan_state_route": (
            {"require_line_matching_reader"},
            "none",
        ),
        "send_matching_plan_information_route": (
            {"require_line_matching_sender"},
            "durable-provider-worker",
        ),
        "record_matching_customer_decision_route": (
            {"require_line_matching_override"},
            "none",
        ),
        "record_matching_plan_willingness_route": (
            {"require_line_matching_override"},
            "none",
        ),
        "send_matching_plan_resumes_route": (
            {"require_line_matching_sender"},
            "durable-provider-worker",
        ),
        "preview_manual_matching_plan_resumes_route": (
            {"require_line_matching_override"},
            "none",
        ),
        "apply_manual_matching_plan_resumes_route": (
            {"require_line_matching_override"},
            "none",
        ),
        "cancel_matching_plan_route": ({"require_system_admin"}, "none"),
        "create_matching_plan_version_route": ({"require_system_admin"}, "none"),
        "recommend_staff": ({"require_system_admin"}, "none"),
    },
    "runtime_health.py": {
        "query_safe_review_link": ({"require_line_monitor_reader"}, "none"),
        "issue_safe_review_link": ({"require_line_alert_manager"}, "none"),
        "redeem_safe_review_link": ({"require_line_alert_manager"}, "none"),
        "revoke_safe_review_link": ({"require_line_alert_manager"}, "none"),
        "health_status": ({"require_line_monitor_reader"}, "none"),
        "health_events": ({"require_line_monitor_reader"}, "none"),
        "alert_targets": ({"require_line_monitor_reader"}, "none"),
        "admin_alert_candidates": ({"require_line_alert_manager"}, "none"),
        "add_admin_target": ({"require_line_alert_manager"}, "none"),
        "preview_add_admin_target": ({"require_line_alert_manager"}, "none"),
        "reset_group_target": ({"require_line_alert_manager"}, "none"),
        "preview_reset_group_target": ({"require_line_alert_manager"}, "none"),
        "set_target_enabled": ({"require_line_alert_manager"}, "none"),
        "preview_set_target_enabled": ({"require_line_alert_manager"}, "none"),
    },
}
RETIRED_410_HANDLERS = {
    "send_info_1",
    "send_info_2",
    "reply_matching_inquiry",
    "send_resume_to_client",
    "send_resume_for_case",
    "assign_staff_to_order",
}
EXPECTED_CAPABILITIES = {
    "require_line_matching_reader": "line.matching.read",
    "require_line_matching_sender": "line.matching.send",
    "require_line_matching_override": "line.matching.override",
    "require_system_admin": "system.administration",
    "require_line_monitor_reader": "line.monitor.read",
    "require_line_alert_manager": "line.alert.manage",
}
SIDE_EFFECT_CALLS = {
    "wakeup-only": {"publish_line_wakeup_best_effort", "wake_worker"},
    "durable-provider-worker": {
        "enqueue_line_task",
        "send_information",
        "request_caregiver_information",
        "request_customer_profiles",
    },
}


def _dependency_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id != "Depends" or not call.args:
            continue
        dependency = call.args[0]
        if isinstance(dependency, ast.Name):
            names.add(dependency.id)
        elif isinstance(dependency, ast.Attribute):
            names.add(dependency.attr)
    return names


def _route_inventory(filename: str) -> dict[str, set[str]]:
    tree = ast.parse((ROUTES / filename).read_text(encoding="utf-8"))
    router_dependencies: dict[str, set[str]] = {}
    inventory: dict[str, set[str]] = {}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "APIRouter"
        ):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    router_dependencies[target.id] = _dependency_names(statement.value)
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routers = {
            decorator.func.value.id
            for decorator in statement.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
        }
        if not routers:
            continue
        route_decorators = [
            decorator
            for decorator in statement.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id in routers
        ]
        if statement.name in RETIRED_410_HANDLERS or route_decorators and all(
            any(
                isinstance(keyword.value, ast.Constant)
                and keyword.arg == "include_in_schema"
                and keyword.value.value is False
                for keyword in decorator.keywords
            )
            for decorator in route_decorators
        ):
            continue
        dependencies = _dependency_names(statement)
        for router in routers:
                    inventory[statement.name] = dependencies | router_dependencies.get(router, set())
    return inventory


def _route_endpoint_nodes(filename: str) -> dict[str, ast.AST]:
    tree = ast.parse((ROUTES / filename).read_text(encoding="utf-8"))
    endpoint_nodes: dict[str, ast.AST] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routers = {
            decorator.func.value.id
            for decorator in statement.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
        }
        if routers:
            route_decorators = [
                decorator
                for decorator in statement.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id in routers
            ]
            if statement.name in RETIRED_410_HANDLERS or route_decorators and all(
                any(
                    isinstance(keyword.value, ast.Constant)
                    and keyword.arg == "include_in_schema"
                    and keyword.value.value is False
                    for keyword in decorator.keywords
                )
                for decorator in route_decorators
            ):
                continue
            endpoint_nodes[statement.name] = statement
    return endpoint_nodes


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name):
            names.add(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            names.add(call.func.attr)
    return names


def _side_effect_class(node: ast.AST) -> str:
    called = _called_names(node)
    for side_effect, call_names in SIDE_EFFECT_CALLS.items():
        if called & call_names:
            return side_effect
    return "none"


def _registered_capability_aliases() -> dict[str, str]:
    capability_tree = ast.parse(
        (ROOT / "subsystems" / "line" / "capabilities.py").read_text(
            encoding="utf-8"
        )
    )
    capability_values: dict[str, str] = {}
    for statement in capability_tree.body:
        if not isinstance(statement, ast.ClassDef) or statement.name != "LineCapability":
            continue
        for member in statement.body:
            target = (
                member.target
                if isinstance(member, ast.AnnAssign)
                else member.targets[0]
                if isinstance(member, ast.Assign) and len(member.targets) == 1
                else None
            )
            value = member.value if isinstance(member, (ast.Assign, ast.AnnAssign)) else None
            if (
                isinstance(target, ast.Name)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                capability_values[target.id] = value.value

    auth_tree = ast.parse(
        (ROOT / "api" / "dependencies" / "admin_auth.py").read_text(
            encoding="utf-8"
        )
    )
    aliases: dict[str, str] = {}
    for statement in auth_tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = statement.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Name) or value.func.id != "require_capability":
            continue
        if not value.args:
            continue
        argument = value.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            aliases[target.id] = argument.value
        elif (
            isinstance(argument, ast.Attribute)
            and isinstance(argument.value, ast.Name)
            and argument.value.id == "LineCapability"
            and argument.attr in capability_values
        ):
            aliases[target.id] = capability_values[argument.attr]
    return aliases


def test_knowledge_routes_use_only_registered_knowledge_guards() -> None:
    inventory = _route_inventory("knowledge_retrieval.py")

    assert inventory
    assert all(dependencies & KNOWLEDGE_GUARDS for dependencies in inventory.values())
    assert all("require_root" not in dependencies for dependencies in inventory.values())


def test_contract_route_uses_registered_contract_reader() -> None:
    inventory = _route_inventory("contracts.py")

    assert inventory == {
        "get_staff_contract_by_case_no": {
            "require_contract_evidence_reader",
            "get_contract_context_service",
        }
    }


def test_line_admin_routes_are_guarded_without_root_gate() -> None:
    inventory = _route_inventory("line_admin.py")

    assert inventory
    assert all("require_line_viewer" in dependencies for dependencies in inventory.values())
    assert all("require_root" not in dependencies for dependencies in inventory.values())


def test_line_business_routes_have_registered_admin_dependencies() -> None:
    for filename in LINE_ROUTE_FILES:
        inventory = _route_inventory(filename)
        assert inventory, filename
        assert all(
            any(name.startswith(prefix) for name in dependencies for prefix in LINE_GUARDS)
            for dependencies in inventory.values()
        ), filename
        assert all("require_root" not in dependencies for dependencies in inventory.values()), filename


def test_matching_and_runtime_routes_have_complete_guard_capability_matrix() -> None:
    registered_aliases = _registered_capability_aliases()
    assert {
        alias: registered_aliases.get(alias)
        for alias in EXPECTED_CAPABILITIES
    } == EXPECTED_CAPABILITIES

    route_count = 0
    for filename, expected_routes in MATCHING_ROUTE_CONTRACT.items():
        inventory = _route_inventory(filename)
        nodes = _route_endpoint_nodes(filename)
        assert set(inventory) == set(expected_routes), filename
        assert set(nodes) == set(expected_routes), filename
        for route_name, (expected_dependencies, expected_side_effect) in expected_routes.items():
            dependencies = inventory[route_name]
            assert dependencies == expected_dependencies, (filename, route_name)
            assert "require_root" not in dependencies, (filename, route_name)
            assert expected_dependencies <= set(registered_aliases), (filename, route_name)
            assert _side_effect_class(nodes[route_name]) == expected_side_effect, (
                filename,
                route_name,
            )
            route_count += 1

    assert route_count == 31


def test_identity_public_liff_and_page_static_routes_are_explicit_exclusions() -> None:
    inventory = _route_inventory("line_identity.py")

    public_names = {
        "identity_runtime_config",
        "open_identity_flow",
        "validate_identity_flow",
        "preview_customer",
        "apply_customer",
        "preview_staff",
        "apply_staff",
        "apply_admin",
        "apply_provisional_registration",
        "identity_page",
        "registration_page",
        "staff_orders_page",
        "staff_schedule_page",
    }
    assert public_names <= inventory.keys()
    assert all(not (inventory[name] & {"require_root", "require_admin"}) for name in public_names)
    assert "require_line_identity_reader" in inventory["list_reviews"]
    assert "require_line_identity_reviewer" in inventory["decide_review"]


def test_line_system_config_separates_admin_router_from_public_liff_router() -> None:
    inventory = _route_inventory("line_system_config.py")

    assert "require_line_viewer" in inventory["get_message_templates"]
    assert "require_line_manager" in inventory["replace_message_templates"]
    assert not inventory["get_liff_config"]
    assert not inventory["get_liff_runtime"]


def test_service_runtime_boundary_uses_internal_service_auth() -> None:
    inventory = _route_inventory("private_operations.py")

    assert inventory
    assert all("require_internal_service" in dependencies for dependencies in inventory.values())
    assert all(not any(name.startswith("require_admin") for name in dependencies) for dependencies in inventory.values())


def test_line_webhook_stays_outside_admin_session_route_matrix() -> None:
    tree = ast.parse((ROOT / "line" / "line_bot.py").read_text(encoding="utf-8"))
    webhook = next(
        statement
        for statement in tree.body
        if isinstance(statement, ast.AsyncFunctionDef) and statement.name == "line_webhook"
    )

    decorator_paths = {
        decorator.args[0].value
        for decorator in webhook.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "router"
        and decorator.args
        and isinstance(decorator.args[0], ast.Constant)
    }
    called_names = {
        call.func.id
        for call in ast.walk(webhook)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }

    assert "/webhook/line" in decorator_paths
    assert not _dependency_names(webhook)
    assert "canonical_line_webhook" in called_names


def test_account_center_is_the_only_root_only_route_module() -> None:
    account_inventory = _route_inventory("account_center.py")
    assert account_inventory
    assert all("require_root" in dependencies for dependencies in account_inventory.values())

    for filename in (
        "contracts.py",
        "knowledge_retrieval.py",
        "line_admin.py",
        *LINE_ROUTE_FILES,
    ):
        inventory = _route_inventory(filename)
        assert all("require_root" not in dependencies for dependencies in inventory.values()), filename
