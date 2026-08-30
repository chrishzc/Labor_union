from infrastructure.mysql.admin_command_repository import AdminCommandRepository


def test_generic_source_correction_methods_are_removed():
    repository = AdminCommandRepository(object())

    assert not hasattr(repository, "load_source_row")
    assert not hasattr(repository, "update_source_row")
