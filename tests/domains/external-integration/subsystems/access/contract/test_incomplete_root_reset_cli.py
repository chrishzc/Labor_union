"""Offline reset entry is explicit, local-only and does not expose credentials."""
from unittest.mock import Mock

import pytest

from scripts import reset_incomplete_root_setup as cli
from subsystems.access.incomplete_root_reset import IncompleteRootPreview, IncompleteRootResetError, reset_incomplete_root_setup


@pytest.fixture
def entry(monkeypatch):
    monkeypatch.setattr(cli, "_database_config_from_environment", lambda: {"host": "127.0.0.1", "database": "union_db"})
    monkeypatch.setattr(cli, "get_access_control_connection_factory", lambda: object())
    preview = Mock(return_value=IncompleteRootPreview("union_db", 7, 1))
    apply = Mock()
    monkeypatch.setattr(cli, "preview_incomplete_root_reset", preview)
    monkeypatch.setattr(cli, "reset_incomplete_root_setup", apply)
    return preview, apply


def test_default_is_read_only_and_apply_requires_exact_confirmation(entry):
    preview, apply = entry
    assert cli.main([]) == 0
    apply.assert_not_called()
    assert cli.main(["--apply"], confirm=lambda _: "cancel") == 1
    apply.assert_not_called()
    assert cli.main(["--apply"], confirm=lambda _: "RESET ROOT union_db 7") == 0
    assert apply.call_args.kwargs["expected_account_id"] == 7
    assert apply.call_args.kwargs["expected_version"] == 1


def test_remote_configuration_never_opens_a_connection(entry, monkeypatch):
    monkeypatch.setattr(cli, "_database_config_from_environment", lambda: {"host": "nas.example.test", "database": "union_db"})
    assert cli.main(["--apply"]) == 2
    entry[0].assert_not_called()
    entry[1].assert_not_called()


def test_production_cannot_reach_the_reset_writer(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    factory = Mock()
    with pytest.raises(IncompleteRootResetError, match="development_required"):
        reset_incomplete_root_setup(connection_factory=factory, target_database="union_db", expected_account_id=7, expected_version=1)
    factory.assert_not_called()


def test_driver_errors_are_not_echoed(entry, capsys):
    entry[0].side_effect = RuntimeError("private-connection-password")
    assert cli.main([]) == 2
    assert "private-connection-password" not in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["", "yes", "RESET ROOT union_db 8", "RESET ROOT other_db 7"])
def test_clicking_or_confirming_the_wrong_target_cannot_apply(entry, answer):
    assert cli.main(["--apply"], confirm=lambda _: answer) == 1
    entry[1].assert_not_called()
