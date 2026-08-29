from pathlib import Path

from scripts import migrate_admin_capability_grants_schema as migration


def test_standalone_access_migration_fails_closed_without_writer(capsys):
    assert migration.main() == 2
    assert migration.MIGRATION_BLOCKED_REASON in capsys.readouterr().err


def test_standalone_access_migration_exposes_no_direct_ddl_or_commit():
    source = Path(migration.__file__).read_text(encoding="utf-8")

    assert "def migrate(" not in source
    assert ".commit(" not in source
    assert "ALTER TABLE" not in source
