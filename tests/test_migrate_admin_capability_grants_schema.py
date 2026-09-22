"""The retired standalone migration commands are absent from the working tree."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RetiredStandaloneMigrationTests(unittest.TestCase):
    def test_retired_standalone_migration_entrypoints_are_removed(self) -> None:
        for name in (
            "migrate_admin_capability_grants_schema.py",
            "migrate_case_architecture_bootstrap_receipt_version_contract.py",
            "migrate_leave_substitution_holiday_only_batch_contract.py",
        ):
            with self.subTest(entrypoint=name):
                self.assertFalse((ROOT / "scripts" / name).exists())


if __name__ == "__main__":
    unittest.main()
