from scripts.migrate_admin_capability_grants_schema import migrate


class _Cursor:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if statement.startswith("ALTER TABLE"):
            self.exists = True

    def fetchone(self):
        return {"Field": "authorization_version"} if self.exists else None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.cursor_instance = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_existing_database_adds_authorization_version_once():
    cursor = _Cursor(False)
    connection = _Connection(cursor)

    assert migrate(connection) == "migrated"
    assert cursor.exists is True
    assert connection.committed is True


def test_current_database_replays_without_ddl():
    cursor = _Cursor(True)

    assert migrate(_Connection(cursor)) == "already_current"
    assert not any(statement.startswith("ALTER TABLE") for statement in cursor.statements)
    assert any(statement.startswith("CREATE TABLE IF NOT EXISTS admin_capability_grants") for statement in cursor.statements)
