"""Tests for the audited client-identity source migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_client_identity_status_source.py"
SPEC = importlib.util.spec_from_file_location("client_identity_migration", SCRIPT)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class Cursor:
    def __init__(
        self, *, missing_identity=0, unlinked_orders=0, views=(), routines=0,
        column_exists=True, uppercase_metadata=False,
    ):
        self.missing_identity = missing_identity
        self.unlinked_orders = unlinked_orders
        self.views = list(views)
        self.routines = routines
        self.column_exists = column_exists
        self.uppercase_metadata = uppercase_metadata
        self.executed: list[str] = []
        self.current = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=()):
        compact = " ".join(sql.split())
        self.executed.append(compact)
        if compact == "SELECT COUNT(*) AS count FROM orders":
            self.current = {"count": 3}
        elif "FROM clients" in compact:
            self.current = {"count": self.missing_identity}
        elif "LEFT JOIN clients" in compact:
            self.current = {"count": self.unlinked_orders}
        elif "JOIN clients c" in compact and "identity_status IS NULL" in compact:
            self.current = {"count": self.missing_identity}
        elif "SELECT table_name, view_definition" in compact:
            self.current = self.views
        elif "information_schema.columns" in compact:
            self.current = {"count": int(self.column_exists)}
        elif "information_schema.routines" in compact:
            self.current = {"count": self.routines}
        elif compact == "SHOW CREATE TABLE orders":
            self.current = (
                {"TABLE": "orders", "CREATE TABLE": "CREATE TABLE orders (`id` int)"}
                if self.uppercase_metadata
                else {"Table": "orders", "Create Table": "CREATE TABLE orders (`id` int)"}
            )
        elif compact.startswith("SHOW CREATE VIEW"):
            view_name = compact.split("`")[1]
            self.current = (
                {
                    "VIEW": view_name,
                    "CREATE VIEW": "CREATE VIEW `" + view_name + "` AS SELECT o.clients.identity_status FROM orders o JOIN clients c ON c.id = o.client_id",
                }
                if self.uppercase_metadata
                else {
                    "View": view_name,
                    "Create View": "CREATE VIEW `" + view_name + "` AS SELECT o.clients.identity_status FROM orders o JOIN clients c ON c.id = o.client_id",
                }
            )
        elif compact.startswith("CREATE OR REPLACE VIEW"):
            self.current = {}
        elif compact.startswith("ALTER TABLE orders DROP COLUMN"):
            self.column_exists = False
            self.current = {}
        else:
            raise AssertionError(compact)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current) if isinstance(self.current, list) else []


class Connection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def cursor(self):
        return self.cursor_instance


def _clean_project(tmp_path: Path) -> Path:
    for directory in migration.SOURCE_DIRECTORIES:
        (tmp_path / directory).mkdir()
    return tmp_path


def test_dry_run_is_read_only_and_reports_a_safe_removal_plan(tmp_path):
    cursor = Cursor()
    manifest = migration.run_migration(Connection(cursor), project_root=_clean_project(tmp_path))

    assert manifest["mode"] == "dry-run"
    assert manifest["blocked_reasons"] == []
    assert manifest["ddl"]["executed"] is False
    assert manifest["postcheck"]["status"] == "would_remove"
    assert not any(sql.startswith("ALTER ") for sql in cursor.executed)


def test_apply_fails_closed_before_ddl_when_identity_is_missing(tmp_path):
    cursor = Cursor(missing_identity=1)
    manifest = migration.run_migration(Connection(cursor), apply=True, project_root=_clean_project(tmp_path))

    assert "clients_have_missing_identity_status" in manifest["blocked_reasons"]
    assert manifest["ddl"]["executed"] is False
    assert not any(sql.startswith("SHOW CREATE") or sql.startswith("ALTER ") for sql in cursor.executed)


def test_apply_fails_closed_when_a_source_consumer_remains(tmp_path):
    root = _clean_project(tmp_path)
    (root / "services" / "legacy.py").write_text("value = 'subsidy_eligibility'\n", encoding="utf-8")

    manifest = migration.run_migration(Connection(Cursor()), apply=True, project_root=root)

    assert manifest["blocked_reasons"] == ["application_or_sql_sources_still_reference_legacy_column"]
    assert manifest["source_references"] == [{"path": "services/legacy.py", "line": 1}]
    assert manifest["ddl"]["executed"] is False


def test_fake_data_force_mode_still_blocks_a_source_consumer(tmp_path):
    root = _clean_project(tmp_path)
    (root / "services" / "legacy.py").write_text("value = 'subsidy_eligibility'\n", encoding="utf-8")

    manifest = migration.run_migration(
        Connection(Cursor(missing_identity=2)), apply=True, discard_fake_data=True, project_root=root
    )

    assert manifest["force_mode"]["discard_fake_data"] is True
    assert manifest["force_mode"]["identity_gaps"]["clients_missing_identity_status"] == 2
    assert manifest["ddl"]["executed"] is False
    assert manifest["blocked_reasons"] == ["application_or_sql_sources_still_reference_legacy_column"]


def test_apply_captures_schema_then_removes_column_and_postchecks(tmp_path):
    cursor = Cursor()
    manifest = migration.run_migration(Connection(cursor), apply=True, project_root=_clean_project(tmp_path))

    assert manifest["schema_before"] == "CREATE TABLE orders (`id` int)"
    assert manifest["ddl"]["executed"] is True
    assert manifest["ddl"]["transactional"] is False
    assert manifest["postcheck"]["status"] == "passed"
    assert cursor.column_exists is False


def test_fake_data_force_mode_rebuilds_views_before_dropping_legacy_column(tmp_path):
    cursor = Cursor(
        missing_identity=2,
        views=[{"table_name": "v_order_details", "view_definition": "SELECT o.clients.identity_status"}],
    )

    manifest = migration.run_migration(
        Connection(cursor), apply=True, discard_fake_data=True, project_root=_clean_project(tmp_path)
    )

    assert manifest["ddl"]["executed"] is True
    view_rebuild = manifest["force_mode"]["view_rebuilds"][0]
    assert view_rebuild["view_name"] == "v_order_details"
    assert view_rebuild["view_definition_before"] == "CREATE VIEW `v_order_details` AS SELECT o.clients.identity_status FROM orders o JOIN clients c ON c.id = o.client_id"
    assert view_rebuild["rebuilt_statement"] == migration._canonical_v_order_details_statement()
    assert any(sql.startswith("CREATE OR REPLACE VIEW") for sql in cursor.executed)
    assert cursor.executed.index(next(sql for sql in cursor.executed if sql.startswith("CREATE OR REPLACE VIEW"))) < cursor.executed.index(next(sql for sql in cursor.executed if sql.startswith("ALTER TABLE")))


def test_uppercase_dictcursor_metadata_is_backed_up_rebuilt_and_dropped(tmp_path):
    cursor = Cursor(
        missing_identity=1,
        uppercase_metadata=True,
        views=[{"TABLE_NAME": "v_order_details", "VIEW_DEFINITION": "SELECT o.clients.identity_status"}],
    )

    manifest = migration.run_migration(
        Connection(cursor), apply=True, discard_fake_data=True, project_root=_clean_project(tmp_path)
    )

    assert manifest["schema_before"] == "CREATE TABLE orders (`id` int)"
    assert manifest["force_mode"]["view_rebuilds"][0]["view_name"] == "v_order_details"
    assert manifest["ddl"]["executed"] is True


def test_fake_data_force_mode_rejects_unknown_affected_view_before_ddl(tmp_path):
    cursor = Cursor(
        missing_identity=1,
        views=[{"table_name": "v_unrecognized", "view_definition": "SELECT o.clients.identity_status"}],
    )

    try:
        migration.run_migration(
            Connection(cursor), apply=True, discard_fake_data=True, project_root=_clean_project(tmp_path)
        )
    except RuntimeError as exc:
        assert "unknown affected views" in str(exc)
    else:
        raise AssertionError("unknown affected views must fail closed")

    assert not any(sql.startswith("CREATE OR REPLACE VIEW") or sql.startswith("ALTER TABLE") for sql in cursor.executed)


def test_discard_fake_data_requires_apply(tmp_path):
    try:
        migration.run_migration(Connection(Cursor()), discard_fake_data=True, project_root=_clean_project(tmp_path))
    except ValueError as exc:
        assert "requires apply" in str(exc)
    else:
        raise AssertionError("force mode must require --apply")


def test_source_scan_excludes_the_migration_script_but_not_other_consumers(tmp_path):
    root = _clean_project(tmp_path)
    (root / "scripts" / SCRIPT.name).write_text("subsidy_eligibility\n", encoding="utf-8")
    (root / "ui" / "page.py").write_text("subsidy_eligibility\n", encoding="utf-8")

    references = migration.find_legacy_source_references(root)

    assert references == [{"path": "ui/page.py", "line": 1}]
