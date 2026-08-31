"""Regression contracts for filesystem checks used by runtime artifacts."""

from __future__ import annotations

from pathlib import Path

from infrastructure.runtime.path_compatibility import (
    install_path_junction_compatibility,
    is_link_like_directory,
)


class _SymlinkPath:
    def is_symlink(self) -> bool:
        return True

    def is_junction(self) -> bool:
        raise AssertionError("symlink detection must short-circuit junction detection")


class _JunctionPath:
    def is_symlink(self) -> bool:
        return False

    def is_junction(self) -> bool:
        return True


class _PlainLegacyPath:
    def is_symlink(self) -> bool:
        return False


def test_supported_runtime_always_exposes_path_is_junction(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delattr(Path, "is_junction", raising=False)

    install_path_junction_compatibility()

    assert callable(getattr(Path, "is_junction", None))
    assert Path(tmp_path).is_junction() is False


def test_link_like_directory_short_circuits_symlinks() -> None:
    assert is_link_like_directory(_SymlinkPath()) is True


def test_link_like_directory_recognizes_available_junction_api() -> None:
    assert is_link_like_directory(_JunctionPath()) is True


def test_link_like_directory_accepts_plain_paths_without_junction_api() -> None:
    assert is_link_like_directory(_PlainLegacyPath()) is False
