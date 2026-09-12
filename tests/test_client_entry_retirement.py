"""Verify obsolete Client entries are removed while their owners stay mounted."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ClientEntryRetirementTests(unittest.TestCase):
    def test_retired_client_module_is_removed(self) -> None:
        self.assertFalse((ROOT / "api/routes/clients.py").exists())

    def test_application_does_not_import_or_mount_retired_client_router(self) -> None:
        tree = ast.parse((ROOT / "api/main.py").read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "api.routes"
            for alias in node.names
        }
        self.assertNotIn("clients", imported)
        self.assertNotIn("clients.router", {
            ast.unparse(node.args[0])
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
        })

    def test_replacement_owner_and_archive_queries_remain_mounted(self) -> None:
        tree = ast.parse((ROOT / "api/main.py").read_text(encoding="utf-8"))
        mounted = {
            ast.unparse(node.args[0])
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
        }
        self.assertTrue({
            "client_registry.router", "hcm_import.router", "data_browser_admin.router",
        }.issubset(mounted))


if __name__ == "__main__":
    unittest.main()
