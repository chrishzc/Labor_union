"""Default production file settings stay inside the single NAS root."""
import pytest
from infrastructure.runtime.file_transfer_settings import file_settings_path, save_file_settings, FileSettingsError


def test_production_settings_and_layout_use_only_existing_common_root(tmp_path, monkeypatch):
    root = tmp_path / "NAS"
    root.mkdir()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(root))
    monkeypatch.delenv("FILE_SETTINGS_PATH", raising=False)
    assert file_settings_path() == root / ".file-settings.json"
    assert not list(root.iterdir())
    result = save_file_settings(expected_version=0, photo_max_bytes=1000, resume_max_bytes=2000, timeout_seconds=30)
    assert result["version"] == 1
    assert file_settings_path().is_file()
    assert not (tmp_path / "file-settings.json").exists()


def test_missing_production_root_is_not_created_by_settings_write(tmp_path, monkeypatch):
    root = tmp_path / "offline-share"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(root))
    monkeypatch.delenv("FILE_SETTINGS_PATH", raising=False)
    with pytest.raises(FileSettingsError, match="file_settings_unavailable"):
        save_file_settings(expected_version=0, photo_max_bytes=1000, resume_max_bytes=2000, timeout_seconds=30)
    assert not root.exists()


def test_development_settings_keep_their_original_location(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", str(tmp_path / "controlled"))
    monkeypatch.delenv("FILE_SETTINGS_PATH", raising=False)
    assert file_settings_path() == tmp_path / "file-settings.json"


def test_unconfigured_production_settings_do_not_fall_back_to_local_data(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("CONTROLLED_FILE_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("FILE_SETTINGS_PATH", raising=False)
    with pytest.raises(FileSettingsError, match="file_settings_unavailable"):
        file_settings_path()
