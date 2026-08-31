"""Cross-version filesystem compatibility helpers for supported Python runtimes."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def _compat_is_junction(path: Path) -> bool:
    """Implement ``Path.is_junction`` for runtimes that predate that API."""

    if os.name != "nt":
        return False
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def install_path_junction_compatibility() -> None:
    """Install a safe ``Path.is_junction`` fallback on Python 3.11."""

    if not hasattr(Path, "is_junction"):
        setattr(Path, "is_junction", _compat_is_junction)


def is_link_like_directory(path: Path) -> bool:
    """Return whether *path* is a symlink or Windows junction."""

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else _compat_is_junction(path)


__all__ = ["install_path_junction_compatibility", "is_link_like_directory"]
