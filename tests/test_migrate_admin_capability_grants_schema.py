"""Read-only regression checks for removed commands and current documentation."""

import ast
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOVED_SCRIPTS = (
    "migrate_admin_capability_grants_schema",
    "migrate_case_architecture_bootstrap_receipt_version_contract",
    "migrate_leave_substitution_holiday_only_batch_contract",
    "audit_staff_historical_adoption",
    "bootstrap_line_configuration",
    "create_admin",
    "export_db_snapshot_fixture_v2",
    "fix_schedule_conflicts",
    "generate_staff_resume_docs",
    "import_db_snapshot_fixture_v2",
    "prepare_issue218_persisted_browser_fixture",
    "reconcile_fixture_order_dates_v2",
    "run_contract_signing_normal_chain",
    "run_holiday_work_agreement_scenario",
    "run_task96_hob_route_a",
    "run_task96_payout001_scenario",
    "run_task96_rpre_browser_scenario",
    "run_task96_scheduling_lane_c",
    "upgrade_line_menu_merge_defaults",
    "verify_validation_database",
    "verify_validation_dataset",
)
LIBRARY_ONLY_SCRIPTS = (
    "backfill_canonical_accounting_projections",
    "bootstrap_disposable_mysql_schema",
    "collect_local_additive_engine_evidence",
    "migrate_assignment_schedule_integrity",
    "migrate_legacy_ui_dataset",
    "plan_legacy_ui_dataset_integration",
    "run_case_import_invalid_scenario",
    "seed_payment_schedule_normal_case",
    "seed_ui_validation_dataset",
    "seed_validation_beclass_review",
    "seed_validation_dataset",
    "seed_validation_finance_manual_review",
    "verify_case_import_invalid_scenario",
    "verify_finance_manual_review_scenario",
    "verify_integrated_ui_validation_dataset",
    "verify_legacy_ui_preservation",
    "init_db",
    "migrate_remove_other_addition",
)


def tracked_paths():
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=True,
    )
    return [ROOT / name for name in output.split("\0") if name]


class RetiredScriptEntrypointTests(unittest.TestCase):
    def test_retired_commands_are_removed(self):
        for name in REMOVED_SCRIPTS:
            with self.subTest(script=name):
                self.assertFalse((ROOT / "scripts" / f"{name}.py").exists())

    def test_retained_libraries_have_no_command_entrypoints(self):
        for name in LIBRARY_ONLY_SCRIPTS:
            with self.subTest(script=name):
                tree = ast.parse((ROOT / "scripts" / f"{name}.py").read_bytes())
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.assertNotEqual(node.name, "main")
                    if isinstance(node, ast.If):
                        test = ast.unparse(node.test)
                        self.assertFalse("__name__" in test and "__main__" in test)

    def test_no_python_imports_target_removed_scripts(self):
        removed = {f"scripts.{name}" for name in REMOVED_SCRIPTS}
        for path in tracked_paths():
            if path.suffix != ".py" or not path.is_file():
                continue
            for node in ast.walk(ast.parse(path.read_bytes())):
                targets = []
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    targets = [node.module or ""]
                    targets.extend(f"{node.module}.{alias.name}" for alias in node.names)
                if targets:
                    with self.subTest(path=path.relative_to(ROOT), line=node.lineno):
                        self.assertFalse(removed.intersection(targets))

    def test_current_documentation_does_not_advertise_removed_scripts(self):
        documents = [
            ROOT / "scripts/scripts_map.md",
            ROOT / "scripts/imports/imports_map.md",
            ROOT / "config/README_CONFIG.md",
            ROOT / "validation/datasets/README.md",
            *(ROOT / ".arch-map").rglob("*.md"),
        ]
        removed = {f"scripts/{name}.py" for name in REMOVED_SCRIPTS}
        libraries = {f"scripts/{name}.py" for name in LIBRARY_ONLY_SCRIPTS}
        for path in documents:
            source = path.read_text(encoding="utf-8")
            refs = set(re.findall(r"scripts/[A-Za-z0-9_/]+\.py", source))
            for ref in refs & (removed | libraries):
                with self.subTest(document=path.relative_to(ROOT), script=ref):
                    self.assertTrue((ROOT / ref).is_file())
            for module in re.findall(r"python -m (scripts\.[A-Za-z0-9_.]+)", source):
                command = ROOT / (module.replace(".", "/") + ".py")
                with self.subTest(document=path.relative_to(ROOT), command=module):
                    self.assertTrue(command.is_file())
                    tree = ast.parse(command.read_bytes())
                    self.assertTrue(any(
                        isinstance(node, ast.If)
                        and "__name__" in ast.unparse(node.test)
                        and "__main__" in ast.unparse(node.test)
                        for node in tree.body
                    ))

    def test_scenarios_without_runners_are_not_claimed_as_bound(self):
        for relative in (
            "validation/scenarios/MIG-VALIDATION-SCHEMA-002.json",
            "validation/scenarios/historical_orders/HOB-F04-ROUTE-A-001.json",
            "validation/scenarios/anomalies/PAYOUT-001-EXACT-001.json",
        ):
            with self.subTest(scenario=relative):
                data = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                self.assertEqual(data["status"], "blocked")
                self.assertTrue(data["blocker"].strip())
                execution = json.dumps(data.get("execution", {}))
                for name in REMOVED_SCRIPTS + LIBRARY_ONLY_SCRIPTS:
                    self.assertNotIn(f"scripts/{name}.py", execution)
                    self.assertNotIn(f"scripts\\\\{name}.py", execution)

    def test_ci_uses_assertions_and_read_only_artifact_checks(self):
        workflow = (ROOT / ".github/workflows/python-app.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("python -m unittest discover -s tests -p test_migrate_admin_capability_grants_schema.py", workflow)
        self.assertIn("python -m scripts.verify_validation_schema_manifest", workflow)
        self.assertIn("python -m scripts.build_validation_schema_release --check", workflow)
        self.assertNotIn("script-cleanup-source", workflow)
        self.assertNotIn("Inspect remaining command references", workflow)


if __name__ == "__main__":
    unittest.main()
