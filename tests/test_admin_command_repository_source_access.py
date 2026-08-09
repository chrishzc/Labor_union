import pytest

from infrastructure.mysql.admin_command_repository import AdminCommandRepository


class UnexpectedDatabaseAccess:
    def cursor(self):
        raise AssertionError("protected source fields must fail before database access")


def test_source_row_update_rejects_protected_fields_before_database_access():
    repository = AdminCommandRepository(UnexpectedDatabaseAccess())

    with pytest.raises(ValueError, match="protected_source_field:case_no"):
        repository.update_source_row("clients", 1, {"case_no": "CASE-002"})
